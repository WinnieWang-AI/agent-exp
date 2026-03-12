Submit a video generation job, wait for completion, and download the result — all in one call.

This is the **preferred tool for video generation**. Unlike GenerateVideo + CheckVideoJob, this tool handles the full lifecycle automatically.

**Parallel execution:** Call this tool multiple times in the same response to generate multiple clips concurrently. Independent shots (no Technique C dependency) can and should be generated in parallel.

**Parameters are identical to GenerateVideo**, with the addition of:
- `download_path` (required): Where to save the completed video
- `poll_interval_seconds`: How often to check status (default 10s)
- `timeout_seconds`: Max wait time (default 600s)

**Important:** This tool calls a paid external API. The user will be asked for approval before submission.
