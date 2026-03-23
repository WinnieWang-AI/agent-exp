from pathlib import Path
from typing import Literal, override

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.soul.agent import Runtime
from kimi_cli.tools.agent_graph.static import build_topology
from kimi_cli.tools.agent_graph.view import build_agent_graph_view, build_compare_view
from kimi_cli.tools.utils import ToolResultBuilder, load_desc

__all__ = ["AnalyzeAgentGraph"]


class Params(BaseModel):
    agents: list[str] = Field(
        description=(
            'List of agent names to analyze (e.g. ["video-director"]). '
            'Use ["*"] to analyze all agents.'
        ),
    )
    mode: Literal["topology", "workflow", "full", "compare"] = Field(
        default="topology",
        description=(
            "Analysis mode. "
            '"topology": static agent topology only. '
            '"workflow": topology + workflow extraction (requires LLM). '
            '"full": topology + workflow + log analysis. '
            '"compare": three-layer comparison (ideal plan vs prompt prediction vs actual behavior).'
        ),
    )
    task: str = Field(
        default="",
        description=(
            "Task description for compare mode. "
            "If empty, will be extracted from the most recent session log."
        ),
    )
    session_id: str = Field(
        default="",
        description="Specific session ID to analyze. Empty = most recent session.",
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

        is_single_agent = len(params.agents) == 1 and params.agents[0] != "*"

        # --- Compare mode (early return) ---
        if params.mode == "compare":
            if not is_single_agent:
                return builder.error(
                    "Compare mode requires a single agent name (not '*' or multiple agents).",
                    brief="Error",
                )
            return await self._run_compare(params, topology, builder)

        # --- Workflow extraction (if requested) ---
        workflow = None

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

    async def _run_compare(
        self,
        params: Params,
        topology: "AgentGraphTopology",
        builder: ToolResultBuilder,
    ) -> ToolReturnValue:
        """Execute three-layer comparison analysis."""
        from kimi_cli.agentspec import get_agents_dir, load_agent_spec
        from kimi_cli.tools.agent_graph.actual_tracer import find_chat_jsonl, trace_session
        from kimi_cli.tools.agent_graph.comparator import compare
        from kimi_cli.tools.agent_graph.ideal_planner import plan_ideal
        from kimi_cli.tools.agent_graph.prompt_predictor import predict_behavior

        agent_name = params.agents[0]
        work_dir = str(self._runtime.builtin_args.KIMI_WORK_DIR)
        llm = self._runtime.llm

        # --- Layer 3: Actual behavior (no LLM needed) ---
        actual = None
        chat_path = find_chat_jsonl(work_dir, params.session_id)
        if chat_path:
            try:
                actual = trace_session(chat_path)
                builder.write(
                    f"Layer 3 (actual): {len(actual.steps)} steps from {chat_path.name}\n"
                )
            except Exception as e:
                builder.write(f"[WARN] Layer 3 failed: {e}\n")
        else:
            builder.write("[WARN] No session log found, skipping layer 3 (actual behavior).\n")

        # Determine task description
        task = params.task
        if not task and actual:
            task = actual.task_description
        if not task:
            return builder.error(
                "No task description provided and none found in session logs. "
                "Use the 'task' parameter to specify the task.",
                brief="No task",
            )

        # --- Layer 1: Ideal plan (requires LLM) ---
        ideal = None
        if llm:
            agents_dir = get_agents_dir()
            agent_file = agents_dir / agent_name / "agent.yaml"
            if agent_file.exists():
                spec = load_agent_spec(agent_file)
                try:
                    ideal = await plan_ideal(task, spec, llm.chat_provider)
                    builder.write(f"Layer 1 (ideal): {len(ideal.steps)} steps\n")
                except Exception as e:
                    builder.write(f"[WARN] Layer 1 failed: {e}\n")
        else:
            builder.write("[WARN] LLM not available, skipping layer 1 (ideal plan).\n")

        # --- Layer 2: Prompt prediction (requires LLM) ---
        predicted = None
        if llm:
            try:
                predicted = await predict_behavior(task, agent_name, llm.chat_provider)
                builder.write(f"Layer 2 (predicted): {len(predicted.steps)} steps\n")
            except Exception as e:
                builder.write(f"[WARN] Layer 2 failed: {e}\n")
        else:
            builder.write("[WARN] LLM not available, skipping layer 2 (prompt prediction).\n")

        builder.write("\n")

        # --- Compare ---
        comparison = compare(ideal, predicted, actual, task)

        # --- Build view ---
        view_block = build_compare_view(comparison, topology)
        builder.display(view_block)

        # --- Text summary ---
        n_gaps = len(comparison.gaps)
        n_errors = sum(1 for g in comparison.gaps if g.severity == "error")
        n_warnings = sum(1 for g in comparison.gaps if g.severity == "warning")

        builder.write(f"Comparison: {n_gaps} gaps found ")
        builder.write(f"({n_errors} errors, {n_warnings} warnings)\n\n")

        if comparison.gaps:
            builder.write("Gaps:\n")
            for g in comparison.gaps:
                builder.write(
                    f"  [{g.severity}] {g.gap_type} ({g.layers[0]} vs {g.layers[1]}): "
                    f"{g.description}\n"
                )
                if g.suggestion:
                    builder.write(f"    -> {g.suggestion}\n")

        if comparison.diagnosis:
            builder.write(f"\nDiagnosis:\n{comparison.diagnosis}\n")

        layers_used = sum(1 for x in [ideal, predicted, actual] if x is not None)
        brief = f"{layers_used} layers, {n_gaps} gaps"
        return builder.ok(
            message=f"Three-layer comparison: {n_gaps} gaps ({n_errors} errors, {n_warnings} warnings)",
            brief=brief,
        )
