"""Linearize a Story Graph into a deterministic shot-by-shot execution plan."""

from __future__ import annotations

import json
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
        # Find the last entry whose `since` is <= event_id in topological order.
        # We use a simple heuristic: take the last entry whose `since` is None
        # or whose `since` appears before event_id in _topo_order.
        # _topo_order is set externally after topological sort.
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
        """Return the production style active during *event_id*.

        Returns a dict with keys: style_prefix, negative_prefix, aspect_ratio, description.
        Returns empty strings / default aspect_ratio if no style node is found.
        """
        style_nodes = self.get_active("style_active_during", event_id)
        if style_nodes:
            s = style_nodes[0]
            return {
                "style_prefix": s.get("style_prefix", ""),
                "negative_prefix": s.get("negative_prefix", ""),
                "aspect_ratio": s.get("aspect_ratio", "16:9"),
                "description": s.get("description", ""),
            }
        return {"style_prefix": "", "negative_prefix": "", "aspect_ratio": "16:9", "description": ""}


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
# Reference image collection & priority
# ---------------------------------------------------------------------------

_PRIORITY_MAP = {
    "appear_": 1,   # character appearance state
    "char_": 2,     # character entity
    "lstate_": 3,   # location state
    "loc_": 4,      # location entity
    "pstate_": 5,   # prop state
    "prop_": 6,     # prop entity
    "mind_": 99,    # minds have no reference image, skip
}


def _id_priority(node_id: str) -> int:
    for prefix, prio in _PRIORITY_MAP.items():
        if node_id.startswith(prefix):
            return prio
    return 50


def _collect_reference_images(
    shot: dict[str, Any],
    g: _GraphIndex,
    max_images: int = 4,
) -> list[dict[str, Any]]:
    """Collect reference images from focus_on nodes + their parent entities."""
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []

    for state_id in shot.get("focus_on", []):
        node = g.nodes.get(state_id)
        if not node:
            continue
        ref = node.get("reference_image")
        if ref and state_id not in seen:
            seen.add(state_id)
            candidates.append({"id": state_id, "path": ref, "priority": _id_priority(state_id)})
        # Also add parent entity's reference image
        entity = g.entity_of(node)
        if entity:
            ent_id = entity.get("id", "")
            ent_ref = entity.get("reference_image")
            if ent_ref and ent_id not in seen:
                seen.add(ent_id)
                candidates.append({"id": ent_id, "path": ent_ref, "priority": _id_priority(ent_id)})

    candidates.sort(key=lambda c: c["priority"])
    return candidates[:max_images]


# ---------------------------------------------------------------------------
# Prompt material extraction
# ---------------------------------------------------------------------------

def _extract_prompt_materials(
    event: dict[str, Any],
    shot: dict[str, Any],
    g: _GraphIndex,
) -> dict[str, Any]:
    """Extract all prompt-relevant information for a shot from the graph."""
    event_id = event["id"]

    # Read style from ProductionStyle nodes in the graph
    effective_style = g.get_style_for_event(event_id)

    # Active appearances
    appearances = []
    for a in g.get_active("appearance_active_during", event_id):
        appearances.append({
            "id": a["id"],
            "entity": a.get("entity", ""),
            "phase": a.get("phase", ""),
            "visual": a.get("visual", {}),
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

    # Location state
    location_state = None
    for ls in g.get_active("location_active_during", event_id):
        location_state = {
            "id": ls["id"],
            "entity": ls.get("entity", ""),
            "phase": ls.get("phase", ""),
            "appearance": ls.get("appearance", {}),
        }
        break  # typically one location state per event

    # Prop states
    prop_states = []
    for ps in g.get_active("prop_active_during", event_id):
        prop_states.append({
            "id": ps["id"],
            "entity": ps.get("entity", ""),
            "phase": ps.get("phase", ""),
            "appearance": ps.get("appearance", {}),
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
        "aspect_ratio": effective_style.get("aspect_ratio", "16:9"),
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
# Technique derivation
# ---------------------------------------------------------------------------

_CLOSE_SHOT_TYPES = {"close_up", "extreme_close", "over_shoulder", "detail_insert"}


def _derive_techniques(
    shot: dict[str, Any],
    event: dict[str, Any],
    prev_shot_info: dict[str, Any] | None,
    ref_images: list[dict[str, Any]],
    g: _GraphIndex,
    aspect_ratio: str = "16:9",
) -> dict[str, Any]:
    """Derive which consistency techniques to use for this shot."""

    # --- Technique A: reference images ---
    tech_a = {
        "enabled": len(ref_images) > 0,
        "images": ref_images,
        "reason": "focus_on contains state nodes with reference images" if ref_images else "no reference images available",
    }

    # --- Technique C: tail-frame continuity ---
    tech_c: dict[str, Any] = {"enabled": False, "reason": ""}
    if prev_shot_info:
        same_location = prev_shot_info.get("happens_at") == event.get("happens_at")
        if same_location and prev_shot_info.get("output_path"):
            tech_c = {
                "enabled": True,
                "prev_clip_path": prev_shot_info["output_path"],
                "reason": f"previous shot at same location ({event.get('happens_at', '')})",
            }
        else:
            tech_c = {
                "enabled": False,
                "reason": f"location changed ({prev_shot_info.get('happens_at', '')} -> {event.get('happens_at', '')})"
                if not same_location
                else "no previous clip available",
            }
    else:
        tech_c = {"enabled": False, "reason": "first shot, no previous clip"}

    # --- Technique B: first-frame generation ---
    shot_type = shot.get("shot_type", "")
    char_appearances_in_focus = [
        sid for sid in shot.get("focus_on", []) if sid.startswith("appear_")
    ]
    needs_first_frame = (
        shot_type in _CLOSE_SHOT_TYPES
        or len(char_appearances_in_focus) >= 2
    )

    tech_b: dict[str, Any]
    if needs_first_frame:
        # Collect reference_image_paths for GenerateImage
        gen_img_refs: list[str] = []
        for sid in shot.get("focus_on", []):
            node = g.nodes.get(sid)
            if node and node.get("reference_image"):
                gen_img_refs.append(node["reference_image"])
            if node:
                entity = g.entity_of(node)
                if entity and entity.get("reference_image"):
                    ent_ref = entity["reference_image"]
                    if ent_ref not in gen_img_refs:
                        gen_img_refs.append(ent_ref)

        reasons = []
        if shot_type in _CLOSE_SHOT_TYPES:
            reasons.append(f"shot_type is {shot_type}")
        if len(char_appearances_in_focus) >= 2:
            reasons.append(f"focus_on contains {len(char_appearances_in_focus)} character appearances")

        tech_b = {
            "enabled": True,
            "reason": "; ".join(reasons),
            "generate_image_spec": {
                "reference_image_paths": gen_img_refs,
                "aspect_ratio": aspect_ratio,
            },
        }
    else:
        tech_b = {"enabled": False, "reason": "not a close-up and < 2 character appearances in focus"}

    return {
        "A_reference_images": tech_a,
        "B_first_frame": tech_b,
        "C_tail_frame": tech_c,
    }


# ---------------------------------------------------------------------------
# Recommended call assembly
# ---------------------------------------------------------------------------

def _build_recommended_call(
    techniques: dict[str, Any],
    ref_images: list[dict[str, Any]],
    shot: dict[str, Any],
    aspect_ratio: str = "16:9",
) -> dict[str, Any]:
    """Build recommended GenerateVideo parameters."""
    tech_c = techniques["C_tail_frame"]
    tech_b = techniques["B_first_frame"]

    # Determine mode
    if tech_c["enabled"] or tech_b["enabled"]:
        mode = "image_to_video"
    else:
        mode = "text_to_video"

    call: dict[str, Any] = {
        "mode": mode,
        "duration_seconds": 5,
        "aspect_ratio": aspect_ratio,
    }

    # reference_images (Technique A)
    if ref_images:
        call["reference_images"] = [img["path"] for img in ref_images]

    # reference_image_path source priority: C (tail frame) > B (first frame)
    if tech_c["enabled"]:
        call["reference_image_source"] = "tail_frame"
        call["tail_frame_clip"] = tech_c["prev_clip_path"]
    elif tech_b["enabled"]:
        call["reference_image_source"] = "generated_first_frame"

    return call


# ---------------------------------------------------------------------------
# Main linearization
# ---------------------------------------------------------------------------

def linearize(data: dict[str, Any]) -> dict[str, Any]:
    """Linearize a story graph into a shot plan. Pure function, no I/O."""
    g = _GraphIndex(data)

    # Topological sort
    event_ids = set(g.events.keys())
    sorted_events = _topological_sort(event_ids, g.event_sequence)
    event_order = {eid: i for i, eid in enumerate(sorted_events)}
    g.set_event_order(event_order)

    # Parallel groups
    parallel_groups = _find_parallel_groups(g.event_sequence)

    # Build shots
    shots: list[dict[str, Any]] = []
    warnings: list[str] = []
    prev_shot_info: dict[str, Any] | None = None

    for event_id in sorted_events:
        event = g.events.get(event_id)
        if not event:
            continue

        cam = g.cam_by_event.get(event_id)
        if not cam:
            warnings.append(f"event {event_id}: no camera_directive found, skipping")
            continue

        cam_shots = cam.get("shots", [])
        for shot in sorted(cam_shots, key=lambda s: s.get("order", 0)):
            shot_id = f"{cam['id']}_shot_{shot.get('order', 0)}"
            output_path = f"assets/clips/{event_id}_shot_{shot.get('order', 0)}.mp4"

            # Collect reference images (Technique A)
            ref_images = _collect_reference_images(shot, g)

            # Check for missing reference images
            for sid in shot.get("focus_on", []):
                node = g.nodes.get(sid)
                if node and not node.get("reference_image") and not sid.startswith("mind_"):
                    warnings.append(f"{shot_id}: focus_on '{sid}' has no reference_image")

            # Extract prompt materials (includes per-event style from graph)
            materials = _extract_prompt_materials(event, shot, g)
            shot_aspect_ratio = materials.get("aspect_ratio", "16:9")

            # Derive techniques
            techniques = _derive_techniques(shot, event, prev_shot_info, ref_images, g, shot_aspect_ratio)

            # Build recommended call
            recommended_call = _build_recommended_call(techniques, ref_images, shot, shot_aspect_ratio)

            shot_plan = {
                "shot_id": shot_id,
                "event_id": event_id,
                "camera_directive_id": cam["id"],
                "order": shot.get("order", 0),
                "output_path": output_path,
                # Camera language
                "shot_type": shot.get("shot_type", ""),
                "angle": shot.get("angle", ""),
                "movement": shot.get("movement", ""),
                "intent": shot.get("intent", ""),
                "focus_on": shot.get("focus_on", []),
                # Consistency techniques
                "techniques": techniques,
                # Prompt materials
                "prompt_materials": materials,
                # Recommended call
                "recommended_call": recommended_call,
            }
            shots.append(shot_plan)

            # Update prev_shot_info for next iteration
            prev_shot_info = {
                "shot_id": shot_id,
                "event_id": event_id,
                "happens_at": event.get("happens_at", ""),
                "output_path": output_path,
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

        # Linearize (style is read from production_styles nodes in the graph)
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

        tech_a_count = sum(1 for s in plan["shots"] if s["techniques"]["A_reference_images"]["enabled"])
        tech_b_count = sum(1 for s in plan["shots"] if s["techniques"]["B_first_frame"]["enabled"])
        tech_c_count = sum(1 for s in plan["shots"] if s["techniques"]["C_tail_frame"]["enabled"])

        builder.write(f"Shot plan generated: {n_shots} shots\n\n")
        builder.write(f"Consistency techniques:\n")
        builder.write(f"  Technique A (reference images): {tech_a_count}/{n_shots} shots\n")
        builder.write(f"  Technique B (first-frame gen):  {tech_b_count}/{n_shots} shots\n")
        builder.write(f"  Technique C (tail-frame cont):  {tech_c_count}/{n_shots} shots\n")
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
