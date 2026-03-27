import json
import re
from pathlib import Path
from typing import Any, override

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.tools.story_graph.linearize import LinearizeStoryGraph
from kimi_cli.tools.story_graph.view import build_story_graph_view
from kimi_cli.tools.utils import ToolResultBuilder, load_desc

__all__ = ["ValidateStoryGraph", "LinearizeStoryGraph"]


class Params(BaseModel):
    file_path: str = Field(description="Absolute path to the story-graph JSON file to validate.")


def _collect_ids(data: dict[str, Any]) -> dict[str, set[str]]:
    """Collect all defined IDs grouped by type."""
    ids: dict[str, set[str]] = {
        "character": set(),
        "prop": set(),
        "location": set(),
        "timeline": set(),
        "event": set(),
        "character_appearance": set(),
        "prop_state": set(),
        "location_state": set(),
        "audio_state": set(),
        "camera_directive": set(),
        "production_style": set(),
    }
    for c in data.get("characters", []):
        ids["character"].add(c["id"])
    for p in data.get("props", []):
        ids["prop"].add(p["id"])
    for loc in data.get("locations", []):
        ids["location"].add(loc["id"])
    for tp in data.get("timelines", []):
        ids["timeline"].add(tp["id"])
    for e in data.get("events", []):
        ids["event"].add(e["id"])
    for a in data.get("character_appearances", []):
        ids["character_appearance"].add(a["id"])
    for ps in data.get("prop_states", []):
        ids["prop_state"].add(ps["id"])
    for ls in data.get("location_states", []):
        ids["location_state"].add(ls["id"])
    for aus in data.get("audio_states", []):
        ids["audio_state"].add(aus["id"])
    for cd in data.get("camera_directives", []):
        ids["camera_directive"].add(cd["id"])
    for ps in data.get("production_styles", []):
        ids["production_style"].add(ps["id"])
    return ids


def _all_ids(ids: dict[str, set[str]]) -> set[str]:
    result: set[str] = set()
    for s in ids.values():
        result |= s
    return result


_VALID_AUDIO_LAYERS = {"audio_bgm", "audio_dialogue"}


def _validate_references(data: dict[str, Any], ids: dict[str, set[str]]) -> list[str]:
    """Check that all cross-references point to existing IDs."""
    issues: list[str] = []
    all_ids = _all_ids(ids)
    entity_ids = ids["character"] | ids["prop"] | ids["location"]

    # audio_states: layer must be one of the supported types
    for aus in data.get("audio_states", []):
        layer = aus.get("layer", "")
        if layer not in _VALID_AUDIO_LAYERS:
            issues.append(
                f'audio_state {aus["id"]}: layer "{layer}" is not supported. '
                f"Only {sorted(_VALID_AUDIO_LAYERS)} are allowed (no audio_ambience/audio_sfx — no provider available)"
            )

    # character_appearances.entity -> character
    for a in data.get("character_appearances", []):
        if a.get("entity") not in ids["character"]:
            issues.append(f'appearance {a["id"]}: entity "{a.get("entity")}" not found in characters')
        if a.get("based_on") and a["based_on"] not in ids["character_appearance"]:
            issues.append(f'appearance {a["id"]}: based_on "{a["based_on"]}" not found')
        if a.get("based_on"):
            if not a.get("change_reason"):
                issues.append(
                    f'appearance {a["id"]}: has based_on but missing change_reason. '
                    f"Only two reasons justify a new appearance: costume change or significant body injury."
                )
            costume = a.get("visual", {}).get("costume", "")
            _SAME_COSTUME_MARKERS = ["同款", "同一套", "same", "unchanged", "不变"]
            if any(marker in costume for marker in _SAME_COSTUME_MARKERS):
                issues.append(
                    f'appearance {a["id"]}: costume "{costume}" indicates the same outfit as the base. '
                    f"A new appearance requires a different costume or significant body injury. "
                    f"Remove this node and describe other changes (posture, glow, movement) in the video prompt."
                )

    # prop_states.entity -> prop
    for ps in data.get("prop_states", []):
        if ps.get("entity") not in ids["prop"]:
            issues.append(f'prop_state {ps["id"]}: entity "{ps.get("entity")}" not found in props')
        if ps.get("based_on") and ps["based_on"] not in ids["prop_state"]:
            issues.append(f'prop_state {ps["id"]}: based_on "{ps["based_on"]}" not found')

    # location_states.entity -> location
    for ls in data.get("location_states", []):
        if ls.get("entity") not in ids["location"]:
            issues.append(f'location_state {ls["id"]}: entity "{ls.get("entity")}" not found in locations')
        if ls.get("based_on") and ls["based_on"] not in ids["location_state"]:
            issues.append(f'location_state {ls["id"]}: based_on "{ls["based_on"]}" not found')

    # events
    for e in data.get("events", []):
        if e.get("happens_at") and e["happens_at"] not in ids["location"]:
            issues.append(f'event {e["id"]}: happens_at "{e["happens_at"]}" not found')
        if e.get("happens_during") and e["happens_during"] not in ids["timeline"]:
            issues.append(f'event {e["id"]}: happens_during "{e["happens_during"]}" not found')

    # event_sequence
    for seq in data.get("event_sequence", []):
        if seq.get("from") not in ids["event"]:
            issues.append(f'event_sequence: from "{seq.get("from")}" not found')
        if seq.get("to") not in ids["event"]:
            issues.append(f'event_sequence: to "{seq.get("to")}" not found')

    # *_active_during maps
    for map_name in ["appearance_active_during", "prop_active_during",
                      "location_active_during", "audio_active_during", "style_active_during"]:
        mapping = data.get(map_name, {})
        for state_id, event_list in mapping.items():
            if state_id not in all_ids:
                issues.append(f'{map_name}: state "{state_id}" not defined')
            for evt in event_list:
                if evt not in ids["event"]:
                    issues.append(f'{map_name}[{state_id}]: event "{evt}" not found')

    # transitions
    for trans_name in ["appearance_transitions", "audio_transitions", "style_transitions"]:
        for t in data.get(trans_name, []):
            if t.get("from") not in all_ids:
                issues.append(f'{trans_name}: from "{t.get("from")}" not defined')
            if t.get("to") not in all_ids:
                issues.append(f'{trans_name}: to "{t.get("to")}" not defined')
            if t.get("trigger") and t["trigger"] not in ids["event"]:
                issues.append(f'{trans_name}: trigger "{t.get("trigger")}" not found')

    # camera_directives
    for cd in data.get("camera_directives", []):
        for_event = cd.get("for_event")
        if isinstance(for_event, str):
            for_event = [for_event]
        for evt in (for_event or []):
            if evt not in ids["event"]:
                issues.append(f'camera {cd["id"]}: for_event "{evt}" not found')
        for shot in cd.get("shots", []):
            for ref in shot.get("focus_on", []):
                if ref not in all_ids:
                    issues.append(f'camera {cd["id"]} shot {shot.get("order")}: focus_on "{ref}" not defined')

    # relationships
    for c in data.get("characters", []):
        for target, rels in c.get("relationships", {}).items():
            if target not in entity_ids:
                issues.append(f'character {c["id"]}: relationship target "{target}" not found')
            for rel in rels:
                since = rel.get("since")
                if since is not None and since not in ids["event"]:
                    issues.append(f'character {c["id"]}: relationship since "{since}" not found')
    for p in data.get("props", []):
        for target, rels in p.get("relationships", {}).items():
            if target not in entity_ids:
                issues.append(f'prop {p["id"]}: relationship target "{target}" not found')
            for rel in rels:
                since = rel.get("since")
                if since is not None and since not in ids["event"]:
                    issues.append(f'prop {p["id"]}: relationship since "{since}" not found')

    return issues


def _validate_coverage(data: dict[str, Any], ids: dict[str, set[str]]) -> list[str]:
    """Check that events have proper state coverage."""
    issues: list[str] = []

    # Check for truncated output: active_during maps reference IDs but definition arrays are empty
    appear_active = data.get("appearance_active_during", {})
    if appear_active and not data.get("character_appearances"):
        issues.append(
            "CRITICAL: appearance_active_during references IDs but character_appearances array is empty or missing. "
            "This usually means the JSON was truncated during generation. "
            "Regenerate the full story graph with all character_appearances defined."
        )

    # Build reverse maps: event -> which states are active
    loc_active = data.get("location_active_during", {})

    # event -> location_states active
    evt_loc: dict[str, list[str]] = {}
    for state_id, evts in loc_active.items():
        for e in evts:
            evt_loc.setdefault(e, []).append(state_id)

    # event -> appearances active
    evt_appear: dict[str, list[str]] = {}
    for state_id, evts in appear_active.items():
        for e in evts:
            evt_appear.setdefault(e, []).append(state_id)

    # Build appearance entity map
    appear_entity: dict[str, str] = {}
    for a in data.get("character_appearances", []):
        appear_entity[a["id"]] = a.get("entity", "")

    for e in data.get("events", []):
        eid = e["id"]

        # Every event at a location should have a location_state
        if e.get("happens_at") and eid not in evt_loc:
            issues.append(f'event {eid}: no location_state active (happens_at {e["happens_at"]})')

    # Check video_info has required fields (aspect_ratio, duration, language)
    vi = data.get("video_info")
    if vi:
        if not vi.get("aspect_ratio"):
            issues.append('video_info: missing required "aspect_ratio" field')
        if not vi.get("duration"):
            issues.append('video_info: missing required "duration" field')
        if not vi.get("language"):
            issues.append('video_info: missing required "language" field')
    else:
        # Backward compat: accept old format where these live in production_styles
        ps_list = data.get("production_styles", [])
        if ps_list and (ps_list[0].get("aspect_ratio") or ps_list[0].get("language")):
            issues.append(
                'video_info is missing. aspect_ratio/duration/language found in production_styles '
                '(old format). Move them to a top-level "video_info" object.'
            )
        else:
            issues.append('video_info: missing required top-level field')

    # Check every event has a production_style active
    style_active = data.get("style_active_during", {})
    evt_has_style: set[str] = set()
    for _sid, evts in style_active.items():
        for e in evts:
            evt_has_style.add(e)
    for e in data.get("events", []):
        if e["id"] not in evt_has_style:
            issues.append(f'event {e["id"]}: no production_style active (style_active_during)')

    # Check no state has empty active_during
    for map_name in ["appearance_active_during", "prop_active_during",
                      "location_active_during", "audio_active_during", "style_active_during"]:
        mapping = data.get(map_name, {})
        for state_id, evts in mapping.items():
            if not evts:
                issues.append(f'{map_name}[{state_id}]: active during zero events')

    return issues


def _validate_event_dag(data: dict[str, Any], ids: dict[str, set[str]]) -> list[str]:
    """Check event_sequence forms a DAG with no orphans."""
    issues: list[str] = []
    event_ids = ids["event"]
    if not event_ids:
        return issues

    # Build adjacency
    adj: dict[str, list[str]] = {eid: [] for eid in event_ids}
    in_degree: dict[str, int] = {eid: 0 for eid in event_ids}
    for seq in data.get("event_sequence", []):
        f, t = seq.get("from", ""), seq.get("to", "")
        if f in event_ids and t in event_ids:
            adj[f].append(t)
            in_degree[t] = in_degree.get(t, 0) + 1

    # Kahn's algorithm for cycle detection
    queue = [eid for eid, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited < len(event_ids):
        issues.append(f'event_sequence contains a cycle ({len(event_ids) - visited} events involved)')

    # Check for orphan events (not connected to any sequence edge)
    mentioned = set()
    for seq in data.get("event_sequence", []):
        mentioned.add(seq.get("from", ""))
        mentioned.add(seq.get("to", ""))
    orphans = event_ids - mentioned
    if orphans:
        issues.append(f'orphan events not in event_sequence: {sorted(orphans)}')

    return issues


def _validate_reference_image_placeholders(data: dict[str, Any], project_dir: str = "") -> list[str]:
    """Check that reference_image fields are either null or real existing file paths,
    and that state-level images match their owning state/entity ID."""
    issues: list[str] = []

    # Build entity_id lookup for states
    state_entity: dict[str, str] = {}
    for key in ("character_appearances", "prop_states", "location_states"):
        for node in data.get(key, []):
            state_entity[node["id"]] = node.get("entity", "")

    for key in ("characters", "props", "locations",
                "character_appearances", "prop_states", "location_states"):
        for node in data.get(key, []):
            ref = node.get("reference_image")
            if ref is None:
                continue
            nid = node["id"]
            if ref == "":
                issues.append(
                    f'{nid}: reference_image is empty string "" — must be null '
                    f"(to be filled by video-creator) or a real file path"
                )
                continue
            # Resolve relative paths against project directory
            ref_path = Path(ref)
            if not ref_path.is_absolute() and project_dir:
                ref_path = Path(project_dir) / ref
            if not ref_path.is_file():
                issues.append(
                    f'{nid}: reference_image "{ref}" does not exist on disk — '
                    f"must be null (to be filled by video-creator) or a real file path"
                )
                continue

            # Check that the image filename is plausibly related to this node.
            # The filename stem should contain the node ID or entity ID.
            stem = ref_path.stem
            entity_id = state_entity.get(nid, "")
            if stem != nid and stem != entity_id:
                issues.append(
                    f'{nid}: reference_image filename "{ref_path.name}" does not match '
                    f'node ID "{nid}" or entity ID "{entity_id}". '
                    f"This may indicate the image was assigned to the wrong node."
                )
    return issues


_TIMESTAMP_PATTERN = re.compile(r'\d+\.?\d*\s*s(?:ec)?|\d+\s*-\s*\d+\s*s')


def _validate_timelines(data: dict[str, Any], ids: dict[str, set[str]]) -> list[str]:
    """Check timeline definitions and usage."""
    issues: list[str] = []

    # Check if any event uses happens_during but timelines is missing/empty
    events_with_timeline = [
        e for e in data.get("events", []) if e.get("happens_during")
    ]
    if events_with_timeline and not ids["timeline"]:
        issues.append(
            f'timelines array is missing or empty, but {len(events_with_timeline)} event(s) '
            f'reference happens_during (e.g. "{events_with_timeline[0].get("happens_during")}"). '
            f'Add timelines definitions or remove happens_during from events.'
        )

    # Check label does not contain production timestamps (e.g. "3.5s", "0-6s")
    for tl in data.get("timelines", []):
        label = tl.get("label", "")
        if _TIMESTAMP_PATTERN.search(label):
            issues.append(
                f'timeline {tl["id"]}: label "{label}" contains production timestamps. '
                f'Timeline labels should describe narrative time (e.g. "清晨", "午后"), '
                f'not video durations or second ranges.'
            )

    return issues


def _validate_blocking(data: dict[str, Any], ids: dict[str, set[str]]) -> list[str]:
    """Check spatial continuity of blocking fields across events."""
    issues: list[str] = []
    events_by_id = {e["id"]: e for e in data.get("events", [])}

    # Build topo-sorted event order
    event_ids = ids["event"]
    if not event_ids:
        return issues

    # Check that events have blocking
    events_with_blocking = [e for e in data.get("events", []) if e.get("blocking")]
    events_without_blocking = [e for e in data.get("events", []) if not e.get("blocking")]
    if events_without_blocking and events_with_blocking:
        missing = [e["id"] for e in events_without_blocking]
        issues.append(
            f'Some events have blocking but others do not: {sorted(missing)}. '
            f'All events should have blocking for spatial continuity checking.'
        )

    if not events_with_blocking:
        return issues

    # Build continuous edges for spatial continuity checking
    continuous_edges: list[tuple[str, str]] = []
    for seq in data.get("event_sequence", []):
        if seq.get("type") == "THEN" and seq.get("continuous", False):
            f, t = seq.get("from", ""), seq.get("to", "")
            if f in events_by_id and t in events_by_id:
                continuous_edges.append((f, t))

    # Check spatial continuity across continuous edges
    for from_id, to_id in continuous_edges:
        from_evt = events_by_id[from_id]
        to_evt = events_by_id[to_id]
        from_blocking = from_evt.get("blocking", {})
        to_blocking = to_evt.get("blocking", {})

        if not from_blocking or not to_blocking:
            continue

        # For each character present in both events, check end -> start continuity
        shared_chars = set(from_blocking.keys()) & set(to_blocking.keys())
        for char_id in shared_chars:
            from_end = from_blocking[char_id].get("end", "")
            to_start = to_blocking[char_id].get("start", "")
            if not from_end or not to_start:
                issues.append(
                    f'{char_id} in continuous edge {from_id} -> {to_id}: '
                    f'missing end or start in blocking.'
                )

    # Check that blocking references valid character IDs
    char_ids = ids["character"]
    for evt in data.get("events", []):
        blocking = evt.get("blocking", {})
        for char_id in blocking:
            if char_id not in char_ids:
                issues.append(
                    f'event {evt["id"]}: blocking references unknown character {char_id}'
                )

    return issues


def validate_story_graph(data: dict[str, Any], project_dir: str = "") -> dict[str, list[str]]:
    """Run all validations and return issues grouped by category."""
    ids = _collect_ids(data)
    result: dict[str, list[str]] = {}

    ref_issues = _validate_references(data, ids)
    if ref_issues:
        result["reference_integrity"] = ref_issues

    cov_issues = _validate_coverage(data, ids)
    if cov_issues:
        result["coverage"] = cov_issues

    dag_issues = _validate_event_dag(data, ids)
    if dag_issues:
        result["event_sequence"] = dag_issues

    timeline_issues = _validate_timelines(data, ids)
    if timeline_issues:
        result["timelines"] = timeline_issues

    placeholder_issues = _validate_reference_image_placeholders(data, project_dir)
    if placeholder_issues:
        result["reference_image_placeholders"] = placeholder_issues

    blocking_issues = _validate_blocking(data, ids)
    if blocking_issues:
        result["blocking"] = blocking_issues

    synopsis = data.get("synopsis")
    if not synopsis or not isinstance(synopsis, str) or len(synopsis.strip()) < 10:
        result.setdefault("synopsis", []).append(
            "Missing or too short 'synopsis' field at top level. "
            "Write a coherent story synopsis before decomposing into events."
        )

    return result


class ValidateStoryGraph(CallableTool2[Params]):
    name: str = "ValidateStoryGraph"
    description: str = load_desc(Path(__file__).parent / "validate.md")
    params: type[Params] = Params

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()
        path = Path(params.file_path)
        if not path.exists():
            return builder.error(f"File not found: {params.file_path}", brief="File not found")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return builder.error(f"Invalid JSON: {e}", brief="JSON parse error")

        project_dir = str(path.parent)
        issues = validate_story_graph(data, project_dir)

        # Emit story graph view display block
        has_refs = any(
            c.get("reference_image")
            for c in data.get("characters", []) + data.get("locations", []) + data.get("props", [])
        )
        phase = "references" if has_refs else "skeleton"
        project_dir = str(path.parent)
        view_block = build_story_graph_view(data, phase=phase, project_dir=project_dir)
        builder.display(view_block)

        if not issues:
            builder.write("No issues found. The story graph is structurally valid.")
            return builder.ok(message="Story graph validation passed", brief="Valid")

        total = sum(len(v) for v in issues.values())
        builder.write(f"Found {total} issue(s) in {len(issues)} category(s):\n\n")
        for category, items in issues.items():
            builder.write(f"## {category} ({len(items)})\n")
            for item in items:
                builder.write(f"  - {item}\n")
            builder.write("\n")

        return builder.ok(message=f"Validation found {total} issue(s)", brief=f"{total} issues")
