Validate a Story Graph JSON for structural correctness.

Performs deterministic checks on the graph structure:
- **Reference integrity**: all IDs referenced by `entity`, `happens_at`, `happens_during`, `based_on`, `focus_on`, `for_event`, `trigger`, transition `from`/`to` actually exist.
- **Coverage**: every event has at least one location_state in `location_active_during`; every character that appears in a camera `focus_on` has a corresponding appearance active during that event.
- **Transition continuity**: state chains (appearance_transitions, etc.) form valid paths without gaps or dangling references.
- **Event sequence**: `event_sequence` forms a DAG (no cycles); every event in `events` is reachable from at least one other event (no orphans, except the first event).
- **Timelines**: `timelines` array must exist and be non-empty if any event uses `happens_during`; timeline labels must describe narrative time (e.g. "清晨", "午后"), not contain production timestamps (e.g. "3.5s", "0-6s").
- **active_during consistency**: states listed in `*_active_during` reference valid event IDs; no state is active during zero events.
- **Blocking**: all character IDs in `blocking` exist in `characters`; for `continuous: true` edges, shared characters have non-empty `end`/`start`; all events either have or lack blocking consistently.
- **Location framing**: `framing.visible_regions` references valid `spatial_layout.regions`; visible regions are spatially adjacent (connected); `blocking.region` exists in `spatial_layout.regions` and falls within the active LocationState's `framing.visible_regions`; character movement paths within a location follow `connections`.

Input: the path to a `story-graph.json` file.
Output: a list of issues found (empty if valid), grouped by category.
