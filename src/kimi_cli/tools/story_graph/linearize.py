"""Linearize a Story Graph into a shot-level execution plan.

Produces one entry per camera shot — the atomic unit of video generation.
Each shot carries a material inventory (reference images, prompt materials,
camera language) so the agent can decide generation strategy independently.

Tail-frame continuity is only used when a single shot is split into multiple
generations due to duration limits.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, override

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.tools.story_graph.view import build_story_graph_view
from kimi_cli.tools.utils import ToolResultBuilder, load_desc


# ---------------------------------------------------------------------------
# Pydantic params
# ---------------------------------------------------------------------------

class Params(BaseModel):
    story_graph_path: str = Field(description="Absolute path to the story-graph.json file.")
    output_path: str = Field(
        default="",
        description="Absolute path for the output shot-plan.json. Defaults to shot-plan.json next to the story graph.",
    )


# ---------------------------------------------------------------------------
# Graph indexing helpers
# ---------------------------------------------------------------------------

class _GraphIndex:
    """Pre-computed indexes over a raw story-graph dict for fast lookups."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

        # Global video specs (top-level)
        vi = data.get("video_info")
        if vi:
            self.video_info: dict[str, str] = {
                "aspect_ratio": vi.get("aspect_ratio", ""),
                "duration": vi.get("duration", ""),
                "language": vi.get("language", ""),
            }
        else:
            # Backward compat: fall back to production_styles[0]
            ps0 = (data.get("production_styles") or [{}])[0] if data.get("production_styles") else {}
            self.video_info = {
                "aspect_ratio": ps0.get("aspect_ratio", ""),
                "duration": ps0.get("duration", ""),
                "language": ps0.get("language", ""),
            }

        # Entity / state lookups by id
        self.nodes: dict[str, dict[str, Any]] = {}
        for key in (
            "characters", "props", "locations",
            "character_appearances", "character_minds",
            "prop_states", "location_states", "audio_states",
            "camera_directives", "production_styles",
        ):
            for node in data.get(key, []):
                self.nodes[node["id"]] = node

        # event by id
        self.events: dict[str, dict[str, Any]] = {}
        for e in data.get("events", []):
            self.events[e["id"]] = e

        # camera_directive by event_id (one directive may cover multiple events)
        self.cam_by_event: dict[str, dict[str, Any]] = {}
        for cd in data.get("camera_directives", []):
            for_event = cd.get("for_event", [])
            if isinstance(for_event, str):
                for_event = [for_event]
            for eid in for_event:
                self.cam_by_event[eid] = cd

        # Reverse maps: event_id -> list[state_id] for each active_during category
        self.active_states: dict[str, dict[str, list[str]]] = {}
        for map_name in (
            "appearance_active_during", "mind_active_during",
            "prop_active_during", "location_active_during",
            "audio_active_during", "style_active_during",
        ):
            rev: dict[str, list[str]] = defaultdict(list)
            for state_id, evt_list in data.get(map_name, {}).items():
                for eid in evt_list:
                    rev[eid].append(state_id)
            self.active_states[map_name] = dict(rev)

        # event_sequence edges
        self.event_sequence: list[dict[str, str]] = data.get("event_sequence", [])

    # --- convenience accessors ---

    def get_active(self, map_name: str, event_id: str) -> list[dict[str, Any]]:
        """Return full node dicts for states active during *event_id*."""
        ids = self.active_states.get(map_name, {}).get(event_id, [])
        return [self.nodes[sid] for sid in ids if sid in self.nodes]

    def entity_of(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Return the parent entity node for a state node."""
        eid = state.get("entity", "")
        return self.nodes.get(eid) or self.events.get(eid)

    def current_relationship(self, char: dict[str, Any], target_id: str, event_id: str) -> str | None:
        """Get the relationship kind between *char* and *target_id* at *event_id*."""
        rels = char.get("relationships", {}).get(target_id, [])
        if not rels:
            return None
        result = rels[0].get("kind")
        for rel in rels:
            since = rel.get("since")
            if since is None:
                result = rel["kind"]
            elif since in self._event_order and event_id in self._event_order:
                if self._event_order[since] <= self._event_order[event_id]:
                    result = rel["kind"]
        return result

    _event_order: dict[str, int] = {}

    def set_event_order(self, order: dict[str, int]) -> None:
        self._event_order = order

    def get_style_for_event(self, event_id: str) -> dict[str, str]:
        """Return the visual style active during *event_id*."""
        style_nodes = self.get_active("style_active_during", event_id)
        if style_nodes:
            s = style_nodes[0]
            return {
                "style_prefix": s.get("style_prefix", ""),
                "negative_prefix": s.get("negative_prefix", ""),
                "description": s.get("description", ""),
            }
        return {"style_prefix": "", "negative_prefix": "", "description": ""}


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------

def _topological_sort(event_ids: set[str], edges: list[dict[str, str]]) -> list[str]:
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
    # Append any unreachable events at the end
    for eid in sorted(event_ids - set(result)):
        result.append(eid)
    return result


# ---------------------------------------------------------------------------
# Parallel group detection
# ---------------------------------------------------------------------------

def _find_parallel_groups(edges: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Identify groups of events connected by PARALLEL edges."""
    from collections import deque

    parallel_adj: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e.get("type") == "PARALLEL":
            parallel_adj[e["from"]].add(e["to"])
            parallel_adj[e["to"]].add(e["from"])

    if not parallel_adj:
        return []

    visited: set[str] = set()
    groups: list[dict[str, Any]] = []
    for start in parallel_adj:
        if start in visited:
            continue
        # BFS to find connected component
        component: list[str] = []
        q: deque[str] = deque([start])
        while q:
            node = q.popleft()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for nb in parallel_adj[node]:
                if nb not in visited:
                    q.append(nb)
        if len(component) >= 2:
            groups.append({
                "events": sorted(component),
                "interleave_order": _build_interleave_order(sorted(component)),
            })
    return groups


def _build_interleave_order(events: list[str]) -> list[str]:
    """Build a default interleave order for cross-cutting parallel events."""
    if len(events) <= 1:
        return events
    # Simple A-B-A-B pattern
    order: list[str] = []
    for i in range(max(len(events), 3)):
        order.append(events[i % len(events)])
    return order


# ---------------------------------------------------------------------------
# Prompt material extraction
# ---------------------------------------------------------------------------

def _extract_prompt_materials(
    event: dict[str, Any],
    g: _GraphIndex,
) -> dict[str, Any]:
    """Extract all prompt-relevant information for an event from the graph.

    Each state node includes its own ``reference_image`` and its parent
    entity's ``entity_reference_image`` so the agent can decide which
    images to use without additional lookups.
    """
    event_id = event["id"]

    # Read style from ProductionStyle nodes in the graph
    effective_style = g.get_style_for_event(event_id)

    # Active appearances — with reference images
    appearances = []
    for a in g.get_active("appearance_active_during", event_id):
        entity = g.entity_of(a)
        appearances.append({
            "id": a["id"],
            "entity": a.get("entity", ""),
            "phase": a.get("phase", ""),
            "visual": a.get("visual", {}),
            "reference_image": a.get("reference_image") or "",
            "entity_reference_image": (entity.get("reference_image") or "") if entity else "",
        })

    # Active minds
    minds = []
    for m in g.get_active("mind_active_during", event_id):
        minds.append({
            "id": m["id"],
            "entity": m.get("entity", ""),
            "phase": m.get("phase", ""),
            "emotion": m.get("emotion", ""),
            "behavior": m.get("behavior", ""),
        })

    # Location state — with reference image
    location_state = None
    for ls in g.get_active("location_active_during", event_id):
        entity = g.entity_of(ls)
        location_state = {
            "id": ls["id"],
            "entity": ls.get("entity", ""),
            "phase": ls.get("phase", ""),
            "appearance": ls.get("appearance", {}),
            "reference_image": ls.get("reference_image") or "",
            "entity_reference_image": (entity.get("reference_image") or "") if entity else "",
        }
        break  # typically one location state per event

    # Prop states — with reference images
    prop_states = []
    for ps in g.get_active("prop_active_during", event_id):
        entity = g.entity_of(ps)
        prop_states.append({
            "id": ps["id"],
            "entity": ps.get("entity", ""),
            "phase": ps.get("phase", ""),
            "appearance": ps.get("appearance", {}),
            "reference_image": ps.get("reference_image") or "",
            "entity_reference_image": (entity.get("reference_image") or "") if entity else "",
        })

    # Audio states
    audio_states = []
    for aus in g.get_active("audio_active_during", event_id):
        audio_states.append({
            "id": aus["id"],
            "layer": aus.get("layer", ""),
            "phase": aus.get("phase", ""),
            "style": aus.get("style", ""),
        })

    # Interactions
    interactions = event.get("interactions", [])

    # Current relationships between interacting characters
    relationships = []
    for inter in interactions:
        chars = inter.get("between", [])
        if len(chars) >= 2:
            for i in range(len(chars)):
                for j in range(i + 1, len(chars)):
                    c1 = g.nodes.get(chars[i])
                    if c1:
                        kind = g.current_relationship(c1, chars[j], event_id)
                        if kind:
                            relationships.append({
                                "pair": [chars[i], chars[j]],
                                "current_kind": kind,
                            })

    return {
        "style_prefix": effective_style.get("style_prefix", ""),
        "negative_prefix": effective_style.get("negative_prefix", ""),
        "aspect_ratio": g.video_info.get("aspect_ratio", ""),
        "language": g.video_info.get("language", ""),
        "event_description": event.get("description", ""),
        "happens_at": event.get("happens_at", ""),
        "happens_during": event.get("happens_during", ""),
        "appearances": appearances,
        "minds": minds,
        "location_state": location_state,
        "prop_states": prop_states,
        "audio_states": audio_states,
        "interactions": interactions,
        "relationships": relationships,
    }


# ---------------------------------------------------------------------------
# Duration helpers
# ---------------------------------------------------------------------------

MAX_SHOT_DURATION = 10.0  # model single-generation limit in seconds


def _parse_duration(raw: Any, default: float = 5.0) -> float:
    """Parse a duration value (number or string like '5s') into float seconds."""
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw.replace("s", "").replace("sec", "").strip())
        except ValueError:
            return default
    return default


# ---------------------------------------------------------------------------
# Main linearization
# ---------------------------------------------------------------------------

def linearize(data: dict[str, Any]) -> dict[str, Any]:
    """Linearize a story graph into a shot-level execution plan.

    Each shot from ``camera_directives`` becomes an independent execution
    unit.  If a single shot exceeds *MAX_SHOT_DURATION* it is split into
    continuation parts that require tail-frame handoff.
    """
    g = _GraphIndex(data)

    # Topological sort
    event_ids = set(g.events.keys())
    sorted_events = _topological_sort(event_ids, g.event_sequence)
    event_order = {eid: i for i, eid in enumerate(sorted_events)}
    g.set_event_order(event_order)

    # Parallel groups
    parallel_groups = _find_parallel_groups(g.event_sequence)

    # Build shots — one entry per camera shot (or per duration-split part)
    shots: list[dict[str, Any]] = []
    warnings: list[str] = []

    for event_id in sorted_events:
        event = g.events.get(event_id)
        if not event:
            continue

        cam = g.cam_by_event.get(event_id)
        if not cam:
            warnings.append(f"event {event_id}: no camera_directive found, skipping")
            continue

        cam_shots = sorted(cam.get("shots", []), key=lambda s: s.get("order", 0))

        # Extract prompt materials once per event (shared by all shots)
        materials = _extract_prompt_materials(event, g)

        for cam_shot in cam_shots:
            shot_order = cam_shot.get("order", 1)
            shot_id = f"{event_id}_shot_{shot_order}"
            duration = _parse_duration(cam_shot.get("duration"), default=5.0)

            focus_on = cam_shot.get("focus_on", [])

            # Warn about missing reference images
            for sid in focus_on:
                node = g.nodes.get(sid)
                if node and not node.get("reference_image") and not sid.startswith("mind_"):
                    warnings.append(f"{shot_id}: focus_on '{sid}' has no reference_image")

            base_entry = {
                "event_id": event_id,
                "camera_directive_id": cam["id"],
                "order": shot_order,
                "shot_type": cam_shot.get("shot_type", ""),
                "angle": cam_shot.get("angle", ""),
                "movement": cam_shot.get("movement", ""),
                "intent": cam_shot.get("intent", ""),
                "focus_on": focus_on,
                "prompt_materials": materials,
            }

            if duration <= MAX_SHOT_DURATION:
                # Single generation
                shots.append({
                    **base_entry,
                    "shot_id": shot_id,
                    "output_path": f"assets/shots/{shot_id}.mp4",
                    "duration_seconds": duration,
                    "is_continuation": False,
                    "prev_shot": None,
                })
            else:
                # Split into continuation parts (tail-frame handoff)
                n_parts = math.ceil(duration / MAX_SHOT_DURATION)
                part_duration = round(duration / n_parts, 1)
                prev_part_info: dict[str, Any] | None = None

                for part_idx in range(n_parts):
                    part_id = f"{shot_id}_part_{part_idx + 1}"
                    part_output = f"assets/shots/{part_id}.mp4"
                    is_continuation = part_idx > 0

                    shots.append({
                        **base_entry,
                        "shot_id": part_id,
                        "output_path": part_output,
                        "duration_seconds": part_duration,
                        "is_continuation": is_continuation,
                        "prev_shot": prev_part_info,
                    })

                    prev_part_info = {
                        "shot_id": part_id,
                        "event_id": event_id,
                        "output_path": part_output,
                    }

    plan = {
        "shots": shots,
        "parallel_groups": parallel_groups,
        "total_shots": len(shots),
        "warnings": warnings,
    }
    return plan


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------

class LinearizeStoryGraph(CallableTool2[Params]):
    name: str = "LinearizeStoryGraph"
    description: str = load_desc(Path(__file__).parent / "linearize.md")
    params: type[Params] = Params

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()
        sg_path = Path(params.story_graph_path)

        if not sg_path.exists():
            return builder.error(f"File not found: {params.story_graph_path}", brief="File not found")

        try:
            data = json.loads(sg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return builder.error(f"Invalid JSON: {e}", brief="JSON parse error")

        # Linearize
        plan = linearize(data)

        # Write output
        sg_dir = sg_path.parent
        out_path_str = params.output_path or str(sg_dir / "shot-plan.json")
        out_path = Path(out_path_str)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

        # Emit story graph view display block
        project_dir = str(sg_path.parent)
        view_block = build_story_graph_view(data, phase="shots", shot_plan=plan, project_dir=project_dir)
        builder.display(view_block)

        # Summary
        n_shots = plan["total_shots"]
        n_warnings = len(plan["warnings"])
        n_parallel = len(plan["parallel_groups"])

        # Reference image coverage
        n_shots_with_refs = 0
        n_total_refs = 0
        for s in plan["shots"]:
            pm = s["prompt_materials"]
            refs = [a for a in pm.get("appearances", []) if a.get("reference_image")]
            if pm.get("location_state") and pm["location_state"].get("reference_image"):
                refs.append(pm["location_state"])
            refs.extend(p for p in pm.get("prop_states", []) if p.get("reference_image"))
            if refs:
                n_shots_with_refs += 1
            n_total_refs += len(refs)

        builder.write(f"Shot plan generated: {n_shots} shots\n\n")
        builder.write(f"Reference image coverage: {n_shots_with_refs}/{n_shots} shots have reference images ({n_total_refs} total)\n")
        if n_parallel:
            builder.write(f"\nParallel groups: {n_parallel}\n")
            for pg in plan["parallel_groups"]:
                builder.write(f"  {pg['events']} -> interleave: {pg['interleave_order']}\n")
        if n_warnings:
            builder.write(f"\nWarnings ({n_warnings}):\n")
            for w in plan["warnings"]:
                builder.write(f"  - {w}\n")

        builder.write(f"\nOutput: {out_path_str}\n")

        brief = f"{n_shots} shots"
        if n_warnings:
            brief += f", {n_warnings} warnings"
        return builder.ok(message=f"Shot plan with {n_shots} shots written to {out_path_str}", brief=brief)
