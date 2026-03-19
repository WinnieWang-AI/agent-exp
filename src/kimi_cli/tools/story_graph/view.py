"""Build StoryGraphViewDisplayBlock from story-graph data."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from kimi_cli.tools.display import (
    StoryGraphAudioState,
    StoryGraphEntity,
    StoryGraphEvent,
    StoryGraphInteraction,
    StoryGraphMind,
    StoryGraphOutput,
    StoryGraphProductionStyle,
    StoryGraphShot,
    StoryGraphState,
    StoryGraphVideoInfo,
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


def _topo_sort_events(data: dict[str, Any]) -> list[str]:
    """Topological sort of events by event_sequence edges."""
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


def _summarize_visual(visual: dict[str, Any] | Any) -> str:
    """Flatten a visual/appearance dict into a short description string."""
    if not visual or not isinstance(visual, dict):
        return ""
    parts = [f"{v}" for v in visual.values() if v]
    return "，".join(parts)


def _build_entity_states(data: dict[str, Any]) -> dict[str, list[StoryGraphState]]:
    """Build entity_id -> list of child state nodes."""
    states: dict[str, list[StoryGraphState]] = defaultdict(list)
    for a in data.get("character_appearances", []):
        states[a.get("entity", "")].append(StoryGraphState(
            id=a["id"],
            phase=a.get("phase", ""),
            reference_image=a.get("reference_image") or "",
            description=_summarize_visual(a.get("visual")),
            generation_prompt=a.get("generation_prompt") or "",
        ))
    for ls in data.get("location_states", []):
        states[ls.get("entity", "")].append(StoryGraphState(
            id=ls["id"],
            phase=ls.get("phase", ""),
            reference_image=ls.get("reference_image") or "",
            description=_summarize_visual(ls.get("appearance")),
            generation_prompt=ls.get("generation_prompt") or "",
        ))
    for ps in data.get("prop_states", []):
        states[ps.get("entity", "")].append(StoryGraphState(
            id=ps["id"],
            phase=ps.get("phase", ""),
            reference_image=ps.get("reference_image") or "",
            description=_summarize_visual(ps.get("appearance")),
            generation_prompt=ps.get("generation_prompt") or "",
        ))
    return dict(states)


def _build_audio_by_event(
    data: dict[str, Any],
    project_dir: str,
) -> dict[str, list[StoryGraphAudioState]]:
    """Build event_id -> list of active audio states."""
    audio_nodes: dict[str, dict[str, Any]] = {}
    for a in data.get("audio_states", []):
        audio_nodes[a["id"]] = a

    audio_by_event: dict[str, list[str]] = defaultdict(list)
    for state_id, evt_list in data.get("audio_active_during", {}).items():
        for eid in evt_list:
            audio_by_event[eid].append(state_id)

    result: dict[str, list[StoryGraphAudioState]] = {}
    for eid, state_ids in audio_by_event.items():
        items: list[StoryGraphAudioState] = []
        for aid in state_ids:
            anode = audio_nodes.get(aid, {})
            audio_file = ""
            if project_dir:
                candidate = Path(project_dir) / "assets" / "audio" / f"{aid}.mp3"
                if candidate.exists():
                    audio_file = str(candidate)
            items.append(StoryGraphAudioState(
                id=aid,
                layer=anode.get("layer", ""),
                phase=anode.get("phase", ""),
                text=anode.get("text", ""),
                speaker=anode.get("speaker", ""),
                audio_file=audio_file,
            ))
        result[eid] = items
    return result


def _build_minds_by_event(
    data: dict[str, Any],
    char_names: dict[str, str],
) -> dict[str, list[StoryGraphMind]]:
    """Build event_id -> list of active character minds."""
    mind_nodes: dict[str, dict[str, Any]] = {}
    for m in data.get("character_minds", []):
        mind_nodes[m["id"]] = m

    minds_by_event: dict[str, list[str]] = defaultdict(list)
    for mind_id, evt_list in data.get("mind_active_during", {}).items():
        for eid in evt_list:
            minds_by_event[eid].append(mind_id)

    result: dict[str, list[StoryGraphMind]] = {}
    for eid, mind_ids in minds_by_event.items():
        items: list[StoryGraphMind] = []
        for mid in mind_ids:
            mnode = mind_nodes.get(mid, {})
            entity_id = mnode.get("entity", "")
            items.append(StoryGraphMind(
                id=mid,
                entity=entity_id,
                entity_name=char_names.get(entity_id, entity_id),
                phase=mnode.get("phase", ""),
                emotion=mnode.get("emotion", ""),
                behavior=mnode.get("behavior", ""),
            ))
        result[eid] = items
    return result


def _build_outputs(project_dir: str) -> list[StoryGraphOutput]:
    """Scan project output directory for assembled videos."""
    if not project_dir:
        return []
    output_dir = Path(project_dir) / "output"
    if not output_dir.exists():
        return []

    stage_labels = {
        "picture_lock": "画面定版",
        "temp_bgm": "叠加 BGM",
        "final": "最终成片",
    }
    outputs: list[StoryGraphOutput] = []
    for mp4 in sorted(output_dir.glob("*.mp4")):
        stem = mp4.stem
        if stem.startswith("tmp_"):
            continue
        outputs.append(StoryGraphOutput(
            stage=stem,
            video_path=str(mp4),
            label=stage_labels.get(stem, stem),
        ))
    return outputs


def _resolve_path(project_dir: str, relative_path: str) -> str:
    """Resolve a relative asset path to absolute, or return as-is."""
    if not project_dir or not relative_path:
        return relative_path
    absolute = Path(project_dir) / relative_path
    return str(absolute)


def _collect_shot_reference_images(shot: dict[str, Any]) -> list[str]:
    """Collect all available reference images from a shot's prompt_materials.

    Returns deduplicated paths in stable order (appearance states first,
    then location, then props; state images before entity images).
    """
    materials = shot.get("prompt_materials", {})
    refs: list[str] = []
    seen: set[str] = set()

    def _add(path: str) -> None:
        if path and path not in seen:
            seen.add(path)
            refs.append(path)

    for app in materials.get("appearances", []):
        _add(app.get("reference_image", ""))
    for app in materials.get("appearances", []):
        _add(app.get("entity_reference_image", ""))
    loc = materials.get("location_state")
    if loc:
        _add(loc.get("reference_image", ""))
        _add(loc.get("entity_reference_image", ""))
    for ps in materials.get("prop_states", []):
        _add(ps.get("reference_image", ""))
    for ps in materials.get("prop_states", []):
        _add(ps.get("entity_reference_image", ""))
    return refs


def build_story_graph_view(
    data: dict[str, Any],
    *,
    phase: str = "skeleton",
    shot_plan: dict[str, Any] | None = None,
    project_dir: str = "",
) -> StoryGraphViewDisplayBlock:
    """Build a StoryGraphViewDisplayBlock from raw story-graph data.

    Args:
        data: The parsed story-graph.json dict.
        phase: One of "skeleton", "references", "shots", "videos".
        shot_plan: Optional parsed shot-plan.json for enriching shot data.
        project_dir: Absolute path to the project directory (for resolving asset paths).
    """
    # --- Video Info (global specs) ---
    vi = data.get("video_info")
    if vi:
        video_info = StoryGraphVideoInfo(
            aspect_ratio=vi.get("aspect_ratio", ""),
            duration=vi.get("duration", ""),
            language=vi.get("language", ""),
        )
    else:
        # Backward compat: fall back to production_styles[0]
        ps0 = (data.get("production_styles") or [{}])[0] if data.get("production_styles") else {}
        video_info = StoryGraphVideoInfo(
            aspect_ratio=ps0.get("aspect_ratio", ""),
            duration=ps0.get("duration", ""),
            language=ps0.get("language", ""),
        )

    # --- Production Styles ---
    production_styles: list[StoryGraphProductionStyle] = []
    for ps in data.get("production_styles", []):
        production_styles.append(StoryGraphProductionStyle(
            id=ps["id"],
            description=ps.get("description", ""),
            style_prefix=ps.get("style_prefix", ""),
            negative_prefix=ps.get("negative_prefix", ""),
        ))

    # --- Entity states ---
    entity_states = _build_entity_states(data)

    # --- Entities (with child states) ---
    entities: list[StoryGraphEntity] = []
    for c in data.get("characters", []):
        entities.append(StoryGraphEntity(
            id=c["id"],
            name=c.get("name", c["id"]),
            kind="character",
            reference_image=c.get("reference_image") or "",
            description=c.get("fixed_traits", ""),
            generation_prompt=c.get("generation_prompt") or "",
            states=entity_states.get(c["id"], []),
        ))
    for loc in data.get("locations", []):
        entities.append(StoryGraphEntity(
            id=loc["id"],
            name=loc.get("name", loc["id"]),
            kind="location",
            reference_image=loc.get("reference_image") or "",
            description=loc.get("fixed_traits", ""),
            generation_prompt=loc.get("generation_prompt") or "",
            states=entity_states.get(loc["id"], []),
        ))
    for p in data.get("props", []):
        entities.append(StoryGraphEntity(
            id=p["id"],
            name=p.get("name", p["id"]),
            kind="prop",
            reference_image=p.get("reference_image") or "",
            description=p.get("fixed_traits", ""),
            generation_prompt=p.get("generation_prompt") or "",
            states=entity_states.get(p["id"], []),
        ))

    # --- Reverse map: event -> appearance state ids (for character_ids) ---
    appear_by_event: dict[str, list[str]] = defaultdict(list)
    for state_id, evt_list in data.get("appearance_active_during", {}).items():
        for eid in evt_list:
            appear_by_event[eid].append(state_id)

    appear_entity: dict[str, str] = {}
    for a in data.get("character_appearances", []):
        appear_entity[a["id"]] = a.get("entity", "")

    # --- Audio by event ---
    audio_by_event = _build_audio_by_event(data, project_dir)

    # --- Character name lookup (for mind/audio speaker display) ---
    char_names: dict[str, str] = {}
    for c in data.get("characters", []):
        char_names[c["id"]] = c.get("name", c["id"])

    # --- Minds by event ---
    minds_by_event = _build_minds_by_event(data, char_names)

    # --- Shot lookup from shot_plan ---
    shots_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if shot_plan:
        for s in shot_plan.get("shots", []):
            shots_by_event[s["event_id"]].append(s)

    # --- Topological event order ---
    sorted_event_ids = _topo_sort_events(data)
    events_by_id = {e["id"]: e for e in data.get("events", [])}

    # --- Timeline ---
    timeline: list[StoryGraphEvent] = []
    for eid in sorted_event_ids:
        event = events_by_id.get(eid)
        if not event:
            continue

        char_ids = _extract_character_ids_for_event(event, appear_by_event, appear_entity)
        active_appear_ids = appear_by_event.get(eid, [])

        # Interactions
        interactions = [
            StoryGraphInteraction(
                between=[char_names.get(cid, cid) for cid in i.get("between", [])],
                style=i.get("style", ""),
            )
            for i in event.get("interactions", [])
        ]

        # Audio states for this event (resolve speaker id -> name)
        event_audio: list[StoryGraphAudioState] = []
        for a in audio_by_event.get(eid, []):
            event_audio.append(StoryGraphAudioState(
                id=a.id,
                layer=a.layer,
                phase=a.phase,
                text=a.text,
                speaker=char_names.get(a.speaker, a.speaker),
                audio_file=a.audio_file,
            ))

        # Shots (1:1 from shot_plan)
        shots: list[StoryGraphShot] = []
        for shot_entry in shots_by_event.get(eid, []):
            shot_id = shot_entry["shot_id"]
            execution = shot_entry.get("execution")

            if execution:
                # Agent has executed this shot — show actual materials used
                ref_images = [_resolve_path(project_dir, p) for p in execution.get("reference_images", []) if p]
                first_frame = _resolve_path(project_dir, execution.get("first_frame_path", ""))
                tail_frame = _resolve_path(project_dir, execution.get("tail_frame_path", ""))
                mode = execution.get("mode", "")
                prompt = execution.get("prompt", "")
            else:
                # Not yet executed — show available materials from inventory
                ref_images = [_resolve_path(project_dir, p) for p in _collect_shot_reference_images(shot_entry) if p]
                first_frame = ""
                tail_frame = ""
                if project_dir:
                    ff = Path(project_dir) / f"assets/frames/{shot_id}_first.png"
                    if ff.exists():
                        first_frame = str(ff)
                    tf = Path(project_dir) / f"assets/frames/{shot_id}_tail.png"
                    if tf.exists():
                        tail_frame = str(tf)
                mode = ""
                prompt = ""

            # Video file: resolve to absolute path only if file exists
            video_clip = ""
            if project_dir and shot_entry.get("output_path"):
                vc = Path(project_dir) / shot_entry["output_path"]
                if vc.exists():
                    video_clip = str(vc)

            # Sequence continuity (cross-shot tail-frame)
            seq_prev = shot_entry.get("prev_shot_in_sequence")
            seq_prev_shot_id = seq_prev["shot_id"] if seq_prev else ""
            seq_tail_frame = ""
            if seq_prev and project_dir:
                # Check if agent wrote the extracted tail frame
                seq_tf = Path(project_dir) / f"assets/frames/{shot_id}_seq_tail.png"
                if seq_tf.exists():
                    seq_tail_frame = str(seq_tf)
            if execution and execution.get("sequence_tail_frame_path"):
                seq_tail_frame = _resolve_path(project_dir, execution["sequence_tail_frame_path"])

            shots.append(StoryGraphShot(
                shot_id=shot_id,
                order=shot_entry.get("order", 1),
                shot_type=shot_entry.get("shot_type", ""),
                angle=shot_entry.get("angle", ""),
                movement=shot_entry.get("movement", ""),
                intent=shot_entry.get("intent", ""),
                focus_on=shot_entry.get("focus_on", []),
                is_continuation=shot_entry.get("is_continuation", False),
                sequence_prev_shot_id=seq_prev_shot_id,
                sequence_tail_frame=seq_tail_frame,
                mode=mode,
                prompt=prompt,
                video_clip=video_clip,
                reference_images=ref_images,
                first_frame=first_frame,
                tail_frame=tail_frame,
            ))

        timeline.append(StoryGraphEvent(
            id=eid,
            description=event.get("description", ""),
            happens_at=event.get("happens_at", ""),
            character_ids=char_ids,
            active_appearance_ids=active_appear_ids,
            minds=minds_by_event.get(eid, []),
            shots=shots,
            interactions=interactions,
            audio_states=event_audio,
        ))

    # --- Parallel groups ---
    edges = data.get("event_sequence", [])
    parallel_groups: list[list[str]] = []
    for e in edges:
        if e.get("type") == "PARALLEL":
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

    # --- Outputs ---
    outputs = _build_outputs(project_dir)

    # --- Summary ---
    n_chars = sum(1 for e in entities if e.kind == "character")
    n_locs = sum(1 for e in entities if e.kind == "location")
    n_props = sum(1 for e in entities if e.kind == "prop")
    n_events = len(timeline)
    n_shots = sum(len(ev.shots) for ev in timeline)
    n_with_ref = sum(1 for e in entities if e.reference_image)
    n_states = sum(len(e.states) for e in entities)
    n_audio = len(data.get("audio_states", []))

    summary = {
        "characters": n_chars,
        "locations": n_locs,
        "props": n_props,
        "events": n_events,
        "shots": n_shots,
        "entities_with_reference_images": n_with_ref,
        "states": n_states,
        "audio_states": n_audio,
        "outputs": len(outputs),
    }

    return StoryGraphViewDisplayBlock(
        phase=phase,
        video_info=video_info,
        production_styles=production_styles,
        entities=entities,
        timeline=timeline,
        parallel_groups=parallel_groups,
        summary=summary,
        outputs=outputs,
    )
