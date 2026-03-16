Analyze agent structure and generate a visual topology graph.

Recursively parses agent.yaml definitions to extract agent nodes, their tools, and subagent relationships. Outputs an interactive graph visualization.

**Parameters:**
- `agents`: List of agent names to analyze, e.g. `["video-director"]`. Use `["*"]` for all agents.
- `mode`: `"topology"` (static structure only), `"workflow"` (+ workflow extraction), or `"full"` (+ log analysis).
