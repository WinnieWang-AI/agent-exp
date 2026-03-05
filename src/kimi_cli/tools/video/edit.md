Perform structured video editing operations using FFmpeg.

**Operations:**

- `concat`: Concatenate multiple video clips into one. Requires at least 2 input files.
- `trim`: Trim a video to a specific time range using start_time and end_time (in seconds).
- `add_audio`: Replace or add audio track to a video. Requires audio_path.
- `add_subtitles`: Burn subtitles into a video. Requires subtitle_path (SRT format).
- `transition`: Apply a crossfade transition between two video clips. Supports transition_type (e.g. "fade", "wipeleft", "slideright") and transition_duration.

Each operation executes an FFmpeg command and requires user approval.
