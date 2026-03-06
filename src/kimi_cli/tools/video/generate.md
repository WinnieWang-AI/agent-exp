Submit an asynchronous video generation job to a configured video provider.

Returns a job_id immediately. Use CheckVideoJob to poll for completion and download the result.

**Provider selection:**
- Leave `provider` empty to use the default (first configured) provider. This is recommended in most cases.
- Only specify `provider` explicitly when retrying with a different provider after a failure.
- Do NOT guess or assume which providers are available. If a provider is not configured, the call will fail.

**Modes:**
- `text_to_video`: Generate video from a text prompt alone.
- `image_to_video`: Generate video using a reference image as the starting frame. Requires `reference_image_path`.

**Important:** This tool calls a paid external API. The user will be asked for approval before submission.
