import json
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
        "character_mind": set(),
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
    for m in data.get("character_minds", []):
        ids["character_mind"].add(m["id"])
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


def _validate_references(data: dict[str, Any], ids: dict[str, set[str]]) -> list[str]:
    """Check that all cross-references point to existing IDs."""
    issues: list[str] = []
    all_ids = _all_ids(ids)
    entity_ids = ids["character"] | ids["prop"] | ids["location"]

    # character_appearances.entity -> character
    for a in data.get("character_appearances", []):
        if a.get("entity") not in ids["character"]:
            issues.append(f'appearance {a["id"]}: entity "{a.get("entity")}" not found in characters')
        if a.get("based_on") and a["based_on"] not in ids["character_appearance"]:
            issues.append(f'appearance {a["id"]}: based_on "{a["based_on"]}" not found')

    # character_minds.entity -> character
    for m in data.get("character_minds", []):
        if m.get("entity") not in ids["character"]:
            issues.append(f'mind {m["id"]}: entity "{m.get("entity")}" not found in characters')

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
    for map_name in ["appearance_active_during", "mind_active_during", "prop_active_during",
                      "location_active_during", "audio_active_during", "style_active_during"]:
        mapping = data.get(map_name, {})
        for state_id, event_list in mapping.items():
            if state_id not in all_ids:
                issues.append(f'{map_name}: state "{state_id}" not defined')
            for evt in event_list:
                if evt not in ids["event"]:
                    issues.append(f'{map_name}[{state_id}]: event "{evt}" not found')

    # transitions
    for trans_name in ["appearance_transitions", "mind_transitions", "audio_transitions", "style_transitions"]:
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
    mind_active = data.get("mind_active_during", {})
    if appear_active and not data.get("character_appearances"):
        issues.append(
            "CRITICAL: appearance_active_during references IDs but character_appearances array is empty or missing. "
            "This usually means the JSON was truncated during generation. "
            "Regenerate the full story graph with all character_appearances defined."
        )
    if mind_active and not data.get("character_minds"):
        issues.append(
            "CRITICAL: mind_active_during references IDs but character_minds array is empty or missing. "
            "This usually means the JSON was truncated during generation. "
            "Regenerate the full story graph with all character_minds defined."
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

    # event -> minds active
    evt_mind: dict[str, list[str]] = {}
    for state_id, evts in mind_active.items():
        for e in evts:
            evt_mind.setdefault(e, []).append(state_id)

    # Build appearance entity map
    appear_entity: dict[str, str] = {}
    for a in data.get("character_appearances", []):
        appear_entity[a["id"]] = a.get("entity", "")
    mind_entity: dict[str, str] = {}
    for m in data.get("character_minds", []):
        mind_entity[m["id"]] = m.get("entity", "")

    for e in data.get("events", []):
        eid = e["id"]

        # Every event at a location should have a location_state
        if e.get("happens_at") and eid not in evt_loc:
            issues.append(f'event {eid}: no location_state active (happens_at {e["happens_at"]})')

        # Characters in interactions should have appearance + mind
        for inter in e.get("interactions", []):
            for char_id in inter.get("between", []):
                if char_id not in ids["character"]:
                    continue
                # Check appearance
                has_appear = any(
                    appear_entity.get(aid) == char_id
                    for aid in evt_appear.get(eid, [])
                )
                if not has_appear:
                    issues.append(f'event {eid}: character {char_id} in interactions but no appearance active')
                # Check mind
                has_mind = any(
                    mind_entity.get(mid) == char_id
                    for mid in evt_mind.get(eid, [])
                )
                if not has_mind:
                    issues.append(f'event {eid}: character {char_id} in interactions but no mind active')

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
    for map_name in ["appearance_active_during", "mind_active_during", "prop_active_during",
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
    """Check that reference_image fields are either null or real existing file paths."""
    issues: list[str] = []
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

    placeholder_issues = _validate_reference_image_placeholders(data, project_dir)
    if placeholder_issues:
        result["reference_image_placeholders"] = placeholder_issues

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
