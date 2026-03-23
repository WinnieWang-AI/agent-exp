"""
Parse chat.jsonl wire messages into an agent operation graph.

The graph shows:
1. User goals (from TurnBegin)
2. Task delegations (director -> subagent via Task tool)
3. Tool calls within each delegation
4. Resources (files/assets) produced or consumed
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


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
    "CheckVideoJob": {},
    "CheckMusicJob": {},
}

_FILE_ARG_KEYS = {"path", "file_path", "output_path", "image_path", "save_path", "input_path", "story_graph_path"}


def _guess_resource_type(path: str) -> str:
    p = path.lower()
    if p.endswith(".json"):
        return "json"
    if p.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "image"
    if p.endswith((".mp4", ".mov", ".webm")):
        return "video"
    if p.endswith((".mp3", ".wav", ".m4a", ".flac")):
        return "audio"
    return "file"


def _short_path(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= 3:
        return path
    return ".../" + "/".join(parts[-3:])


# Trivial messages that should not become goal nodes
_TRIVIAL_RE = re.compile(
    r"^(继续|好的?|确认|ok|是的?|对|嗯|可以|没问题|就这样|开始|go|yes|done|lgtm|就用这个|好 的)$",
    re.IGNORECASE,
)


def _is_trivial_message(text: str) -> bool:
    return bool(_TRIVIAL_RE.match(text.strip()))


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


def parse_chat_to_op_graph(chat_path: Path) -> dict[str, Any]:
    """Parse a chat.jsonl file and return an operation graph."""

    if not chat_path.exists():
        return {"goal": "", "nodes": [], "edges": [], "stats": {}}

    entries = []
    for line in chat_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    resource_nodes: dict[str, str] = {}  # path -> node_id

    goal_text = ""
    delegation_idx = 0
    tool_idx = 0
    seq_num = 0  # global sequence number for ordering
    current_turn_goal: str | None = None
    current_goal_id: str | None = None
    goal_connected = False

    # Track active delegations by task_tool_call_id
    delegations: dict[str, dict[str, Any]] = {}
    # Map inner tool_call_id → tool node id (for matching ToolResult)
    inner_call_to_node: dict[str, str] = {}

    # For detecting parallel vs serial delegations:
    # Collect pending Task ToolCalls (not yet resolved by ToolResult).
    # If we see another Task ToolCall before the previous one's ToolResult, they are parallel.
    pending_task_calls: list[str] = []  # list of delegation node ids awaiting ToolResult
    # Last completed batch of delegations (serial predecessors for next batch)
    last_completed_batch: list[str] = []
    # Current batch of parallel delegations being dispatched
    current_parallel_batch: list[str] = []

    def ensure_resource(path: str) -> str:
        if path in resource_nodes:
            return resource_nodes[path]
        rid = f"res_{len(resource_nodes)}"
        resource_nodes[path] = rid
        nodes.append({
            "id": rid,
            "type": "resource",
            "resource_type": _guess_resource_type(path),
            "label": _short_path(path),
            "path": path,
        })
        node_ids.add(rid)
        return rid

    def ensure_goal(text: str) -> str:
        nonlocal current_goal_id
        # Reuse existing goal node for same text
        for n in nodes:
            if n["type"] == "goal" and n.get("text") == text:
                current_goal_id = n["id"]
                return n["id"]
        gid = f"goal_{len([n for n in nodes if n['type'] == 'goal'])}"
        label = text[:60] + ("..." if len(text) > 60 else "")
        nodes.append({"id": gid, "type": "goal", "label": label, "text": text})
        node_ids.add(gid)
        current_goal_id = gid
        return gid

    for entry in entries:
        role = entry.get("role")
        content = entry.get("content")
        ts = entry.get("timestamp", 0)

        # User message -> potential goal (skip trivial confirmations)
        if role == "user" and isinstance(content, str) and content.strip():
            text = content.strip()
            if not text.startswith("[Session resumed") and not _is_trivial_message(text):
                current_turn_goal = text
                goal_connected = False  # new goal, not yet connected
                if not goal_text:
                    goal_text = text
                ensure_goal(text)

        if not isinstance(content, dict):
            continue

        msg_type = content.get("type", "")
        payload = content.get("payload", {})

        # TurnBegin with user_input
        if msg_type == "TurnBegin":
            user_input = payload.get("user_input", "")
            if isinstance(user_input, str) and user_input.strip():
                text = user_input.strip()
                if not text.startswith("[Session resumed") and not _is_trivial_message(text):
                    current_turn_goal = text
                    goal_connected = False
                    if not goal_text:
                        goal_text = text
                    ensure_goal(text)

        # Top-level ToolCall
        if msg_type == "ToolCall":
            fn = payload.get("function", {})
            fn_name = fn.get("name", "")
            call_id = payload.get("id", "")
            args = _extract_args(fn.get("arguments"))

            if fn_name == "Task":
                delegation_idx += 1
                seq_num += 1
                did = f"delegation_{delegation_idx}"
                subagent = args.get("subagent_name", "?")
                desc = args.get("description", "")
                prompt = args.get("prompt", "")
                session_id_val = args.get("session_id", "")

                nodes.append({
                    "id": did,
                    "type": "delegation",
                    "label": desc or f"Task -> {subagent}",
                    "agent": subagent,
                    "session_id": session_id_val,
                    "prompt_preview": prompt[:300] if prompt else "",
                    "timestamp": ts,
                    "seq": seq_num,
                })
                node_ids.add(did)
                delegations[call_id] = {"id": did, "agent": subagent, "call_id": call_id}

                # goal -> only the first delegation after this goal
                if current_goal_id and not goal_connected:
                    edges.append({"source": current_goal_id, "target": did, "type": "requires"})
                    goal_connected = True

                # Add to current parallel batch
                current_parallel_batch.append(did)
                pending_task_calls.append(call_id)

            else:
                # Director-level tool call (not Task)
                tool_idx += 1
                tid = f"tool_{tool_idx}"
                nodes.append({
                    "id": tid,
                    "type": "tool_call",
                    "label": fn_name,
                    "tool": fn_name,
                    "agent": "director",
                    "args_preview": json.dumps(args, ensure_ascii=False)[:200],
                    "timestamp": ts,
                    "result": None,
                })
                node_ids.add(tid)
                if call_id:
                    inner_call_to_node[call_id] = tid

                produced, consumed = _extract_file_paths(fn_name, args)
                for p in consumed:
                    edges.append({"source": ensure_resource(p), "target": tid, "type": "consumed_by"})
                for p in produced:
                    edges.append({"source": tid, "target": ensure_resource(p), "type": "produces"})

        # Top-level ToolResult
        if msg_type == "ToolResult":
            result_call_id = payload.get("tool_call_id", "")
            # Attach result to director-level tool_call nodes
            tool_node_id = inner_call_to_node.get(result_call_id)
            if tool_node_id and result_call_id not in [d.get("call_id") for d in delegations.values()]:
                rv = payload.get("return_value", {})
                if rv:
                    msg_text = rv.get("message", "") or rv.get("output", "")
                    if len(msg_text) > 300:
                        msg_text = msg_text[:300] + "..."
                    for n in nodes:
                        if n["id"] == tool_node_id:
                            n["result"] = msg_text
                            n["is_error"] = rv.get("is_error", False)
                            break
            if result_call_id in pending_task_calls:
                pending_task_calls.remove(result_call_id)
                # When all pending tasks in the batch are done, finalize the batch
                if len(pending_task_calls) == 0 and current_parallel_batch:
                    # Wire edges from last_completed_batch -> current_parallel_batch
                    if last_completed_batch:
                        for prev_id in last_completed_batch:
                            for cur_id in current_parallel_batch:
                                edges.append({
                                    "source": prev_id,
                                    "target": cur_id,
                                    "type": "followed_by",
                                })
                    # Mark parallel relationships within the batch
                    if len(current_parallel_batch) > 1:
                        for did in current_parallel_batch:
                            # Tag the node as parallel
                            for n in nodes:
                                if n["id"] == did:
                                    n["parallel_group"] = f"par_{delegation_idx}"
                                    break
                    last_completed_batch = list(current_parallel_batch)
                    current_parallel_batch = []

        # SubagentEvent — tool calls inside delegations
        if msg_type == "SubagentEvent":
            task_call_id = payload.get("task_tool_call_id", "")
            inner = payload.get("event", {})
            inner_type = inner.get("type", "")

            delegation_info = delegations.get(task_call_id)
            if not delegation_info:
                continue

            if inner_type == "ToolCall":
                inner_payload = inner.get("payload", {})
                fn = inner_payload.get("function", {})
                fn_name = fn.get("name", "")
                inner_call_id = inner_payload.get("id", "")
                args = _extract_args(fn.get("arguments"))

                tool_idx += 1
                tid = f"tool_{tool_idx}"
                nodes.append({
                    "id": tid,
                    "type": "tool_call",
                    "label": fn_name,
                    "tool": fn_name,
                    "agent": delegation_info["agent"],
                    "parent_delegation": delegation_info["id"],
                    "args_preview": json.dumps(args, ensure_ascii=False)[:200],
                    "timestamp": ts,
                    "result": None,  # filled in by ToolResult
                })
                node_ids.add(tid)
                if inner_call_id:
                    inner_call_to_node[inner_call_id] = tid

                # delegation -> tool_call
                edges.append({"source": delegation_info["id"], "target": tid, "type": "executes"})

                # resource edges
                produced, consumed = _extract_file_paths(fn_name, args)
                for p in consumed:
                    edges.append({"source": ensure_resource(p), "target": tid, "type": "consumed_by"})
                for p in produced:
                    edges.append({"source": tid, "target": ensure_resource(p), "type": "produces"})

            # ToolResult inside SubagentEvent — attach result to the tool_call node
            if inner_type == "ToolResult":
                inner_payload = inner.get("payload", {})
                result_call_id = inner_payload.get("tool_call_id", "")
                tool_node_id = inner_call_to_node.get(result_call_id)
                if tool_node_id:
                    rv = inner_payload.get("return_value", {})
                    is_error = rv.get("is_error", False)
                    message = rv.get("message", "")
                    output = rv.get("output", "")
                    # Build a concise result summary
                    result_text = message or output
                    if not result_text:
                        # Try display blocks
                        for db in rv.get("display", []):
                            if db.get("type") == "brief" and db.get("text"):
                                result_text = db["text"]
                                break
                    # Truncate
                    if len(result_text) > 300:
                        result_text = result_text[:300] + "..."
                    # Attach to node
                    for n in nodes:
                        if n["id"] == tool_node_id:
                            n["result"] = result_text
                            n["is_error"] = is_error
                            break

    # Handle any remaining incomplete batch (session ended mid-execution)
    if current_parallel_batch and last_completed_batch:
        for prev_id in last_completed_batch:
            for cur_id in current_parallel_batch:
                edges.append({"source": prev_id, "target": cur_id, "type": "followed_by"})
        if len(current_parallel_batch) > 1:
            for did in current_parallel_batch:
                for n in nodes:
                    if n["id"] == did:
                        n["parallel_group"] = f"par_end"
                        break

    # Filter edges to valid nodes
    valid_edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    # Build ordered steps from delegation nodes and followed_by edges
    # A "step" is either a single serial delegation or a group of parallel delegations
    delegation_nodes = [n for n in nodes if n["type"] == "delegation"]
    steps: list[dict[str, Any]] = []
    assigned: set[str] = set()

    # Group by parallel_group
    par_groups: dict[str, list[str]] = {}
    for n in delegation_nodes:
        pg = n.get("parallel_group")
        if pg:
            par_groups.setdefault(pg, []).append(n["id"])

    # Walk delegations in seq order
    sorted_delegations = sorted(delegation_nodes, key=lambda n: n.get("seq", 0))
    for n in sorted_delegations:
        if n["id"] in assigned:
            continue
        pg = n.get("parallel_group")
        if pg and pg in par_groups:
            group_ids = par_groups[pg]
            steps.append({
                "type": "parallel",
                "delegation_ids": group_ids,
            })
            assigned.update(group_ids)
        else:
            steps.append({
                "type": "serial",
                "delegation_ids": [n["id"]],
            })
            assigned.add(n["id"])

    return {
        "goal": goal_text,
        "nodes": nodes,
        "edges": valid_edges,
        "steps": steps,
        "stats": {
            "goals": len([n for n in nodes if n["type"] == "goal"]),
            "delegations": delegation_idx,
            "tool_calls": tool_idx,
            "resources": len(resource_nodes),
        },
    }
