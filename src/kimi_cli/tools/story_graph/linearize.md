Linearize a Story Graph into a shot-by-shot execution plan for video generation.

Reads `story-graph.json` and deterministically produces a `shot-plan.json` containing:

- **Topologically sorted shots** derived from `event_sequence` and `camera_directives`.
- **Prompt materials** for each shot: all active appearances, minds, location states, prop states, audio states, interactions, and current relationships — extracted via graph queries so the LLM does not need to cross-reference `*_active_during` maps manually.
- **Consistency techniques** automatically derived from graph structure:
  - **Technique A (reference images)**: collected from `focus_on` state nodes + their parent entity nodes, sorted by priority, capped at 4.
  - **Technique B (first-frame generation)**: enabled when `shot_type` is close-up/extreme_close/over_shoulder, or when `focus_on` contains 2+ character appearances.
  - **Technique C (tail-frame continuity)**: enabled when the previous shot shares the same location (same event or consecutive same-location events).
- **Recommended GenerateVideo call parameters** pre-filled for each shot.
- **Parallel groups** with suggested interleave order for cross-cutting.
- **Validation warnings** if any required reference images are missing.

Style information (style_prefix, negative_prefix, aspect_ratio) is read from `production_styles` nodes in the story graph via `style_active_during`.

Input: path to `story-graph.json`.
Output: writes `shot-plan.json` next to the story graph and returns a summary.
