Submit an asynchronous video generation job to a configured video provider.

Returns a job_id immediately. Use CheckVideoJob to poll for completion and download the result.

**Available providers (only these are supported):**
- `kling` — 可灵 (Kling), model: kling-video-o1
- `vidu` — Vidu (生数科技), model: viduq3-pro
- `sora` — Sora 2 (via Geneasy API)
- `apiyi` — ApiYi (SSE streaming)

Do NOT use any provider not listed above.

**Modes:**
- `text_to_video`: Generate video from a text prompt alone.
- `image_to_video`: Generate video using a reference image as the starting frame. Requires `reference_image_path`.

**Important:** This tool calls a paid external API. The user will be asked for approval before submission.
