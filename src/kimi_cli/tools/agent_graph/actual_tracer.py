"""Layer 3: Parse wire-format session logs into an ExecutionPlan of actual behavior."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from kimi_cli.tools.display import ExecutionPlan, PlanStep

# Step declaration parsing (【目标】...【验证】...)
_STEP_GOAL_RE = re.compile(r"【目标】\s*(.+?)(?=\n【|$)", re.DOTALL)
_STEP_CHECK_RE = re.compile(r"【验证】\s*(.+?)(?=\n【|$)", re.DOTALL)


def _parse_step_declaration(text: str) -> dict[str, str] | None:
    goal_m = _STEP_GOAL_RE.search(text)
    if not goal_m:
        return None
    result: dict[str, str] = {"goal": goal_m.group(1).strip()}
    check_m = _STEP_CHECK_RE.search(text)
    if check_m:
        result["check_criteria"] = check_m.group(1).strip()
    return result


# Tools that interact with files/resources
_RESOURCE_TOOLS = {
    "WriteFile": {"produces": ["path", "file_path"]},
    "ReadFile": {"consumes": ["path", "file_path"]},
    "StrReplaceFile": {"produces": ["path", "file_path"], "consumes": ["path", "file_path"]},
    "GenerateImage": {"produces": ["save_path", "output_path"]},
    "GenerateVideo": {"produces": ["output_path"]},
    "GenerateVideoSync": {"produces": ["output_path"]},
    "VideoEdit": {"produces": ["output_path"], "consumes": ["input_path"]},
    "GenerateMusic": {"produces": ["output_path"]},
    "GenerateSpeech": {"produces": ["output_path"]},
    "ValidateStoryGraph": {"consumes": ["path", "file_path"]},
    "LinearizeStoryGraph": {"consumes": ["story_graph_path"], "produces": ["output_path"]},
    "ManageVideoProject": {},
    "ReadMediaFile": {"consumes": ["path", "file_path"]},
    "AnalyzeImage": {"consumes": ["image_path"]},
    "AnalyzeVideo": {"consumes": ["video_path"]},
}

_FILE_ARG_KEYS = {
    "path", "file_path", "output_path", "image_path",
    "save_path", "input_path", "story_graph_path", "video_path",
}

_TRIVIAL_RE = re.compile(
    r"^(继续|好的?|确认|ok|是的?|对|嗯|可以|没问题|就这样|开始|go|yes|done|lgtm|就用这个|好 的)$",
    re.IGNORECASE,
)


def _extract_args(arguments: str | None) -> dict[str, Any]:
    if not arguments:
        return {}
    try:
        return json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_file_paths(tool_name: str, args: dict[str, Any]) -> tuple[list[str], list[str]]:
    spec = _RESOURCE_TOOLS.get(tool_name, {})
    produced: list[str] = []
    consumed: list[str] = []

    for key in spec.get("produces", []):
        val = args.get(key)
        if isinstance(val, str) and val:
            produced.append(val)

    for key in spec.get("consumes", []):
        val = args.get(key)
        if isinstance(val, str) and val:
            consumed.append(val)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item:
                    consumed.append(item)

    # Fallback: scan known file-arg keys
    if not produced and not consumed:
        for key, val in args.items():
            if isinstance(val, str) and key in _FILE_ARG_KEYS and val:
                consumed.append(val)

    return produced, consumed


def _short_path(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= 3:
        return path
    return ".../" + "/".join(parts[-3:])


def trace_session(chat_path: Path) -> ExecutionPlan:
    """Parse a chat.jsonl (wire-format) file into an ExecutionPlan.

    Args:
        chat_path: Path to chat.jsonl with wire-format messages.

    Returns:
        ExecutionPlan with source="actual".
    """
    if not chat_path.exists():
        return ExecutionPlan(source="actual", task_description="", steps=[], step_order=[])

    entries: list[dict[str, Any]] = []
    for line in chat_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    steps: list[PlanStep] = []
    step_ids: set[str] = set()
    task_description = ""

    delegation_idx = 0
    tool_idx = 0

    # Track delegations by tool_call_id
    delegations: dict[str, str] = {}  # call_id -> step_id
    delegation_agents: dict[str, str] = {}  # call_id -> agent name
    # Track inner tool calls for matching results
    inner_call_to_step: dict[str, str] = {}

    # Parallel detection
    pending_task_calls: list[str] = []  # call_ids not yet resolved
    current_parallel_batch: list[str] = []  # step_ids in current batch
    all_batches: list[list[str]] = []  # finalized batches for step_order

    # Step declarations and narratives
    pending_step_decl: dict[str, str] | None = None
    subagent_pending_step_decl: dict[str, dict[str, str]] = {}  # task_call_id -> decl
    recently_completed_delegations: list[str] = []

    for entry in entries:
        role = entry.get("role")
        content = entry.get("content")

        # Extract task description from user messages
        if role == "user" and isinstance(content, str) and content.strip():
            text = content.strip()
            if not text.startswith("[Session resumed") and not _TRIVIAL_RE.match(text):
                if not task_description:
                    task_description = text
            recently_completed_delegations = []

        if not isinstance(content, dict):
            continue

        msg_type = content.get("type", "")
        payload = content.get("payload", {})

        # TurnBegin with user_input
        if msg_type == "TurnBegin":
            user_input = payload.get("user_input", "")
            if isinstance(user_input, str) and user_input.strip():
                text = user_input.strip()
                if not text.startswith("[Session resumed") and not _TRIVIAL_RE.match(text):
                    if not task_description:
                        task_description = text

        # Top-level ToolCall
        if msg_type == "ToolCall":
            fn = payload.get("function", {})
            fn_name = fn.get("name", "")
            call_id = payload.get("id", "")
            args = _extract_args(fn.get("arguments"))

            if fn_name == "Task":
                delegation_idx += 1
                sid = f"actual_delegation_{delegation_idx}"
                subagent = args.get("subagent_name", "?")
                desc = args.get("description", "")
                prompt = args.get("prompt", "")

                step = PlanStep(
                    id=sid,
                    label=desc or f"Task -> {subagent}",
                    kind="delegation",
                    agent=subagent,
                    tool="Task",
                    rationale=prompt[:200] if prompt else "",
                    intent=prompt or "",
                )
                # Attach step declaration if present
                if pending_step_decl:
                    step.goal = pending_step_decl.get("goal", "")
                    step.check_criteria = pending_step_decl.get("check_criteria", "")
                    pending_step_decl = None
                steps.append(step)
                step_ids.add(sid)
                delegations[call_id] = sid
                delegation_agents[call_id] = subagent

                current_parallel_batch.append(sid)
                pending_task_calls.append(call_id)

            else:
                # Maker-level tool call
                tool_idx += 1
                sid = f"actual_tool_{tool_idx}"
                produced, consumed = _extract_file_paths(fn_name, args)

                step = PlanStep(
                    id=sid,
                    label=fn_name,
                    kind="tool_call",
                    agent="maker",
                    tool=fn_name,
                    resources_in=[_short_path(p) for p in consumed],
                    resources_out=[_short_path(p) for p in produced],
                )
                if pending_step_decl:
                    step.goal = pending_step_decl.get("goal", "")
                    step.check_criteria = pending_step_decl.get("check_criteria", "")
                    pending_step_decl = None
                steps.append(step)
                step_ids.add(sid)
                if call_id:
                    inner_call_to_step[call_id] = sid

        # Top-level ToolResult
        if msg_type == "ToolResult":
            result_call_id = payload.get("tool_call_id", "")

            # Attach result to maker tool call
            step_id = inner_call_to_step.get(result_call_id)
            if step_id and result_call_id not in delegations:
                rv = payload.get("return_value", {})
                if rv:
                    msg_text = rv.get("message", "") or rv.get("output", "")
                    if len(msg_text) > 200:
                        msg_text = msg_text[:200] + "..."
                    for s in steps:
                        if s.id == step_id:
                            s.result_summary = msg_text
                            s.is_error = rv.get("is_error", False)
                            break

            # Track completed delegations for maker summary attachment
            if result_call_id in delegations:
                recently_completed_delegations.append(delegations[result_call_id])

            # Finalize parallel batch
            if result_call_id in pending_task_calls:
                pending_task_calls.remove(result_call_id)
                if len(pending_task_calls) == 0 and current_parallel_batch:
                    all_batches.append(list(current_parallel_batch))
                    # Tag parallel groups
                    if len(current_parallel_batch) > 1:
                        pg = f"par_{len(all_batches)}"
                        for s in steps:
                            if s.id in current_parallel_batch:
                                s.parallel_group = pg
                    current_parallel_batch = []

        # SubagentEvent — tool calls inside delegations
        if msg_type == "SubagentEvent":
            task_call_id = payload.get("task_tool_call_id", "")
            inner = payload.get("event", {})
            inner_type = inner.get("type", "")

            parent_step_id = delegations.get(task_call_id)
            parent_agent = delegation_agents.get(task_call_id, "?")
            if not parent_step_id:
                continue

            if inner_type == "ToolCall":
                inner_payload = inner.get("payload", {})
                fn = inner_payload.get("function", {})
                fn_name = fn.get("name", "")
                inner_call_id = inner_payload.get("id", "")
                args = _extract_args(fn.get("arguments"))

                tool_idx += 1
                sid = f"actual_tool_{tool_idx}"
                produced, consumed = _extract_file_paths(fn_name, args)

                step = PlanStep(
                    id=sid,
                    label=f"{parent_agent}/{fn_name}",
                    kind="tool_call",
                    agent=parent_agent,
                    tool=fn_name,
                    resources_in=[_short_path(p) for p in consumed],
                    resources_out=[_short_path(p) for p in produced],
                )
                # Attach subagent step declaration if present
                sub_decl = subagent_pending_step_decl.pop(task_call_id, None)
                if sub_decl:
                    step.goal = sub_decl.get("goal", "")
                    step.check_criteria = sub_decl.get("check_criteria", "")
                steps.append(step)
                step_ids.add(sid)
                if inner_call_id:
                    inner_call_to_step[inner_call_id] = sid

            if inner_type == "ToolResult":
                inner_payload = inner.get("payload", {})
                result_call_id = inner_payload.get("tool_call_id", "")
                step_id = inner_call_to_step.get(result_call_id)
                if step_id:
                    rv = inner_payload.get("return_value", {})
                    is_error = rv.get("is_error", False)
                    result_text = rv.get("message", "") or rv.get("output", "")
                    if not result_text:
                        for db in rv.get("display", []):
                            if db.get("type") == "brief" and db.get("text"):
                                result_text = db["text"]
                                break
                    if len(result_text) > 200:
                        result_text = result_text[:200] + "..."
                    for s in steps:
                        if s.id == step_id:
                            s.result_summary = result_text
                            s.is_error = is_error
                            break

            # ContentPart inside SubagentEvent — step declaration or report
            if inner_type == "ContentPart":
                inner_payload = inner.get("payload", {})
                text = inner_payload.get("text", "")
                if text.strip():
                    sub_step_decl = _parse_step_declaration(text)
                    if sub_step_decl:
                        subagent_pending_step_decl[task_call_id] = sub_step_decl
                    else:
                        # Subagent report — attach to parent delegation step
                        for s in steps:
                            if s.id == parent_step_id:
                                existing = s.subagent_report
                                s.subagent_report = (existing + "\n" + text).strip() if existing else text
                                break

        # Maker-level ContentPart — step declaration or summary
        if msg_type == "ContentPart":
            text = payload.get("text", "")
            if text.strip():
                step_decl = _parse_step_declaration(text)
                if step_decl:
                    pending_step_decl = step_decl
                else:
                    # Maker summary — attach to recently completed delegations
                    for did in recently_completed_delegations:
                        for s in steps:
                            if s.id == did:
                                s.maker_summary = text
                                break

    # Handle incomplete batch
    if current_parallel_batch:
        all_batches.append(list(current_parallel_batch))
        if len(current_parallel_batch) > 1:
            pg = f"par_{len(all_batches)}"
            for s in steps:
                if s.id in current_parallel_batch:
                    s.parallel_group = pg

    # Build step_order: delegation batches define the high-level order,
    # tool calls under each delegation are nested within
    step_order = all_batches if all_batches else [[s.id] for s in steps if s.kind == "delegation"]

    return ExecutionPlan(
        source="actual",
        task_description=task_description,
        steps=steps,
        step_order=step_order,
    )


def find_chat_jsonl(work_dir: str, session_id: str = "") -> Path | None:
    """Find the most recent chat.jsonl for a work directory.

    Looks for wire-format chat logs in ~/.kimi/sessions/{hash}/.
    """
    from hashlib import md5

    work_dir_hash = md5(work_dir.encode()).hexdigest()
    sessions_root = Path.home() / ".kimi" / "sessions" / work_dir_hash
    if not sessions_root.exists():
        return None

    if session_id:
        candidate = sessions_root / session_id / "chat.jsonl"
        if candidate.exists():
            return candidate

    # Find most recent session with chat.jsonl
    candidates: list[Path] = []
    for d in sessions_root.iterdir():
        if d.is_dir():
            chat = d / "chat.jsonl"
            if chat.exists():
                candidates.append(chat)
    if not candidates:
        # Fallback: look for context.jsonl (older format)
        for d in sessions_root.iterdir():
            if d.is_dir():
                ctx = d / "context.jsonl"
                if ctx.exists():
                    candidates.append(ctx)

    if not candidates:
        return None

    return max(candidates, key=lambda p: p.stat().st_mtime)
