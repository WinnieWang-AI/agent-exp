Validate a Story Graph JSON for structural correctness.

Performs deterministic checks on the graph structure:
- **Reference integrity**: all IDs referenced by `entity`, `happens_at`, `happens_during`, `based_on`, `focus_on`, `for_event`, `trigger`, transition `from`/`to` actually exist.
- **Coverage**: every event has at least one location_state in `location_active_during`; every character that appears in an event's `interactions` or camera `focus_on` has a corresponding appearance + mind active during that event.
- **Transition continuity**: state chains (appearance_transitions, mind_transitions, etc.) form valid paths without gaps or dangling references.
- **Event sequence**: `event_sequence` forms a DAG (no cycles); every event in `events` is reachable from at least one other event (no orphans, except the first event).
- **active_during consistency**: states listed in `*_active_during` reference valid event IDs; no state is active during zero events.

Input: the path to a `story-graph.json` file.
Output: a list of issues found (empty if valid), grouped by category.
