Analyze agent structure, workflow, and behavior.

Recursively parses agent.yaml definitions to extract agent nodes, their tools, and subagent relationships. Supports multiple analysis modes.

**Parameters:**
- `agents`: List of agent names to analyze, e.g. `["video-maker"]`. Use `["*"]` for all agents.
- `mode`:
  - `"topology"`: Static agent structure only.
  - `"workflow"`: + LLM-extracted workflow from system.md.
  - `"full"`: + log deviation analysis (workflow vs actual).
  - `"compare"`: Three-layer comparison — ideal plan vs prompt prediction vs actual behavior. Requires single agent.
- `task`: (compare mode) Task description. If empty, extracted from session logs.
- `session_id`: (compare mode) Specific session to analyze. Empty = most recent.
