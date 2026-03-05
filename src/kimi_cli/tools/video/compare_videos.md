Compare two videos using a VLM (vision-language model). Sends both videos to the VLM for side-by-side comparison and returns structured evaluation results.

Use this to evaluate how well a generated video reproduces an original reference video.

Parameters:
- `original_path`: Path to the original reference video.
- `generated_path`: Path to the generated video to evaluate.
- `criteria`: Optional evaluation focus. Defaults to a comprehensive comparison across composition, color, motion, timing, and content fidelity.

Returns a structured comparison with per-dimension scores (1-10) and specific feedback.