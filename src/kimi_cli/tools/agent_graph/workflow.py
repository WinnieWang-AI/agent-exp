"""Workflow extraction: use LLM to parse agent system.md into a workflow graph."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from kosong.chat_provider import ChatProvider
from kosong.message import Message, TextPart

from kimi_cli.agentspec import ResolvedAgentSpec, get_agents_dir, load_agent_spec
from kimi_cli.tools.display import (
    AgentWorkflow,
    WorkflowConstraint,
    WorkflowEdge,
    WorkflowStep,
)

# Maximum number of LLM retries on validation failure
_MAX_RETRIES = 2

_EXTRACTION_SYSTEM_PROMPT = """\
You are a workflow extraction engine. Given an AI agent's system prompt (system.md) and its \
subagent/tool configuration, extract the agent's workflow as a structured JSON graph.

Output ONLY valid JSON matching this schema — no markdown fences, no explanation:

{
  "steps": [
    {
      "id": "string (unique, e.g. step_1, decision_approve, uc_story)",
      "label": "string (short human-readable label)",
      "kind": "begin | end | task | decision | user_confirm",
      "agent_call": "string or null (subagent name if this step calls a subagent)",
      "description": "string (brief description of what happens)"
    }
  ],
  "edges": [
    {
      "source": "step id",
      "target": "step id",
      "label": "string (condition label for decision edges, empty for sequential)",
      "is_loop": true/false
    }
  ],
  "constraints": [
    {
      "id": "string (unique, e.g. c_full_feedback)",
      "rule": "string (the exact rule text from the prompt)",
      "applies_to": ["step_id", ...],
      "check_type": "keyword | parameter | count | semantic"
    }
  ],
  "max_loops": {
    "edge_id_or_description": max_iteration_count
  }
}

Rules for extraction:
1. Always include exactly one "begin" step and one "end" step.
2. Every step must be reachable from "begin".
3. "end" must be reachable from "begin".
4. For "decision" steps (branching points), every outgoing edge MUST have a non-empty label.
5. "user_confirm" steps represent explicit user confirmation/approval gates.
6. "task" steps represent actions (calling subagents, reading files, etc).
7. Mark loop-back edges with "is_loop": true and record max iterations in "max_loops".
8. Extract constraints from Rules/规则 sections — rules containing "must", "always", "never", \
"禁止", "必须", "总是" etc.
9. For check_type: use "keyword" if checkable by string matching, "parameter" if checkable by \
inspecting tool call args, "count" if it's about limits/counts, "semantic" if it needs LLM judgment.
10. Only reference subagent names that appear in the provided subagent list.
11. If the prompt describes multiple workflows (e.g. "Video Creation", "Audio-Only"), model the \
primary workflow fully and note alternative entry points as branches from the begin node.
"""


def _build_user_message(spec: ResolvedAgentSpec, system_md: str) -> str:
    """Build the user message for LLM extraction."""
    subagents_info = []
    for name, sub in spec.subagents.items():
        subagents_info.append(f"  - {name}: {sub.description}")
    subagents_str = "\n".join(subagents_info) if subagents_info else "  (none)"

    tools_short = []
    for t in spec.tools:
        short = t.rsplit(":", 1)[1] if ":" in t else t
        tools_short.append(short)
    tools_str = ", ".join(tools_short)

    return (
        f"Agent name: {spec.name}\n\n"
        f"Subagents:\n{subagents_str}\n\n"
        f"Tools: {tools_str}\n\n"
        f"--- system.md ---\n{system_md}\n--- end ---"
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    # Try to find JSON in code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def _validate_structure(data: dict[str, Any]) -> list[str]:
    """Validate the workflow graph structure. Returns list of issues."""
    issues: list[str] = []
    steps = data.get("steps", [])
    edges = data.get("edges", [])

    step_ids = {s["id"] for s in steps}

    # Check begin/end
    begin_steps = [s for s in steps if s.get("kind") == "begin"]
    end_steps = [s for s in steps if s.get("kind") == "end"]
    if len(begin_steps) != 1:
        issues.append(f"Expected exactly 1 begin step, found {len(begin_steps)}")
    if len(end_steps) != 1:
        issues.append(f"Expected exactly 1 end step, found {len(end_steps)}")

    # Check edge references
    for e in edges:
        if e.get("source") not in step_ids:
            issues.append(f"Edge source '{e.get('source')}' not in steps")
        if e.get("target") not in step_ids:
            issues.append(f"Edge target '{e.get('target')}' not in steps")

    # Check reachability from begin
    if begin_steps:
        begin_id = begin_steps[0]["id"]
        reachable: set[str] = set()
        queue = [begin_id]
        adj: dict[str, list[str]] = {sid: [] for sid in step_ids}
        for e in edges:
            src, dst = e.get("source", ""), e.get("target", "")
            if src in adj:
                adj[src].append(dst)
        while queue:
            node = queue.pop()
            if node in reachable:
                continue
            reachable.add(node)
            for nb in adj.get(node, []):
                if nb not in reachable:
                    queue.append(nb)

        unreachable = step_ids - reachable
        if unreachable:
            issues.append(f"Steps unreachable from begin: {sorted(unreachable)}")

        if end_steps and end_steps[0]["id"] not in reachable:
            issues.append("End step is not reachable from begin")

    # Check decision nodes have labeled edges
    decision_ids = {s["id"] for s in steps if s.get("kind") == "decision"}
    for did in decision_ids:
        out_edges = [e for e in edges if e.get("source") == did]
        if len(out_edges) > 1:
            for e in out_edges:
                if not e.get("label", "").strip():
                    issues.append(f"Decision '{did}' has unlabeled outgoing edge to '{e.get('target')}'")

    return issues


def _validate_consistency(data: dict[str, Any], spec: ResolvedAgentSpec) -> list[str]:
    """Check that agent_call references exist in subagents."""
    issues: list[str] = []
    subagent_names = set(spec.subagents.keys())

    for step in data.get("steps", []):
        agent_call = step.get("agent_call")
        if agent_call and agent_call not in subagent_names:
            issues.append(
                f"Step '{step['id']}' references agent '{agent_call}' "
                f"which is not in subagents: {sorted(subagent_names)}"
            )
    return issues


def _validate_coverage(data: dict[str, Any], spec: ResolvedAgentSpec) -> list[str]:
    """Check that all subagents appear in the workflow."""
    warnings: list[str] = []
    subagent_names = set(spec.subagents.keys())
    referenced = {s.get("agent_call") for s in data.get("steps", []) if s.get("agent_call")}
    missing = subagent_names - referenced
    for name in sorted(missing):
        warnings.append(
            f"Subagent '{name}' is declared in agent.yaml but not referenced in the workflow. "
            "It may appear in an alternative workflow branch not captured."
        )
    return warnings


def _parse_workflow(data: dict[str, Any], agent_id: str, warnings: list[str]) -> AgentWorkflow:
    """Parse validated JSON into AgentWorkflow model."""
    steps = [
        WorkflowStep(
            id=s["id"],
            label=s["label"],
            kind=s["kind"],
            agent_call=s.get("agent_call"),
            description=s.get("description", ""),
        )
        for s in data.get("steps", [])
    ]
    edges = [
        WorkflowEdge(
            source=e["source"],
            target=e["target"],
            label=e.get("label", ""),
            is_loop=e.get("is_loop", False),
        )
        for e in data.get("edges", [])
    ]
    constraints = [
        WorkflowConstraint(
            id=c["id"],
            rule=c["rule"],
            applies_to=c.get("applies_to", []),
            check_type=c.get("check_type", "semantic"),
        )
        for c in data.get("constraints", [])
    ]
    max_loops = data.get("max_loops", {})

    return AgentWorkflow(
        agent_id=agent_id,
        steps=steps,
        edges=edges,
        constraints=constraints,
        max_loops=max_loops,
        warnings=warnings,
    )


async def _call_llm(chat_provider: ChatProvider, system_md: str, spec: ResolvedAgentSpec) -> str:
    """Call the LLM to extract workflow, return raw text response.

    Retries on rate-limit (429) errors with exponential backoff.
    """
    import asyncio

    user_msg = _build_user_message(spec, system_md)
    history = [Message(role="user", content=user_msg)]

    max_api_retries = 3
    for attempt in range(max_api_retries + 1):
        try:
            streamed = await chat_provider.generate(
                _EXTRACTION_SYSTEM_PROMPT, tools=[], history=history
            )
            parts: list[str] = []
            async for part in streamed:
                if isinstance(part, TextPart):
                    parts.append(part.text)
            return "".join(parts)
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "RateLimit" in err_str or "rate" in err_str.lower()) and attempt < max_api_retries:
                wait = 2 ** (attempt + 1)  # 2, 4, 8 seconds
                await asyncio.sleep(wait)
                continue
            raise


async def extract_workflow(
    agent_name: str,
    chat_provider: ChatProvider,
) -> AgentWorkflow:
    """Extract workflow from an agent's system.md using LLM.

    Args:
        agent_name: The agent name (used to locate agent.yaml).
        chat_provider: The LLM chat provider for extraction.

    Returns:
        AgentWorkflow with steps, edges, constraints.

    Raises:
        ValueError: If extraction fails after retries.
    """
    # Load agent spec and system.md
    agents_dir = get_agents_dir()
    agent_file = agents_dir / agent_name / "agent.yaml"
    if not agent_file.exists():
        raise ValueError(f"Agent not found: {agent_name}")

    spec = load_agent_spec(agent_file)
    system_md_path = spec.system_prompt_path
    if not Path(system_md_path).exists():
        raise ValueError(f"System prompt not found: {system_md_path}")
    system_md = Path(system_md_path).read_text(encoding="utf-8")

    last_error = ""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            raw_response = await _call_llm(chat_provider, system_md, spec)
            data = _extract_json(raw_response)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = f"JSON parse error (attempt {attempt + 1}): {e}"
            continue

        # Validate structure
        struct_issues = _validate_structure(data)
        if struct_issues:
            last_error = f"Structure validation failed (attempt {attempt + 1}): {struct_issues}"
            continue

        # Validate consistency (remove invalid references)
        consist_issues = _validate_consistency(data, spec)
        for issue in consist_issues:
            # Auto-fix: null out invalid agent_call references
            for step in data.get("steps", []):
                agent_call = step.get("agent_call")
                if agent_call and agent_call not in spec.subagents:
                    step["agent_call"] = None

        # Check coverage (warnings only)
        warnings = _validate_coverage(data, spec)
        if consist_issues:
            warnings.extend(f"Auto-fixed: {i}" for i in consist_issues)

        return _parse_workflow(data, agent_name, warnings)

    raise ValueError(f"Workflow extraction failed after {_MAX_RETRIES + 1} attempts. Last error: {last_error}")
