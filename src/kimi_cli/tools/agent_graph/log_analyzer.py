"""Log analysis: parse JSONL session logs and detect deviations from workflow."""

from __future__ import annotations

import json
import re
from hashlib import md5
from pathlib import Path
from typing import Any

from kimi_cli.tools.display import (
    AgentWorkflow,
    DeviationReport,
    StepDeviation,
    StepTrace,
    TraceCall,
    TraceDeviation,
)


# ---------------------------------------------------------------------------
# Log discovery
# ---------------------------------------------------------------------------


def find_session_dirs(work_dir: str) -> list[Path]:
    """Find all session directories for a given work directory."""
    work_dir_hash = md5(work_dir.encode()).hexdigest()
    sessions_root = Path.home() / ".kimi" / "sessions" / work_dir_hash
    if not sessions_root.exists():
        return []
    return sorted(
        [d for d in sessions_root.iterdir() if d.is_dir() and (d / "context.jsonl").exists()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )


def load_log(session_dir: Path) -> list[dict[str, Any]]:
    """Load and parse a context.jsonl file."""
    log_file = session_dir / "context.jsonl"
    if not log_file.exists():
        return []
    entries: list[dict[str, Any]] = []
    with open(log_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


# ---------------------------------------------------------------------------
# Extract Task calls from log
# ---------------------------------------------------------------------------


def _extract_task_calls(log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract all Task tool calls from the log in order.

    Returns list of dicts:
      {
        "line_idx": int,
        "subagent_name": str,
        "session_id": str,
        "prompt": str,
        "tool_call_id": str,
        "result": str,        # filled from matching tool response
        "token_usage": int,
      }
    """
    calls: list[dict[str, Any]] = []
    # First pass: collect assistant Task calls
    pending_by_id: dict[str, dict[str, Any]] = {}
    for idx, entry in enumerate(log):
        role = entry.get("role")
        if role == "assistant":
            for tc in entry.get("tool_calls") or []:
                fn = tc.get("function", {})
                if fn.get("name") == "Task":
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}
                    call = {
                        "line_idx": idx,
                        "subagent_name": args.get("subagent_name", ""),
                        "session_id": args.get("session_id", ""),
                        "prompt": args.get("prompt", ""),
                        "tool_call_id": tc.get("id", ""),
                        "result": "",
                        "token_usage": 0,
                    }
                    calls.append(call)
                    pending_by_id[tc.get("id", "")] = call
        elif role == "tool":
            tcid = entry.get("tool_call_id", "")
            if tcid in pending_by_id:
                content = entry.get("content", "")
                if isinstance(content, list):
                    # Extract text parts
                    texts = []
                    for p in content:
                        if isinstance(p, dict) and p.get("type") == "text":
                            texts.append(p.get("text", ""))
                    content = "\n".join(texts)
                pending_by_id[tcid]["result"] = str(content)
        elif role == "_usage":
            # Associate with the most recent call
            if calls:
                calls[-1]["token_usage"] = entry.get("token_count", 0)
    return calls


def _extract_assistant_texts(log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract assistant text messages (thinking/responses) from the log.

    Returns list of dicts: {"line_idx": int, "text": str, "has_tool_calls": bool}
    """
    texts: list[dict[str, Any]] = []
    for idx, entry in enumerate(log):
        if entry.get("role") != "assistant":
            continue
        content = entry.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(p.get("text", ""))
            text = "\n".join(parts)
        has_tc = bool(entry.get("tool_calls"))
        if text or has_tc:
            texts.append({"line_idx": idx, "text": text, "has_tool_calls": has_tc})
    return texts


# ---------------------------------------------------------------------------
# Segment log by workflow steps
# ---------------------------------------------------------------------------


def segment_by_steps(
    log: list[dict[str, Any]],
    workflow: AgentWorkflow,
) -> dict[str, list[list[dict[str, Any]]]]:
    """Segment Task calls into workflow steps by matching subagent_name.

    Returns: {step_id: [[calls for iteration 1], [calls for iteration 2], ...]}
    """
    task_calls = _extract_task_calls(log)

    # Build step lookup: subagent_name -> list of step_ids
    agent_to_steps: dict[str, list[str]] = {}
    for step in workflow.steps:
        if step.agent_call:
            agent_to_steps.setdefault(step.agent_call, []).append(step.id)

    result: dict[str, list[list[dict[str, Any]]]] = {}
    last_step_id: str = ""

    for call in task_calls:
        subagent = call["subagent_name"]
        step_ids = agent_to_steps.get(subagent, [])
        if not step_ids:
            # Unmatched call - track under special key
            result.setdefault("_unmatched", [[]])
            result["_unmatched"][-1].append(call)
            continue

        # Pick the most likely step (for now, use the first match)
        # TODO: use ordering heuristics to disambiguate when multiple steps call the same agent
        step_id = step_ids[0]

        if step_id != last_step_id:
            # New step or new iteration
            if step_id not in result:
                result[step_id] = [[]]
            elif last_step_id != "" and step_id == last_step_id:
                pass  # continue current iteration
            else:
                # Check if we're returning to this step (new iteration)
                result[step_id].append([])
            last_step_id = step_id

        result[step_id][-1].append(call)

    return result


# ---------------------------------------------------------------------------
# Build step traces
# ---------------------------------------------------------------------------


def build_traces(
    segments: dict[str, list[list[dict[str, Any]]]],
    workflow: AgentWorkflow,
) -> dict[str, list[StepTrace]]:
    """Convert segmented calls into StepTrace objects."""
    step_lookup = {s.id: s for s in workflow.steps}
    traces: dict[str, list[StepTrace]] = {}

    for step_id, iterations in segments.items():
        if step_id == "_unmatched":
            continue
        step = step_lookup.get(step_id)
        step_traces: list[StepTrace] = []

        for iter_idx, calls in enumerate(iterations):
            trace_calls: list[TraceCall] = []
            total_tokens = 0

            for seq, call in enumerate(calls):
                # Assistant call
                trace_calls.append(TraceCall(
                    seq=seq * 2,
                    role="assistant",
                    tool_name="Task",
                    tool_args={
                        "subagent_name": call["subagent_name"],
                        "session_id": call["session_id"],
                        "prompt": call["prompt"][:500],
                    },
                ))
                # Tool result
                trace_calls.append(TraceCall(
                    seq=seq * 2 + 1,
                    role="tool",
                    tool_name="Task",
                    tool_result=call["result"][:1000],
                    token_usage=call["token_usage"],
                ))
                total_tokens += call["token_usage"]

            step_traces.append(StepTrace(
                step_id=step_id,
                iteration=iter_idx + 1,
                calls=trace_calls,
                expected_intent=step.description if step else "",
                applicable_rules=[
                    c.id for c in workflow.constraints
                    if step_id in c.applies_to
                ],
                total_tool_calls=len(calls),
                total_tokens=total_tokens,
            ))

        traces[step_id] = step_traces

    return traces


# ---------------------------------------------------------------------------
# Layer 1: Flow-level deviation detection
# ---------------------------------------------------------------------------


def detect_flow_deviations(
    segments: dict[str, list[list[dict[str, Any]]]],
    workflow: AgentWorkflow,
) -> list[StepDeviation]:
    """Detect step ordering, skipping, and loop violations."""
    deviations: list[StepDeviation] = []

    # Get expected step order (topological sort of workflow DAG)
    task_steps = [s for s in workflow.steps if s.kind == "task" and s.agent_call]
    expected_order = [s.id for s in task_steps]

    # Get actual step order from segments
    actual_order: list[str] = []
    # Rebuild from the original task_calls ordering (segments preserves this)
    seen_first: dict[str, int] = {}
    for step_id in segments:
        if step_id == "_unmatched":
            continue
        if step_id not in seen_first:
            seen_first[step_id] = len(actual_order)
            actual_order.append(step_id)

    # Check for skipped steps
    for step_id in expected_order:
        if step_id not in segments or all(len(it) == 0 for it in segments[step_id]):
            deviations.append(StepDeviation(
                step_id=step_id,
                deviation_type="skipped",
                severity="warning",
                description=f"Step '{step_id}' was expected but never executed.",
                expected=step_id,
                actual="(not executed)",
            ))

    # Check for loop violations
    for step_id, iterations in segments.items():
        if step_id == "_unmatched":
            continue
        n_iters = len(iterations)
        # Find max_loops for edges pointing back to this step
        for edge_key, max_iter in workflow.max_loops.items():
            if step_id in edge_key or edge_key == step_id:
                if n_iters > max_iter:
                    deviations.append(StepDeviation(
                        step_id=step_id,
                        deviation_type="loop_exceeded",
                        severity="error",
                        description=(
                            f"Step '{step_id}' executed {n_iters} iterations, "
                            f"exceeding the max of {max_iter}."
                        ),
                        expected=f"<= {max_iter} iterations",
                        actual=f"{n_iters} iterations",
                    ))

    # Check for unexpected calls
    expected_set = set(expected_order)
    if "_unmatched" in segments:
        for calls in segments["_unmatched"]:
            for call in calls:
                deviations.append(StepDeviation(
                    step_id="_unmatched",
                    deviation_type="unexpected",
                    severity="info",
                    description=(
                        f"Unmatched Task call to '{call['subagent_name']}' "
                        f"not mapped to any workflow step."
                    ),
                ))

    return deviations


# ---------------------------------------------------------------------------
# Layer 2: Constraint-level deviation detection
# ---------------------------------------------------------------------------


def detect_constraint_deviations(
    traces: dict[str, list[StepTrace]],
    workflow: AgentWorkflow,
) -> list[TraceDeviation]:
    """Detect constraint violations within traces.

    Currently implements rule-based checks (keyword, parameter, count).
    Semantic checks require LLM and are handled separately.
    """
    all_deviations: list[TraceDeviation] = []

    for constraint in workflow.constraints:
        if constraint.check_type == "semantic":
            continue  # Handled by LLM in Layer 3

        relevant_steps = constraint.applies_to or list(traces.keys())

        for step_id in relevant_steps:
            step_traces = traces.get(step_id, [])
            for trace in step_traces:
                for call in trace.calls:
                    deviation = _check_constraint(call, constraint)
                    if deviation:
                        call.deviations.append(deviation)
                        all_deviations.append(deviation)

    return all_deviations


def _check_constraint(call: TraceCall, constraint: WorkflowConstraint) -> TraceDeviation | None:
    """Check a single constraint against a single call."""
    from kimi_cli.tools.display import WorkflowConstraint

    if constraint.check_type == "parameter":
        # Check for required parameters (e.g. session_id)
        rule_lower = constraint.rule.lower()
        if "session_id" in rule_lower:
            if call.role == "assistant" and call.tool_name == "Task":
                sid = call.tool_args.get("session_id", "")
                if not sid:
                    return TraceDeviation(
                        constraint_id=constraint.id,
                        rule=constraint.rule,
                        severity="warning",
                        expected="session_id should be provided",
                        actual="session_id is empty",
                        evidence=f"Task call to {call.tool_args.get('subagent_name', '?')} missing session_id",
                    )

    elif constraint.check_type == "keyword":
        # Check for forbidden keywords in prompts
        rule_lower = constraint.rule.lower()
        if call.role == "assistant" and call.tool_name == "Task":
            prompt = call.tool_args.get("prompt", "")
            # Common forbidden patterns
            forbidden_patterns = []
            if "禁止降级" in constraint.rule or "local" in rule_lower:
                forbidden_patterns = ["ffmpeg", "ken burns", "animatic", "local assembly", "emergency"]
            if "禁止编造" in constraint.rule or "fabricat" in rule_lower:
                forbidden_patterns = ["正在刷新凭证", "refreshing credential", "每5秒重试"]

            for pattern in forbidden_patterns:
                if pattern.lower() in prompt.lower():
                    return TraceDeviation(
                        constraint_id=constraint.id,
                        rule=constraint.rule,
                        severity="error",
                        expected=f"Should not contain '{pattern}'",
                        actual=f"Found '{pattern}' in prompt",
                        evidence=f"Prompt excerpt: ...{prompt[max(0, prompt.lower().index(pattern.lower())-30):prompt.lower().index(pattern.lower())+50]}...",
                    )

    elif constraint.check_type == "count":
        # Count-based checks are handled at the flow level (loop_exceeded)
        pass

    return None


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------


def analyze_log(
    work_dir: str,
    workflow: AgentWorkflow,
    session_id: str | None = None,
    max_sessions: int = 1,
) -> tuple[DeviationReport, dict[str, list[StepTrace]]]:
    """Analyze session logs against a workflow.

    Args:
        work_dir: Working directory (used to find session logs).
        workflow: The extracted workflow to compare against.
        session_id: Specific session ID to analyze. None = most recent.
        max_sessions: Number of recent sessions to analyze.

    Returns:
        (DeviationReport, traces dict)
    """
    session_dirs = find_session_dirs(work_dir)
    if not session_dirs:
        return (
            DeviationReport(agent_id=workflow.agent_id, summary={"error": 0, "warning": 0, "info": 0}),
            {},
        )

    if session_id:
        session_dirs = [d for d in session_dirs if d.name == session_id]

    session_dirs = session_dirs[:max_sessions]

    all_step_deviations: list[StepDeviation] = []
    all_traces: dict[str, list[StepTrace]] = {}

    for sdir in session_dirs:
        log = load_log(sdir)
        if not log:
            continue

        # Segment by steps
        segments = segment_by_steps(log, workflow)

        # Build traces
        traces = build_traces(segments, workflow)

        # Layer 1: Flow deviations
        flow_devs = detect_flow_deviations(segments, workflow)
        all_step_deviations.extend(flow_devs)

        # Layer 2: Constraint deviations
        detect_constraint_deviations(traces, workflow)

        # Merge traces
        for step_id, step_traces in traces.items():
            all_traces.setdefault(step_id, []).extend(step_traces)

    # Summary counts
    severity_counts = {"error": 0, "warning": 0, "info": 0}
    for d in all_step_deviations:
        severity_counts[d.severity] = severity_counts.get(d.severity, 0) + 1
    # Also count trace-level deviations
    for step_traces in all_traces.values():
        for trace in step_traces:
            for call in trace.calls:
                for dev in call.deviations:
                    severity_counts[dev.severity] = severity_counts.get(dev.severity, 0) + 1

    report = DeviationReport(
        agent_id=workflow.agent_id,
        step_deviations=all_step_deviations,
        summary=severity_counts,
    )

    return report, all_traces
