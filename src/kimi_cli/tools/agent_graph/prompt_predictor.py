"""Layer 2: LLM-based prompt behavior prediction.

Given a task description and an agent's system prompt + config, predict
how the agent would execute the task by following its prompt rules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from kosong.chat_provider import ChatProvider
from kosong.message import Message, TextPart

from kimi_cli.agentspec import ResolvedAgentSpec, get_agents_dir, load_agent_spec
from kimi_cli.tools.display import ExecutionPlan, PlanStep

_SYSTEM_PROMPT = """\
You are an agent behavior predictor. Given an AI agent's system prompt (system.md), \
its tool/subagent configuration, and a specific task, predict step-by-step how this \
agent would execute the task.

You must follow the agent's prompt rules exactly — predict what it WOULD do, not what \
it SHOULD do. Pay attention to:
- The workflow/steps defined in the prompt
- Constraints and rules (must/never/always)
- Decision points and branching logic
- Which subagents it would delegate to and in what order
- What tools it would call directly

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
      "rationale": "string (which prompt rule drives this step)",
      "parallel_group": "string (same value for parallel steps, empty if serial)"
    }
  ],
  "step_order": [["step_1"], ["step_2", "step_3"], ["step_4"]]
}

Rules:
1. step_order is a list of batches. Each batch is a list of step IDs that can run in parallel.
2. Batches execute sequentially.
3. Predict based on the agent's prompt, not on what you think is optimal.
4. If the prompt says to do X before Y, predict X before Y even if it seems suboptimal.
5. Include decision steps where the prompt has conditional logic.
6. In rationale, cite the specific prompt section/rule driving each step.
"""


def _build_user_message(task: str, spec: ResolvedAgentSpec, system_md: str) -> str:
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
        f"Agent name: {spec.name}\n\n"
        f"Subagents:\n{subagents_str}\n\n"
        f"Tools: {tools_str}\n\n"
        f"--- system.md ---\n{system_md}\n--- end ---"
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
        source="predicted",
        task_description=task,
        steps=steps,
        step_order=step_order,
    )


async def predict_behavior(
    task: str,
    agent_name: str,
    chat_provider: ChatProvider,
) -> ExecutionPlan:
    """Predict how an agent would execute a task based on its prompt.

    Args:
        task: The task description.
        agent_name: Agent name (used to locate agent.yaml and system.md).
        chat_provider: LLM provider for prediction.

    Returns:
        ExecutionPlan with source="predicted".
    """
    agents_dir = get_agents_dir()
    agent_file = agents_dir / agent_name / "agent.yaml"
    if not agent_file.exists():
        raise ValueError(f"Agent not found: {agent_name}")

    spec = load_agent_spec(agent_file)
    system_md_path = spec.system_prompt_path
    if not Path(system_md_path).exists():
        raise ValueError(f"System prompt not found: {system_md_path}")
    system_md = Path(system_md_path).read_text(encoding="utf-8")

    user_msg = _build_user_message(task, spec, system_md)
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
