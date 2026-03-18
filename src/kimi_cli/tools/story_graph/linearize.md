Linearize a Story Graph into a shot-level execution plan for video generation.

Reads `story-graph.json` and deterministically produces a `shot-plan.json` containing:

- **Topologically sorted shots** derived from `event_sequence` and `camera_directives`. Each camera shot becomes an independent execution unit (one GenerateVideoSync call = one video file).
- **Prompt materials** for each shot: all active appearances, minds, location states, prop states, audio states, interactions, and current relationships — extracted via graph queries so the LLM does not need to cross-reference `*_active_during` maps manually.
- **Duration splitting**: shots exceeding the model's single-generation limit are split into continuation parts (`is_continuation: true`) with `prev_shot` info for tail-frame handoff.
- **Camera language**: each shot carries `shot_type`, `angle`, `movement`, `intent`, and `focus_on` from the camera directive.
- **Parallel groups** with suggested interleave order for cross-cutting.
- **Validation warnings** if any required reference images are missing.

Video specs (aspect_ratio, language) are read from the top-level `video_info` field. Visual style (style_prefix, negative_prefix) is read from `production_styles` nodes via `style_active_during`.

Input: path to `story-graph.json`.
Output: writes `shot-plan.json` next to the story graph and returns a summary.
