"""Static topology analysis: parse agent.yaml files to build agent graph."""

from __future__ import annotations

from pathlib import Path

from kimi_cli.agentspec import ResolvedAgentSpec, get_agents_dir, load_agent_spec
from kimi_cli.tools.display import AgentGraphEdge, AgentGraphNode, AgentGraphTopology


def _short_tool_name(tool_ref: str) -> str:
    """Extract short tool name from a module:Class reference."""
    # "kimi_cli.tools.multiagent:Task" -> "Task"
    if ":" in tool_ref:
        return tool_ref.rsplit(":", 1)[1]
    return tool_ref


def _discover_agent_files(names: list[str]) -> list[Path]:
    """Resolve agent names to agent.yaml paths.

    If names is ["*"], discover all agents under the agents directory.
    Otherwise, resolve each name to its agent.yaml path.
    """
    agents_dir = get_agents_dir()
    if names == ["*"]:
        return sorted(agents_dir.glob("*/agent.yaml"))
    result: list[Path] = []
    for name in names:
        candidate = agents_dir / name / "agent.yaml"
        if candidate.exists():
            result.append(candidate)
        else:
            # Try treating it as a path
            p = Path(name)
            if p.exists():
                result.append(p)
    return result


def _infer_agent_name(spec: ResolvedAgentSpec, agent_file: Path, override_name: str = "") -> str:
    """Get agent name, falling back to directory name if spec.name is empty."""
    if override_name:
        return override_name
    if spec.name:
        return spec.name
    # Fallback: use parent directory name (e.g. "default" from agents/default/agent.yaml)
    return agent_file.parent.name


def _collect_agent_recursive(
    agent_file: Path,
    nodes: dict[str, AgentGraphNode],
    edges: list[AgentGraphEdge],
    visited: set[str],
    override_name: str = "",
) -> None:
    """Recursively parse an agent and its subagents."""
    try:
        spec = load_agent_spec(agent_file)
    except Exception:
        return

    name = _infer_agent_name(spec, agent_file, override_name)
    if name in visited:
        return
    visited.add(name)

    tools = [_short_tool_name(t) for t in spec.tools]
    node = AgentGraphNode(
        id=name,
        name=name,
        tools=tools,
        tool_count=len(tools),
        subagent_count=len(spec.subagents),
    )
    nodes[name] = node

    for sub_name, sub_spec in spec.subagents.items():
        edges.append(AgentGraphEdge(
            source=name,
            target=sub_name,
            edge_type="SUBAGENT",
            description=sub_spec.description,
        ))
        _collect_agent_recursive(sub_spec.path, nodes, edges, visited, override_name=sub_name)


def build_topology(agent_names: list[str]) -> AgentGraphTopology:
    """Build the full agent topology from a list of agent names.

    Args:
        agent_names: Agent names to analyze. ["*"] means all agents.

    Returns:
        AgentGraphTopology with all discovered nodes and edges.
    """
    agent_files = _discover_agent_files(agent_names)
    nodes: dict[str, AgentGraphNode] = {}
    edges: list[AgentGraphEdge] = []
    visited: set[str] = set()

    for af in agent_files:
        _collect_agent_recursive(af, nodes, edges, visited)

    # Deduplicate edges (same source-target pair)
    seen_edges: set[tuple[str, str, str]] = set()
    unique_edges: list[AgentGraphEdge] = []
    for e in edges:
        key = (e.source, e.target, e.edge_type)
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)

    return AgentGraphTopology(
        nodes=list(nodes.values()),
        edges=unique_edges,
    )
