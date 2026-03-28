import asyncio
import contextlib
import re
from pathlib import Path
from typing import override

from kosong.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.agentspec import get_agents_dir
from kimi_cli.soul import MaxStepsReached, RunCancelled, get_cancel_event_or_none, get_wire_or_none, run_soul
from kimi_cli.soul.agent import Agent, Runtime, load_agent
from kimi_cli.soul.context import Context
from kimi_cli.soul.kimisoul import KimiSoul
from kimi_cli.soul.toolset import get_current_tool_call_or_none
from kimi_cli.tools.utils import load_desc
from kimi_cli.wire import Wire
from kimi_cli.wire.types import (
    ApprovalRequest,
    ApprovalResponse,
    QuestionRequest,
    SubagentEvent,
    ToolCallRequest,
    WireMessage,
)

# Maximum continuation attempts for brief responses
MAX_CONTINUE_ATTEMPTS = 1

CONTINUE_PROMPT = """
Your previous response was too brief. Please provide a more comprehensive summary that includes:

1. Specific technical details and implementations
2. Complete code examples if relevant
3. Detailed findings and analysis
4. All important information that should be aware of by the caller
""".strip()


def _discover_agents() -> dict[str, Path]:
    """Discover all builtin agents by scanning the agents directory."""
    agents_dir = get_agents_dir()
    result: dict[str, Path] = {}
    if not agents_dir.is_dir():
        return result
    for entry in sorted(agents_dir.iterdir()):
        agent_file = entry / "agent.yaml"
        if entry.is_dir() and agent_file.exists():
            result[entry.name] = agent_file
    return result


class Params(BaseModel):
    agent_name: str = Field(
        description="Name of the builtin agent to chat with (e.g. 'video-director')."
    )
    message: str = Field(
        description=(
            "Your message to the agent. Provide all necessary context "
            "because the agent may not have access to your conversation history."
        )
    )
    session_id: str | None = Field(
        default=None,
        description=(
            "Optional session ID for stateful multi-turn dialogue. "
            "When provided, the agent resumes its previous conversation context. "
            "Use the same session_id across multiple calls to maintain continuity."
        ),
    )


class ChatWithAgent(CallableTool2[Params]):
    name: str = "ChatWithAgent"
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        self._available_agents = _discover_agents()
        agents_md = "\n".join(
            f"- `{name}`" for name in self._available_agents
        )
        super().__init__(
            description=load_desc(
                Path(__file__).parent / "chat.md",
                {"AGENTS_MD": agents_md},
            ),
        )
        self._runtime = runtime
        # Cache loaded agents to avoid reloading on every call
        self._loaded_agents: dict[str, Agent] = {}

    async def _get_or_load_agent(self, agent_name: str) -> Agent:
        """Load an agent by name, with caching."""
        if agent_name in self._loaded_agents:
            return self._loaded_agents[agent_name]

        agent_file = self._available_agents.get(agent_name)
        if agent_file is None:
            raise ValueError(
                f"Agent '{agent_name}' not found. "
                f"Available: {', '.join(self._available_agents.keys())}"
            )

        # Load the agent with an isolated runtime (like a fixed subagent)
        agent = await load_agent(
            agent_file,
            self._runtime.copy_for_fixed_subagent(),
            mcp_configs=[],
            _restore_dynamic_subagents=False,
        )
        self._loaded_agents[agent_name] = agent
        return agent

    async def _get_context_file(self, agent_name: str, session_id: str | None) -> Path:
        """Generate a context file path for the agent conversation."""
        parent = self._runtime.session.context_file.parent
        parent.mkdir(parents=True, exist_ok=True)

        if session_id is not None:
            sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", session_id)
            if not sanitized:
                sanitized = "unnamed"
            return parent / f"chat_{agent_name}_{sanitized}.jsonl"

        # Without session_id, use a unique file
        base = f"chat_{agent_name}"
        counter = 0
        while True:
            suffix = f"_{counter}" if counter > 0 else ""
            path = parent / f"{base}{suffix}.jsonl"
            if not path.exists():
                return path
            counter += 1

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        try:
            agent = await self._get_or_load_agent(params.agent_name)
        except ValueError as e:
            return ToolError(message=str(e), brief="Agent not found")

        try:
            return await self._run_agent(agent, params.agent_name, params.message, params.session_id)
        except Exception as e:
            return ToolError(
                message=f"Failed to run agent '{params.agent_name}': {e}",
                brief="Agent execution failed",
            )

    async def _run_agent(
        self,
        agent: Agent,
        agent_name: str,
        message: str,
        session_id: str | None = None,
    ) -> ToolReturnValue:
        """Run the agent and relay wire messages (questions, approvals) to the parent."""
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
                # Interactive messages (questions, approvals) pass through to the
                # parent wire so the calling agent can answer them.
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

        context_file = await self._get_context_file(agent_name, session_id)
        context = Context(file_backend=context_file)
        if session_id is not None and context_file.exists():
            await context.restore()
        soul = KimiSoul(agent, context=context)

        parent_cancel = get_cancel_event_or_none()
        cancel_event = asyncio.Event()

        async def _propagate_cancel():
            await parent_cancel.wait()
            cancel_event.set()

        propagate_task = asyncio.create_task(_propagate_cancel()) if parent_cancel else None
        try:
            await run_soul(soul, message, _ui_loop_fn, cancel_event)

            _error_msg = (
                f"Agent '{agent_name}' did not produce a valid response. "
                "You may need to retry or adjust your message."
            )

            if len(context.history) == 0 or context.history[-1].role != "assistant":
                return ToolError(message=_error_msg, brief="No response from agent")

            final_response = context.history[-1].extract_text(sep="\n")

            # Brief response continuation
            if len(final_response) < 200 and MAX_CONTINUE_ATTEMPTS > 0:
                await run_soul(soul, CONTINUE_PROMPT, _ui_loop_fn, cancel_event)
                if len(context.history) > 0 and context.history[-1].role == "assistant":
                    final_response = context.history[-1].extract_text(sep="\n")

            return ToolOk(output=final_response)
        except RunCancelled:
            raise
        except MaxStepsReached as e:
            return ToolError(
                message=(
                    f"Max steps {e.n_steps} reached when running agent '{agent_name}'. "
                    "Please try splitting the task into smaller parts."
                ),
                brief="Max steps reached",
            )
        finally:
            if propagate_task:
                propagate_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await propagate_task
