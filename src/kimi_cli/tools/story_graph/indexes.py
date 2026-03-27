"""Build three-dimensional index views over a story graph.

Provides O(1) lookups along any of the three dimensions:
- **event_view**: given an event → who is where, which location state
- **character_view**: given a character → full trajectory across events and locations
- **location_view**: given a location → all events, visitors, region usage, states

These views are computed on demand from the normalized story-graph.json
and are never persisted. Consumers (validation, linearization, etc.)
call ``build_indexes(data)`` and query the result.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


# ---------------------------------------------------------------------------
# Topological sort (shared utility)
# ---------------------------------------------------------------------------

def _topological_sort(event_ids: set[str], edges: list[dict[str, Any]]) -> list[str]:
    """Kahn's algorithm. Returns events in execution order."""
    adj: dict[str, list[str]] = {eid: [] for eid in event_ids}
    in_deg: dict[str, int] = {eid: 0 for eid in event_ids}
    for e in edges:
        f, t = e.get("from", ""), e.get("to", "")
        if f in adj and t in adj:
            adj[f].append(t)
            in_deg[t] = in_deg.get(t, 0) + 1
    queue = sorted(eid for eid, d in in_deg.items() if d == 0)
    result: list[str] = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for nb in sorted(adj[node]):
            in_deg[nb] -= 1
            if in_deg[nb] == 0:
                queue.append(nb)
    for eid in sorted(event_ids - set(result)):
        result.append(eid)
    return result


# ---------------------------------------------------------------------------
# Data classes for index entries
# ---------------------------------------------------------------------------

class EventEntry:
    """A single event's spatial context."""

    __slots__ = (
        "event_id", "location", "location_state_id", "framing",
        "characters",
    )

    def __init__(
        self,
        event_id: str,
        location: str,
        location_state_id: str,
        framing: dict[str, Any],
        characters: dict[str, dict[str, Any]],
    ) -> None:
        self.event_id = event_id
        self.location = location
        self.location_state_id = location_state_id
        self.framing = framing  # {"visible_regions": [...], "viewpoint": ..., "excluded_elements": [...]}
        self.characters = characters  # char_id -> {"region": ..., "start": ..., "end": ...}


class TrajectoryPoint:
    """One point in a character's spatial trajectory."""

    __slots__ = ("event_id", "location", "region", "start", "end")

    def __init__(
        self,
        event_id: str,
        location: str,
        region: str,
        start: str,
        end: str,
    ) -> None:
        self.event_id = event_id
        self.location = location
        self.region = region
        self.start = start
        self.end = end


class CharacterEntry:
    """A character's full trajectory and location changes."""

    __slots__ = ("character_id", "trajectory", "location_changes")

    def __init__(
        self,
        character_id: str,
        trajectory: list[TrajectoryPoint],
        location_changes: list[dict[str, Any]],
    ) -> None:
        self.character_id = character_id
        self.trajectory = trajectory
        self.location_changes = location_changes


class LocationEntry:
    """A location's complete usage across the story."""

    __slots__ = (
        "location_id", "spatial_layout", "events_here", "visitors",
        "region_usage", "states_used",
    )

    def __init__(
        self,
        location_id: str,
        spatial_layout: dict[str, Any],
        events_here: list[str],
        visitors: dict[str, list[str]],
        region_usage: dict[str, list[str]],
        states_used: dict[str, dict[str, Any]],
    ) -> None:
        self.location_id = location_id
        self.spatial_layout = spatial_layout
        self.events_here = events_here
        self.visitors = visitors  # char_id -> [event_ids]
        self.region_usage = region_usage  # region_name -> [event_ids]
        self.states_used = states_used  # lstate_id -> {"visible_regions": [...], "events": [...]}


class StoryGraphIndexes:
    """Three-dimensional index views over a story graph."""

    __slots__ = ("event_view", "character_view", "location_view", "event_order")

    def __init__(
        self,
        event_view: dict[str, EventEntry],
        character_view: dict[str, CharacterEntry],
        location_view: dict[str, LocationEntry],
        event_order: list[str],
    ) -> None:
        self.event_view = event_view
        self.character_view = character_view
        self.location_view = location_view
        self.event_order = event_order


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_indexes(data: dict[str, Any]) -> StoryGraphIndexes:
    """Build three-dimensional indexes from a story-graph dict.

    Returns a ``StoryGraphIndexes`` with event, character, and location views.
    """
    # --- Pre-compute node lookups ---
    events_by_id: dict[str, dict[str, Any]] = {
        e["id"]: e for e in data.get("events", [])
    }
    locations_by_id: dict[str, dict[str, Any]] = {
        loc["id"]: loc for loc in data.get("locations", [])
    }
    lstate_by_id: dict[str, dict[str, Any]] = {
        ls["id"]: ls for ls in data.get("location_states", [])
    }

    # Reverse map: event_id -> location_state_id
    evt_to_lstate: dict[str, str] = {}
    for lstate_id, evt_list in data.get("location_active_during", {}).items():
        for eid in evt_list:
            evt_to_lstate[eid] = lstate_id

    # Reverse map: event_id -> [appearance_ids] for character detection
    appear_entity: dict[str, str] = {}
    for a in data.get("character_appearances", []):
        appear_entity[a["id"]] = a.get("entity", "")
    evt_to_chars: dict[str, set[str]] = defaultdict(set)
    for appear_id, evt_list in data.get("appearance_active_during", {}).items():
        char_id = appear_entity.get(appear_id, "")
        if char_id:
            for eid in evt_list:
                evt_to_chars[eid].add(char_id)

    # Topological order
    event_ids = set(events_by_id.keys())
    edges = data.get("event_sequence", [])
    sorted_events = _topological_sort(event_ids, edges)

    # -----------------------------------------------------------------------
    # Build event_view
    # -----------------------------------------------------------------------
    event_view: dict[str, EventEntry] = {}
    for eid in sorted_events:
        event = events_by_id.get(eid)
        if not event:
            continue

        loc_id = event.get("happens_at", "")
        lstate_id = evt_to_lstate.get(eid, "")
        lstate = lstate_by_id.get(lstate_id, {})
        framing = lstate.get("framing", {})

        # Extract blocking with region
        characters: dict[str, dict[str, Any]] = {}
        for char_id, bdata in event.get("blocking", {}).items():
            if isinstance(bdata, dict):
                characters[char_id] = {
                    "region": bdata.get("region", ""),
                    "start": bdata.get("start", ""),
                    "action": bdata.get("action", ""),
                    "end": bdata.get("end", ""),
                }

        event_view[eid] = EventEntry(
            event_id=eid,
            location=loc_id,
            location_state_id=lstate_id,
            framing=framing,
            characters=characters,
        )

    # -----------------------------------------------------------------------
    # Build character_view
    # -----------------------------------------------------------------------
    character_view: dict[str, CharacterEntry] = {}

    # Collect trajectory points per character in topo order
    char_points: dict[str, list[TrajectoryPoint]] = defaultdict(list)
    for eid in sorted_events:
        event = events_by_id.get(eid)
        if not event:
            continue
        loc_id = event.get("happens_at", "")
        for char_id, bdata in event.get("blocking", {}).items():
            if isinstance(bdata, dict):
                char_points[char_id].append(TrajectoryPoint(
                    event_id=eid,
                    location=loc_id,
                    region=bdata.get("region", ""),
                    start=bdata.get("start", ""),
                    end=bdata.get("end", ""),
                ))

    # Also include characters from appearance_active_during who may not have blocking
    for eid in sorted_events:
        event = events_by_id.get(eid)
        if not event:
            continue
        loc_id = event.get("happens_at", "")
        blocking_chars = set(event.get("blocking", {}).keys())
        for char_id in evt_to_chars.get(eid, set()):
            if char_id not in blocking_chars:
                char_points[char_id].append(TrajectoryPoint(
                    event_id=eid,
                    location=loc_id,
                    region="",
                    start="",
                    end="",
                ))

    for char_id, points in char_points.items():
        # Compute location/region changes
        changes: list[dict[str, Any]] = []
        for i in range(1, len(points)):
            prev, curr = points[i - 1], points[i]
            if prev.location != curr.location or prev.region != curr.region:
                changes.append({
                    "from_event": prev.event_id,
                    "to_event": curr.event_id,
                    "from_location": prev.location,
                    "to_location": curr.location,
                    "from_region": prev.region,
                    "to_region": curr.region,
                    "same_location": prev.location == curr.location,
                })

        character_view[char_id] = CharacterEntry(
            character_id=char_id,
            trajectory=points,
            location_changes=changes,
        )

    # -----------------------------------------------------------------------
    # Build location_view
    # -----------------------------------------------------------------------
    location_view: dict[str, LocationEntry] = {}

    # Group events by location
    loc_events: dict[str, list[str]] = defaultdict(list)
    loc_visitors: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    loc_region_usage: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    loc_states: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    for eid in sorted_events:
        event = events_by_id.get(eid)
        if not event:
            continue
        loc_id = event.get("happens_at", "")
        if not loc_id:
            continue

        loc_events[loc_id].append(eid)

        # Visitors from blocking
        for char_id, bdata in event.get("blocking", {}).items():
            loc_visitors[loc_id][char_id].append(eid)
            if isinstance(bdata, dict):
                region = bdata.get("region", "")
                if region:
                    loc_region_usage[loc_id][region].append(eid)

        # Also visitors from appearance_active_during
        blocking_chars = set(event.get("blocking", {}).keys())
        for char_id in evt_to_chars.get(eid, set()):
            if char_id not in blocking_chars:
                loc_visitors[loc_id][char_id].append(eid)

    # States used per location
    for lstate_id, lstate in lstate_by_id.items():
        loc_id = lstate.get("entity", "")
        if not loc_id:
            continue
        framing = lstate.get("framing", {})
        visible_regions = framing.get("visible_regions", [])
        # Find events using this state
        state_events = data.get("location_active_during", {}).get(lstate_id, [])
        loc_states[loc_id][lstate_id] = {
            "visible_regions": visible_regions,
            "events": state_events,
        }

    for loc_id, loc in locations_by_id.items():
        location_view[loc_id] = LocationEntry(
            location_id=loc_id,
            spatial_layout=loc.get("spatial_layout", {}),
            events_here=loc_events.get(loc_id, []),
            visitors=dict(loc_visitors.get(loc_id, {})),
            region_usage=dict(loc_region_usage.get(loc_id, {})),
            states_used=loc_states.get(loc_id, {}),
        )

    return StoryGraphIndexes(
        event_view=event_view,
        character_view=character_view,
        location_view=location_view,
        event_order=sorted_events,
    )
