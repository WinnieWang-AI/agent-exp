Check the status of a music generation job and optionally download completed audio files.

Suno generates 2 songs per request. When the job is completed, song details (title, duration, lyrics) are returned.

Use `download_dir` to automatically download all completed songs to a directory.

**States:**
- `pending`: Job is queued
- `processing`: Music is being generated
- `completed`: Songs are ready for download
- `failed`: Generation failed (check error_message)
