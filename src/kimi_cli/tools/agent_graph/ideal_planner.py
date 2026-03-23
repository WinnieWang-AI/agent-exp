"""Layer 1: LLM-based ideal execution planning.

Given a task description and available tools/subagents, plan the optimal
execution strategy without looking at any agent's system prompt.
"""

from __future__ import annotations

import json
import re
from typing import Any

from kosong.chat_provider import ChatProvider
from kosong.message import Message, TextPart

from kimi_cli.agentspec import ResolvedAgentSpec
from kimi_cli.tools.display import ExecutionPlan, PlanStep

_SYSTEM_PROMPT = """\
You are an expert task planner. Given a task description and available tools/subagents, \
plan the most efficient execution strategy.

You should think purely about what is the BEST way to accomplish this task. \
Do NOT consider any existing agent prompt or workflow — just focus on correctness and efficiency.

Output ONLY valid JSON matching this schema — no markdown fences, no explanation:

{
  "steps": [
    {
      "id": "string (unique, e.g. step_1)",
      "label": "string (short description)",
      "kind": "tool_call | delegation | decision | read | write",
      "agent": "string (subagent name if delegation, empty otherwise)",
      "tool": "string (tool name if tool_call, empty otherwise)",
      "resources_in": ["file paths consumed"],
      "resources_out": ["file paths produced"],
      "rationale": "string (why this step is needed)",
      "parallel_group": "string (same value for steps that can run in parallel, empty if serial)"
    }
  ],
  "step_order": [["step_1"], ["step_2", "step_3"], ["step_4"]]
}

Rules:
1. step_order is a list of batches. Each batch is a list of step IDs that can run in parallel.
2. Batches execute sequentially — batch N+1 starts after batch N completes.
3. Minimize total sequential batches (maximize parallelism where possible).
4. Only use tools/subagents from the provided list.
5. Each step should have a clear purpose — no redundant steps.
6. Use "delegation" kind for subagent calls, "tool_call" for direct tool use.
7. Use "decision" kind for branching points (e.g. checking a condition).
"""


def _build_user_message(task: str, spec: ResolvedAgentSpec) -> str:
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
        f"Task: {task}\n\n"
        f"Available subagents:\n{subagents_str}\n\n"
        f"Available tools: {tools_str}\n"
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def _parse_plan(data: dict[str, Any], task: str) -> ExecutionPlan:
    steps = []
    for s in data.get("steps", []):
        steps.append(PlanStep(
            id=s["id"],
            label=s.get("label", ""),
            kind=s.get("kind", "tool_call"),
            agent=s.get("agent", ""),
            tool=s.get("tool", ""),
            resources_in=s.get("resources_in", []),
            resources_out=s.get("resources_out", []),
            rationale=s.get("rationale", ""),
            parallel_group=s.get("parallel_group", ""),
        ))
    step_order = data.get("step_order", [[s.id] for s in steps])
    return ExecutionPlan(
        source="ideal",
        task_description=task,
        steps=steps,
        step_order=step_order,
    )


async def plan_ideal(
    task: str,
    spec: ResolvedAgentSpec,
    chat_provider: ChatProvider,
) -> ExecutionPlan:
    """Generate an ideal execution plan for a task.

    Args:
        task: The task description.
        spec: The agent spec (used only for available tools/subagents list).
        chat_provider: LLM provider for planning.

    Returns:
        ExecutionPlan with source="ideal".
    """
    user_msg = _build_user_message(task, spec)
    history = [Message(role="user", content=user_msg)]

    streamed = await chat_provider.generate(
        _SYSTEM_PROMPT, tools=[], history=history
    )
    parts: list[str] = []
    async for part in streamed:
        if isinstance(part, TextPart):
            parts.append(part.text)

    raw = "".join(parts)
    data = _extract_json(raw)
    return _parse_plan(data, task)
