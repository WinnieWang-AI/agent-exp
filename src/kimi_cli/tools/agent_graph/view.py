"""Build display blocks from topology, workflow, deviation, and comparison data."""

from __future__ import annotations

from typing import Any

from kimi_cli.tools.display import (
    AgentGraphTopology,
    AgentGraphViewDisplayBlock,
    AgentWorkflow,
    DeviationReport,
    PlanComparison,
    PlanCompareViewDisplayBlock,
    StepTrace,
)


def build_agent_graph_view(
    topology: AgentGraphTopology,
    workflow: AgentWorkflow | None = None,
    deviation_report: DeviationReport | None = None,
    traces: dict[str, list[StepTrace]] | None = None,
) -> AgentGraphViewDisplayBlock:
    """Build display block for the agent graph visualization.

    Args:
        topology: The agent topology (nodes and edges).
        workflow: Optional extracted workflow for a single agent.
        deviation_report: Optional deviation report from log analysis.
        traces: Optional step traces from log analysis.

    Returns:
        AgentGraphViewDisplayBlock ready for frontend rendering.
    """
    n_agents = len(topology.nodes)
    n_edges = len(topology.edges)
    total_tools = sum(n.tool_count for n in topology.nodes)

    # Count root agents (not a target of any SUBAGENT edge)
    targets = {e.target for e in topology.edges if e.edge_type == "SUBAGENT"}
    root_agents = [n for n in topology.nodes if n.id not in targets]

    summary: dict[str, object] = {
        "agents": n_agents,
        "edges": n_edges,
        "total_tools": total_tools,
        "root_agents": len(root_agents),
    }

    if workflow:
        summary["workflow_steps"] = len(workflow.steps)
        summary["workflow_edges"] = len(workflow.edges)
        summary["constraints"] = len(workflow.constraints)
        loop_edges = [e for e in workflow.edges if e.is_loop]
        summary["loops"] = len(loop_edges)

    if deviation_report:
        summary["deviations"] = deviation_report.summary

    return AgentGraphViewDisplayBlock(
        topology=topology,
        workflow=workflow,
        deviation_report=deviation_report,
        traces=traces or {},
        summary=summary,
    )


def build_compare_view(
    comparison: PlanComparison,
    topology: AgentGraphTopology | None = None,
) -> PlanCompareViewDisplayBlock:
    """Build display block for three-layer comparison visualization.

    Args:
        comparison: The PlanComparison result.
        topology: Optional agent topology for context.

    Returns:
        PlanCompareViewDisplayBlock ready for frontend rendering.
    """
    summary: dict[str, Any] = {
        "task": comparison.task_description[:100],
        "layers": sum(1 for x in [comparison.ideal, comparison.predicted, comparison.actual] if x),
        "total_gaps": len(comparison.gaps),
        "errors": sum(1 for g in comparison.gaps if g.severity == "error"),
        "warnings": sum(1 for g in comparison.gaps if g.severity == "warning"),
    }

    if comparison.ideal:
        summary["ideal_steps"] = len(comparison.ideal.steps)
    if comparison.predicted:
        summary["predicted_steps"] = len(comparison.predicted.steps)
    if comparison.actual:
        summary["actual_steps"] = len(comparison.actual.steps)

    # Gap breakdown by layer pair
    layer_gap_counts: dict[str, int] = {}
    for g in comparison.gaps:
        key = f"{g.layers[0]}_vs_{g.layers[1]}"
        layer_gap_counts[key] = layer_gap_counts.get(key, 0) + 1
    summary["gap_breakdown"] = layer_gap_counts

    return PlanCompareViewDisplayBlock(
        comparison=comparison,
        summary=summary,
    )
