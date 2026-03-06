Submit an asynchronous music generation job to a configured music provider (Suno).

Returns a job_id immediately. Use CheckMusicJob to poll for completion and download the result.

Suno generates 2 songs per request. Each song is typically 30-120 seconds long.

**Parameters:**
- `prompt`: Describe the music you want (mood, instruments, tempo, etc.)
- `music_style`: Style tags like "pop, upbeat, energetic" or "cinematic, orchestral, epic"
- `lyrics`: Provide lyrics to generate a song with vocals
- `make_instrumental`: Set to true for instrumental-only music (no vocals)

**Important:** This tool calls a paid external API. The user will be asked for approval before submission.
