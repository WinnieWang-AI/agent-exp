Chat with an independent agent by name. The target agent is loaded dynamically — it does NOT need to be declared as a subagent.

Use this when you need to have a multi-turn, interactive conversation with another agent. The target agent can ask you questions (via AskUserQuestion), and you can answer them in subsequent calls.

Use `session_id` to maintain conversation continuity across multiple calls. The target agent will remember previous interactions within the same session.

Available agents:
${AGENTS_MD}

Parameters:
- `agent_name`: Name of the builtin agent to chat with (e.g. "video-maker", "video-creator").
- `message`: Your message to the agent, as a user would type it.
- `session_id`: Optional session ID for stateful multi-turn dialogue. Use the same ID across calls to maintain context.