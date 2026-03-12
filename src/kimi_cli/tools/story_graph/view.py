"""Build StoryGraphViewDisplayBlock from story-graph data."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from kimi_cli.tools.display import (
    StoryGraphEntity,
    StoryGraphEvent,
    StoryGraphShot,
    StoryGraphViewDisplayBlock,
)


def _extract_character_ids_for_event(
    event: dict[str, Any],
    appear_by_event: dict[str, list[str]],
    appear_entity: dict[str, str],
) -> list[str]:
    """Get character IDs involved in an event via active appearances."""
    char_ids: list[str] = []
    seen: set[str] = set()
    for appear_id in appear_by_event.get(event["id"], []):
        cid = appear_entity.get(appear_id, "")
        if cid and cid not in seen:
            seen.add(cid)
            char_ids.append(cid)
    return char_ids


def build_story_graph_view(
    data: dict[str, Any],
    *,
    phase: str = "skeleton",
    shot_plan: dict[str, Any] | None = None,
) -> StoryGraphViewDisplayBlock:
    """Build a StoryGraphViewDisplayBlock from raw story-graph data.

    Args:
        data: The parsed story-graph.json dict.
        phase: One of "skeleton", "references", "shots", "videos".
        shot_plan: Optional parsed shot-plan.json for enriching shot data.
    """
    # --- Entities ---
    entities: list[StoryGraphEntity] = []
    for c in data.get("characters", []):
        entities.append(StoryGraphEntity(
            id=c["id"],
            name=c.get("name", c["id"]),
            kind="character",
            reference_image=c.get("reference_image", ""),
        ))
    for loc in data.get("locations", []):
        entities.append(StoryGraphEntity(
            id=loc["id"],
            name=loc.get("name", loc["id"]),
            kind="location",
            reference_image=loc.get("reference_image", ""),
        ))
    for p in data.get("props", []):
        entities.append(StoryGraphEntity(
            id=p["id"],
            name=p.get("name", p["id"]),
            kind="prop",
            reference_image=p.get("reference_image", ""),
        ))

    # --- Build reverse map: event -> appearance state ids ---
    appear_by_event: dict[str, list[str]] = defaultdict(list)
    for state_id, evt_list in data.get("appearance_active_during", {}).items():
        for eid in evt_list:
            appear_by_event[eid].append(state_id)

    appear_entity: dict[str, str] = {}
    for a in data.get("character_appearances", []):
        appear_entity[a["id"]] = a.get("entity", "")

    # --- Build shot lookup from shot_plan ---
    shots_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if shot_plan:
        for s in shot_plan.get("shots", []):
            shots_by_event[s["event_id"]].append(s)

    # --- Topological event order ---
    event_ids = {e["id"] for e in data.get("events", [])}
    edges = data.get("event_sequence", [])
    adj: dict[str, list[str]] = {eid: [] for eid in event_ids}
    in_deg: dict[str, int] = {eid: 0 for eid in event_ids}
    for e in edges:
        f, t = e.get("from", ""), e.get("to", "")
        if f in adj and t in adj:
            adj[f].append(t)
            in_deg[t] = in_deg.get(t, 0) + 1
    queue = sorted(eid for eid, d in in_deg.items() if d == 0)
    sorted_event_ids: list[str] = []
    while queue:
        node = queue.pop(0)
        sorted_event_ids.append(node)
        for nb in sorted(adj[node]):
            in_deg[nb] -= 1
            if in_deg[nb] == 0:
                queue.append(nb)
    for eid in sorted(event_ids - set(sorted_event_ids)):
        sorted_event_ids.append(eid)

    events_by_id = {e["id"]: e for e in data.get("events", [])}

    # --- Timeline ---
    timeline: list[StoryGraphEvent] = []
    for eid in sorted_event_ids:
        event = events_by_id.get(eid)
        if not event:
            continue

        char_ids = _extract_character_ids_for_event(event, appear_by_event, appear_entity)

        shots: list[StoryGraphShot] = []
        for sp in shots_by_event.get(eid, []):
            techs: list[str] = []
            techniques = sp.get("techniques", {})
            if techniques.get("A_reference_images", {}).get("enabled"):
                techs.append("A")
            if techniques.get("B_first_frame", {}).get("enabled"):
                techs.append("B")
            if techniques.get("C_tail_frame", {}).get("enabled"):
                techs.append("C")
            shots.append(StoryGraphShot(
                shot_id=sp["shot_id"],
                order=sp.get("order", 0),
                shot_type=sp.get("shot_type", ""),
                intent=sp.get("intent", ""),
                focus_on=sp.get("focus_on", []),
                techniques=techs,
                video_clip=sp.get("output_path", ""),
            ))

        timeline.append(StoryGraphEvent(
            id=eid,
            description=event.get("description", ""),
            happens_at=event.get("happens_at", ""),
            character_ids=char_ids,
            shots=shots,
        ))

    # --- Parallel groups ---
    parallel_groups: list[list[str]] = []
    for e in edges:
        if e.get("type") == "PARALLEL":
            # Collect connected PARALLEL components (simple union)
            found = False
            f, t = e["from"], e["to"]
            for group in parallel_groups:
                if f in group or t in group:
                    if f not in group:
                        group.append(f)
                    if t not in group:
                        group.append(t)
                    found = True
                    break
            if not found:
                parallel_groups.append([f, t])

    # --- Summary ---
    n_chars = sum(1 for e in entities if e.kind == "character")
    n_locs = sum(1 for e in entities if e.kind == "location")
    n_props = sum(1 for e in entities if e.kind == "prop")
    n_events = len(timeline)
    n_shots = sum(len(ev.shots) for ev in timeline)
    n_with_ref = sum(1 for e in entities if e.reference_image)

    summary = {
        "characters": n_chars,
        "locations": n_locs,
        "props": n_props,
        "events": n_events,
        "shots": n_shots,
        "entities_with_reference_images": n_with_ref,
    }

    return StoryGraphViewDisplayBlock(
        phase=phase,
        entities=entities,
        timeline=timeline,
        parallel_groups=parallel_groups,
        summary=summary,
    )
