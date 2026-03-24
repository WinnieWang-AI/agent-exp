Spawn a subagent to perform a specific task. Subagent will be spawned with a fresh context without any history of yours.

**Context Isolation**

Context isolation is one of the key benefits of using subagents. By delegating tasks to subagents, you can keep your main context clean and focused on the main goal requested by the user.

Here are some scenarios you may want this tool for context isolation:

- You wrote some code and it did not work as expected. In this case you can spawn a subagent to fix the code, asking the subagent to return how it is fixed. This can potentially benefit because the detailed process of fixing the code may not be relevant to your main goal, and may clutter your context.
- When you need some latest knowledge of a specific library, framework or technology to proceed with your task, you can spawn a subagent to search on the internet for the needed information and return to you the gathered relevant information, for example code examples, API references, etc. This can avoid ton of irrelevant search results in your own context.

DO NOT directly forward the user prompt to Task tool. DO NOT simply spawn Task tool for each todo item. This will cause the user confused because the user cannot see what the subagent do. Only you can see the response from the subagent. So, only spawn subagents for very specific and narrow tasks like fixing a compilation error, or searching for a specific solution.

**Parallel Multi-Tasking**

Parallel multi-tasking is another key benefit of this tool. When the user request involves multiple subtasks that are independent of each other, you can use Task tool multiple times in a single response to let subagents work in parallel for you.

Examples:

- User requests to code, refactor or fix multiple modules/files in a project, and they can be tested independently. In this case you can spawn multiple subagents each working on a different module/file.
- When you need to analyze a huge codebase (> hundreds of thousands of lines), you can spawn multiple subagents each exploring on a different part of the codebase and gather the summarized results.
- When you need to search the web for multiple queries, you can spawn multiple subagents for better efficiency.

**Stateful Multi-Turn Dialogue**

By default, each Task call gives the subagent a fresh context with no memory of previous calls. When you need a subagent to remember previous interactions across multiple Task calls, provide a `session_id`. The same session_id will let the subagent resume its previous conversation context.

Use cases for stateful dialogue:
- An evaluator agent that tracks improvement trends across multiple feedback rounds
- A creator agent that iteratively refines its output based on accumulated feedback
- Any workflow requiring multi-turn collaboration between agents

Example: Use `session_id="eval_project1"` for all calls to an evaluator subagent within the same project, so it remembers its earlier analysis when comparing new results.

**Context Files (Data Passing)**

Use `context_files` to pass structured data files to the subagent instead of copying file content into the prompt. The subagent will see each file's content prepended to the prompt in `<file>` tags.

This is the preferred way to share project data (story graph, shot plan, configuration) with subagents:
- Keeps the prompt focused on the instruction (what to do)
- Avoids duplicating large file contents in the director's context
- The subagent gets the latest file content at call time

Example: `context_files: ["/path/to/story-graph.json", "/path/to/shot-plan.json"]`

Note: For stateful sessions (with `session_id`), the subagent already remembers files it read in previous calls. Only pass `context_files` on the first call or when files have changed.

**Available Subagents:**

${SUBAGENTS_MD}
