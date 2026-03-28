import asyncio
import contextlib
import re
from pathlib import Path
from typing import override

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
            "Use context_files to pass data files (story graph, shot plan, etc.) "
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
            "pass structured data (e.g., story-graph.json, shot-plan.json, "
            "project-context.json) without copying them into the prompt text. "
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

        # Build the effective prompt: prepend context_files content if provided,
        # but skip injection if this is a resumed session (dialogue file already exists)
        # to avoid duplicating data the subagent already has in its history.
        context_files = params.context_files
        if context_files and params.session_id is not None:
            subagent_file = await self._get_subagent_context_file(params.session_id)
            if subagent_file.exists():
                context_files = None
        effective_prompt = _build_prompt_with_context_files(
            params.prompt, context_files
        )

        try:
            result = await self._run_subagent(agent, effective_prompt, params.session_id)
            return result
        except Exception as e:
            # Truncate long error messages to avoid polluting parent context
            error_str = str(e)
            if len(error_str) > 300:
                error_str = error_str[:300] + "..."
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
