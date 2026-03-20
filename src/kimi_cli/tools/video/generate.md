Submit an asynchronous video generation job to a configured video provider.

Returns a job_id immediately. Use CheckVideoJob to poll for completion and download the result.

**Provider selection:**
- Leave `provider` empty to use the default (first configured) provider. This is recommended in most cases.
- Only specify `provider` explicitly when retrying with a different provider after a failure.
- Do NOT guess or assume which providers are available. If a provider is not configured, the call will fail.

**Modes:**
- `text_to_video`: Generate video from a text prompt alone. No images of any kind.
- `reference_to_video`: Generate video with reference images for character/scene consistency. Uses `reference_images` (referenced in prompt as `<<<image_1>>>`, `<<<image_2>>>`, etc.).
- `image_to_video`: Generate video using a starting frame image. Requires `reference_image_path`. Can also use `reference_images` for additional consistency.

**Important:** This tool calls a paid external API. The user will be asked for approval before submission.
