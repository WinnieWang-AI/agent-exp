Analyze one or more images using a VLM (vision-language model). Sends the images to the VLM along with your prompt, and returns the VLM's analysis as text.

Supports both single-image analysis and multi-image comparison in one call. Each image is given a label so the VLM can reference them.

Use cases:
- **Single image check**: Evaluate a reference image for white background, full body, centering, etc.
- **Multi-image comparison**: Compare a character entity reference with its appearance state to check identity consistency; compare a first frame with character references to verify likeness.

Parameters:
- `images`: A list of `{label, path}` objects. Each label identifies the image in the prompt (e.g. "entity_ref", "state_ref", "first_frame").
- `prompt`: What you want to know. Reference images by their labels. Be specific about what aspects to check.

Returns the VLM's text analysis.
