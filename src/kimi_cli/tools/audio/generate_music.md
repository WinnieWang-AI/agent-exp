Submit an asynchronous music generation job. Returns a job_id immediately — use CheckMusicJob to poll for completion.

Suno generates 2 songs (mp3) per request, each typically 30-120 seconds.

**Parameters:**
- `prompt`: Describe the music (mood, instruments, style, tempo). **Max 300 characters** — keep it concise.
- `lyrics`: Provide lyrics for vocal music (leave empty for instrumental)
- `make_instrumental`: true for instrumental-only (default), false if lyrics provided

**Important:** This tool calls a paid external API. The user will be asked for approval.
