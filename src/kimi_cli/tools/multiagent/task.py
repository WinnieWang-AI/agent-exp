import asyncio
import contextlib
import re
import time
from pathlib import Path
from typing import override

import yaml
from kosong.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.soul import MaxStepsReached, RunCancelled, get_cancel_event_or_none, get_wire_or_none, run_soul
from kimi_cli.soul.agent import Agent, Runtime
from kimi_cli.soul.context import Context
from kimi_cli.soul.kimisoul import KimiSoul
from kimi_cli.soul.toolset import get_current_tool_call_or_none
from kimi_cli.tools.utils import load_desc
from kimi_cli.utils.path import next_available_rotation
from kimi_cli.wire import Wire
from kimi_cli.wire.types import (
    ApprovalRequest,
    ApprovalResponse,
    QuestionRequest,
    SubagentEvent,
    ToolCallRequest,
    WireMessage,
)

# Maximum continuation attempts for task summary
MAX_CONTINUE_ATTEMPTS = 1


CONTINUE_PROMPT = """
Your previous response was too brief. Please provide a more comprehensive summary that includes:

1. Specific technical details and implementations
2. Complete code examples if relevant
3. Detailed findings and analysis
4. All important information that should be aware of by the caller
""".strip()


class Params(BaseModel):
    description: str = Field(description="A short (3-5 word) description of the task")
    subagent_name: str = Field(
        description="The name of the specialized subagent to use for this task"
    )
    prompt: str = Field(
        description=(
            "The task instruction for the subagent. Keep this focused on WHAT to do. "
            "Use context_files to pass data files (entities, events, states, shots, etc.) "
            "instead of copying their content into the prompt."
        )
    )
    session_id: str | None = Field(
        default=None,
        description=(
            "Optional session ID for stateful multi-turn dialogue. "
            "When provided, the subagent resumes its previous conversation context "
            "instead of starting fresh. Use the same session_id across multiple "
            "Task calls to the same subagent to maintain continuity. "
            "This is useful for iterative workflows where a subagent needs to "
            "remember previous interactions (e.g., an evaluator tracking improvements "
            "across multiple rounds of feedback)."
        ),
    )
    context_files: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of file paths whose contents will be automatically "
            "prepended to the subagent's prompt as reference data. Use this to "
            "pass structured data (e.g., entities.json, events.json, shots.json) "
            "without copying them into the prompt text. "
            "The subagent will see: '<file: path>\\ncontent\\n</file>' for each file."
        ),
    )


def _build_prompt_with_context_files(
    prompt: str, context_files: list[str] | None
) -> str:
    """Prepend context file contents to the prompt.

    Each file is wrapped in <file> tags so the subagent can distinguish
    reference data from the actual instruction.
    """
    if not context_files:
        return prompt

    parts: list[str] = []
    for file_path in context_files:
        p = Path(file_path)
        if not p.exists():
            parts.append(f"<file path=\"{file_path}\">\n[File not found]\n</file>")
            continue
        try:
            content = p.read_text(encoding="utf-8")
            # Truncate very large files to avoid blowing up the subagent context
            max_chars = 50_000
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n... [truncated, {len(content)} chars total]"
            parts.append(f"<file path=\"{file_path}\">\n{content}\n</file>")
        except Exception as e:
            parts.append(f"<file path=\"{file_path}\">\n[Read error: {e}]\n</file>")

    if parts:
        return "\n".join(parts) + "\n\n" + prompt
    return prompt


# ---- Knowledge injection ----

# Map subagent names to role tags used in knowledge files
_AGENT_TO_ROLE: dict[str, str] = {
    "video-screenwriter": "screenwriter",
    "screenwriter": "screenwriter",
    "video-director": "director",
    "director": "director",
    "video-camera": "camera",
    "camera": "camera",
    "video-editor": "editor",
    "editor": "editor",
    "video-composer": "composer",
    "composer": "composer",
    "video-audience": "audience",
    "audience": "audience",
    "art-designer": "art-designer",
    "video-producer": "producer",
    "producer": "producer",
}

_KNOWLEDGE_MAX_ITEMS = 20


def _load_knowledge(
    role: str, user_id: str | None, knowledge_root: Path
) -> list[dict]:
    """Load online knowledge entries for a role, sorted by score desc, max 20.

    Reads from:
      knowledge_root/public/{role}.yaml   (public knowledge)
      knowledge_root/users/{user_id}/{role}.yaml  (personal knowledge)

    Returns list of entries with status=online, sorted by score descending.
    """
    entries: list[dict] = []

    # Public knowledge
    public_file = knowledge_root / "public" / f"{role}.yaml"
    if public_file.exists():
        try:
            data = yaml.safe_load(public_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                entries.extend(data)
        except Exception:
            pass

    # Personal knowledge
    if user_id:
        user_file = knowledge_root / "users" / user_id / f"{role}.yaml"
        if user_file.exists():
            try:
                data = yaml.safe_load(user_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    entries.extend(data)
            except Exception:
                pass

    # Filter: only online entries
    online = [e for e in entries if e.get("status") == "online"]

    # Sort by score descending (None treated as 0)
    online.sort(key=lambda e: e.get("score") or 0, reverse=True)

    return online[:_KNOWLEDGE_MAX_ITEMS]


def _extract_user_id_from_output_dir(session_output_dir: str) -> str | None:
    """Extract user_id from session_output_dir path.

    Expected format: .../output/{user_id}/{session_id}/...
    """
    parts = Path(session_output_dir).parts
    try:
        idx = parts.index("output")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    except ValueError:
        pass
    return None


_STEP_DECL_RE = re.compile(
    r"^(【目标】[^\n]*\n【验证】[^\n]*\n*)+", re.MULTILINE
)


def _strip_step_declarations(text: str) -> str:
    """Remove leading 【目标】/【验证】 blocks from subagent responses."""
    return _STEP_DECL_RE.sub("", text).lstrip("\n")


class Task(CallableTool2[Params]):
    name: str = "Task"
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        super().__init__(
            description=load_desc(
                Path(__file__).parent / "task.md",
                {
                    "SUBAGENTS_MD": "\n".join(
                        f"- `{name}`: {desc}"
                        for name, desc in runtime.labor_market.fixed_subagent_descs.items()
                    ),
                },
            ),
        )
        self._labor_market = runtime.labor_market
        self._session = runtime.session

        # Knowledge injection context
        session_output_dir = runtime.builtin_args.SESSION_OUTPUT_DIR
        self._session_output_dir = session_output_dir
        self._user_id = _extract_user_id_from_output_dir(session_output_dir)
        # Knowledge root: {work_dir}/knowledge/ (work_dir is cwd, output/ is under it)
        self._knowledge_root = runtime.session.work_dir.unsafe_to_local_path() / "knowledge"

    def _inject_knowledge(
        self, subagent_name: str, context_files: list[str]
    ) -> list[str]:
        """Load knowledge entries for this subagent and inject as a context file.

        Returns the list of injected knowledge IDs (for logging).
        """
        role = _AGENT_TO_ROLE.get(subagent_name)
        if not role or not self._knowledge_root or not self._knowledge_root.exists():
            return []

        entries = _load_knowledge(role, self._user_id, self._knowledge_root)
        if not entries:
            return []

        # Build knowledge content: only the rule text
        rules = [e.get("rule", "") for e in entries if e.get("rule")]
        if not rules:
            return []

        content = "以下是经过验证的领域知识，请在工作中参考：\n\n"
        for i, rule in enumerate(rules, 1):
            content += f"{i}. {rule}\n"

        # Write to temp file in session output dir
        knowledge_dir = Path(self._session_output_dir) / ".knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        knowledge_file = knowledge_dir / f"{role}.md"
        knowledge_file.write_text(content, encoding="utf-8")

        context_files.append(str(knowledge_file))

        # Log injection
        injected_ids = [e.get("id", "") for e in entries if e.get("rule")]
        self._log_injection(subagent_name, role, injected_ids)

        return injected_ids

    def _log_injection(
        self, subagent_name: str, role: str, knowledge_ids: list[str]
    ) -> None:
        """Append injection record to knowledge-injected.yaml for monitoring."""
        if not knowledge_ids or not self._session_output_dir:
            return

        log_path = Path(self._session_output_dir) / "knowledge-injected.yaml"
        existing: list[dict] = []
        if log_path.exists():
            try:
                existing = yaml.safe_load(log_path.read_text(encoding="utf-8")) or []
            except Exception:
                existing = []

        existing.append({
            "subagent": subagent_name,
            "role": role,
            "knowledge_ids": knowledge_ids,
            "timestamp": time.time(),
        })

        log_path.write_text(
            yaml.dump(existing, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    async def _get_subagent_context_file(self, session_id: str | None = None) -> Path:
        """Generate a context file path for subagent.

        If session_id is provided, returns a stable path so the subagent can
        resume its previous conversation context across multiple Task calls.
        Otherwise, generates a new unique path (original behaviour).
        """
        main_context_file = self._session.context_file
        parent = main_context_file.parent
        parent.mkdir(parents=True, exist_ok=True)

        if session_id is not None:
            sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", session_id)
            if not sanitized:
                sanitized = "unnamed"
            return parent / f"dialogue_{sanitized}.jsonl"

        subagent_base_name = f"{main_context_file.stem}_sub"
        sub_context_file = await next_available_rotation(
            parent / f"{subagent_base_name}{main_context_file.suffix}"
        )
        assert sub_context_file is not None
        return sub_context_file

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        subagents = self._labor_market.subagents

        if params.subagent_name not in subagents:
            return ToolError(
                message=f"Subagent not found: {params.subagent_name}",
                brief="Subagent not found",
            )
        agent = subagents[params.subagent_name]

        # Build the effective prompt: prepend context_files content if provided.
        # The caller controls which files to pass on each call, so we always
        # inject them — even on resumed sessions — to ensure new/updated
        # reference data (e.g. audience-review.json) is never silently dropped.
        context_files = list(params.context_files or [])

        # Knowledge injection: load matching knowledge entries and append as context file
        injected_ids = self._inject_knowledge(
            params.subagent_name, context_files
        )

        effective_prompt = _build_prompt_with_context_files(
            params.prompt, context_files or None
        )

        # Pre-compute context file path for error reporting
        subagent_context_file = await self._get_subagent_context_file(params.session_id)

        try:
            result = await self._run_subagent(agent, effective_prompt, params.session_id)
            return result
        except Exception as e:
            error_str = str(e)
            max_inline_chars = 2000
            if len(error_str) > max_inline_chars:
                error_file = subagent_context_file.with_suffix(".error.md")
                error_file.write_text(error_str, encoding="utf-8")
                error_str = error_str[:max_inline_chars] + f"\n\n[Full error ({len(error_str)} chars) saved to: {error_file}]"
            return ToolError(
                message=f"Failed to run subagent: {error_str}",
                brief="Subagent error",
            )

    async def _run_subagent(
        self, agent: Agent, prompt: str, session_id: str | None = None
    ) -> ToolReturnValue:
        """Run subagent with optional continuation for task summary."""
        super_wire = get_wire_or_none()
        assert super_wire is not None
        current_tool_call = get_current_tool_call_or_none()
        assert current_tool_call is not None
        current_tool_call_id = current_tool_call.id

        def _super_wire_send(msg: WireMessage) -> None:
            if isinstance(
                msg,
                ApprovalRequest | ApprovalResponse | ToolCallRequest | QuestionRequest,
            ):
                # Requests (and their resolution signals) should stay at the root wire level.
                super_wire.soul_side.send(msg)
                return

            event = SubagentEvent(
                task_tool_call_id=current_tool_call_id,
                event=msg,
            )
            super_wire.soul_side.send(event)

        async def _ui_loop_fn(wire: Wire) -> None:
            wire_ui = wire.ui_side(merge=True)
            while True:
                msg = await wire_ui.receive()
                _super_wire_send(msg)

        subagent_context_file = await self._get_subagent_context_file(session_id)
        context = Context(file_backend=subagent_context_file)
        if session_id is not None and subagent_context_file.exists():
            await context.restore()
        soul = KimiSoul(agent, context=context)

        parent_cancel = get_cancel_event_or_none()
        cancel_event = asyncio.Event()

        async def _propagate_cancel():
            await parent_cancel.wait()
            cancel_event.set()

        propagate_task = asyncio.create_task(_propagate_cancel()) if parent_cancel else None
        try:
            await run_soul(soul, prompt, _ui_loop_fn, cancel_event)

            _error_msg = (
                "The subagent seemed not to run properly. Maybe you have to do the task yourself."
            )

            # Check if the subagent context is valid
            if len(context.history) == 0 or context.history[-1].role != "assistant":
                return ToolError(message=_error_msg, brief="Failed to run subagent")

            final_response = context.history[-1].extract_text(sep="\n")

            # Strip leading step declarations (【目标】...【验证】...) that are internal
            # to the subagent and not useful for the parent agent's context.
            final_response = _strip_step_declarations(final_response)

            # Check if response is too brief, if so, run again with continuation prompt
            n_attempts_remaining = MAX_CONTINUE_ATTEMPTS
            if len(final_response) < 200 and n_attempts_remaining > 0:
                await run_soul(soul, CONTINUE_PROMPT, _ui_loop_fn, cancel_event)

                if len(context.history) == 0 or context.history[-1].role != "assistant":
                    return ToolError(message=_error_msg, brief="Failed to run subagent")
                final_response = context.history[-1].extract_text(sep="\n")

            # If the response is very long, save to file and return a summary + pointer
            # to avoid bloating the parent agent's context
            max_inline_chars = 2000
            if len(final_response) > max_inline_chars:
                report_file = subagent_context_file.with_suffix(".report.md")
                report_file.write_text(final_response, encoding="utf-8")
                # Keep the first portion as inline summary, point to file for full content
                summary = final_response[:max_inline_chars]
                return ToolOk(
                    output=f"{summary}\n\n[Full report ({len(final_response)} chars) saved to: {report_file}]"
                )

            return ToolOk(output=final_response)
        except RunCancelled:
            raise  # propagate to parent
        except MaxStepsReached as e:
            return ToolError(
                message=(
                    f"Max steps {e.n_steps} reached when running subagent. "
                    "Please try splitting the task into smaller subtasks."
                ),
                brief="Max steps reached",
            )
        finally:
            if propagate_task:
                propagate_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await propagate_task
