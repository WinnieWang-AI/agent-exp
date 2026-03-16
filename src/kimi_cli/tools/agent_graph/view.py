"""Build AgentGraphViewDisplayBlock from topology, workflow, and deviation data."""

from __future__ import annotations

from kimi_cli.tools.display import (
    AgentGraphTopology,
    AgentGraphViewDisplayBlock,
    AgentWorkflow,
    DeviationReport,
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
