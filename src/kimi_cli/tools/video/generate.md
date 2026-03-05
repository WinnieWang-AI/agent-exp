Submit an asynchronous video generation job to a configured video provider (e.g. Kling, Runway, Sora).

Returns a job_id immediately. Use CheckVideoJob to poll for completion and download the result.

**Modes:**
- `text_to_video`: Generate video from a text prompt alone.
- `image_to_video`: Generate video using a reference image as the starting frame. Requires `reference_image_path`.

**Important:** This tool calls a paid external API. The user will be asked for approval before submission.
