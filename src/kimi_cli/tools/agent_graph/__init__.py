from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, override

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.tools.agent_graph.static import build_topology
from kimi_cli.tools.agent_graph.view import build_agent_graph_view
from kimi_cli.tools.utils import ToolResultBuilder, load_desc

if TYPE_CHECKING:
    from kimi_cli.soul.agent import Runtime

__all__ = ["AnalyzeAgentGraph"]


class Params(BaseModel):
    agents: list[str] = Field(
        description=(
            'List of agent names to analyze (e.g. ["video-director"]). '
            'Use ["*"] to analyze all agents.'
        ),
    )
    mode: Literal["topology", "workflow", "full"] = Field(
        default="topology",
        description=(
            "Analysis mode. "
            '"topology": static agent topology only. '
            '"workflow": topology + workflow extraction (requires LLM). '
            '"full": topology + workflow + log analysis.'
        ),
    )


class AnalyzeAgentGraph(CallableTool2[Params]):
    name: str = "AnalyzeAgentGraph"
    description: str = load_desc(Path(__file__).parent / "analyze.md")
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        super().__init__()
        self._runtime = runtime

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        # --- Static topology ---
        try:
            topology = build_topology(params.agents)
        except Exception as e:
            return builder.error(f"Failed to build topology: {e}", brief="Error")

        n_agents = len(topology.nodes)
        n_edges = len(topology.edges)
        total_tools = sum(n.tool_count for n in topology.nodes)

        # --- Workflow extraction (if requested) ---
        workflow = None
        is_single_agent = len(params.agents) == 1 and params.agents[0] != "*"

        if params.mode in ("workflow", "full"):
            llm = self._runtime.llm
            if not llm:
                builder.write("[WARNING] LLM not available, skipping workflow extraction.\n\n")
            elif is_single_agent:
                from kimi_cli.tools.agent_graph.workflow import extract_workflow

                agent_name = params.agents[0]
                try:
                    workflow = await extract_workflow(agent_name, llm.chat_provider)
                    builder.write(f"Workflow extracted for {agent_name}: "
                                  f"{len(workflow.steps)} steps, {len(workflow.edges)} edges, "
                                  f"{len(workflow.constraints)} constraints.\n")
                    if workflow.warnings:
                        for w in workflow.warnings:
                            builder.write(f"  [WARN] {w}\n")
                    builder.write("\n")
                except Exception as e:
                    builder.write(f"[ERROR] Workflow extraction failed: {e}\n\n")
            else:
                builder.write(
                    "[INFO] Workflow extraction requires a single agent name "
                    "(not '*' or multiple agents). Showing topology only.\n\n"
                )

        # --- Log analysis (if mode=full and workflow available) ---
        deviation_report = None
        traces = None

        if params.mode == "full" and workflow and is_single_agent:
            from kimi_cli.tools.agent_graph.log_analyzer import analyze_log

            work_dir = str(self._runtime.builtin_args.KIMI_WORK_DIR)
            try:
                deviation_report, traces = analyze_log(work_dir, workflow)
                n_devs = sum(deviation_report.summary.values())
                builder.write(f"Log analysis: {n_devs} deviation(s) found ")
                builder.write(f"({deviation_report.summary}).\n")
                for sd in deviation_report.step_deviations:
                    builder.write(f"  [{sd.severity}] {sd.description}\n")
                n_traced = sum(len(st) for st in traces.values())
                builder.write(f"Traces: {len(traces)} steps, {n_traced} iterations.\n\n")
            except Exception as e:
                builder.write(f"[ERROR] Log analysis failed: {e}\n\n")

        # --- Build view ---
        view_block = build_agent_graph_view(topology, workflow, deviation_report, traces)
        builder.display(view_block)

        # --- Text summary ---
        builder.write(f"Agent topology: {n_agents} agents, {n_edges} edges, {total_tools} tools total.\n\n")
        for node in topology.nodes:
            subs = [e.target for e in topology.edges if e.source == node.id and e.edge_type == "SUBAGENT"]
            sub_str = f" -> [{', '.join(subs)}]" if subs else ""
            builder.write(f"- {node.name} ({node.tool_count} tools){sub_str}\n")

        # --- Workflow text summary ---
        if workflow:
            builder.write(f"\nWorkflow for {workflow.agent_id}:\n")
            for step in workflow.steps:
                agent_tag = f" [{step.agent_call}]" if step.agent_call else ""
                builder.write(f"  {step.id}: {step.label} ({step.kind}){agent_tag}\n")
            if workflow.constraints:
                builder.write(f"\nConstraints ({len(workflow.constraints)}):\n")
                for c in workflow.constraints:
                    builder.write(f"  [{c.check_type}] {c.rule}\n")

        brief = f"{n_agents} agents"
        if workflow:
            brief += f", {len(workflow.steps)} steps"
        return builder.ok(
            message=f"Topology: {n_agents} agents, {n_edges} edges",
            brief=brief,
        )
