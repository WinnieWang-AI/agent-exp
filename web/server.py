"""
Web server for interacting with video-director and video-auto-eval agents.

Provides:
- WebSocket endpoints for real-time agent communication
- Three modes: chat with director, chat with auto-eval, auto-interaction mode
- Session management: each conversation gets a session_id for persistence and retrieval
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

import mimetypes

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from kaos.path import KaosPath

from kimi_cli.agentspec import VIDEO_DIRECTOR_AGENT_FILE, VIDEO_AUTO_EVAL_AGENT_FILE, AGENT_OPTIMIZER_AGENT_FILE, SCREENWRITER_AGENT_FILE
from kimi_cli.app import KimiCLI, enable_logging
from kimi_cli.session import Session
from kimi_cli.wire.types import (
    ApprovalRequest,
    ContentPart,
    QuestionRequest,
    SubagentEvent,
    TextPart,
    ThinkPart,
    ToolCall,
    ToolCallPart,
    ToolResult,
    TurnBegin,
    TurnEnd,
    StepBegin,
    StepInterrupted,
    WireMessageEnvelope,
    is_event,
    is_request,
)

enable_logging()

app = FastAPI(title="Video Agent Web UI")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

WORK_DIR = KaosPath.unsafe_from_local_path(Path.cwd())

# Directory for web session metadata (chat logs, session info)
WEB_SESSIONS_DIR = Path.cwd() / "output" / ".sessions"
WEB_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

AGENT_FILES = {
    "video-director": VIDEO_DIRECTOR_AGENT_FILE,
    "video-auto-eval": VIDEO_AUTO_EVAL_AGENT_FILE,
    "agent-optimizer": AGENT_OPTIMIZER_AGENT_FILE,
    "screenwriter": SCREENWRITER_AGENT_FILE,
}


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/files/{file_path:path}")
async def serve_local_file(file_path: str):
    """Serve a local file (images, videos, etc.) so the frontend can display them."""
    full_path = Path("/") / file_path
    # If not found as absolute, try relative to working directory
    if not full_path.is_file():
        full_path = Path.cwd() / file_path
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    # Only serve media files
    mime, _ = mimetypes.guess_type(str(full_path))
    if not mime or not (
        mime.startswith("image/")
        or mime.startswith("video/")
        or mime.startswith("audio/")
    ):
        raise HTTPException(status_code=403, detail="Only media files are served")
    return FileResponse(str(full_path), media_type=mime)


@app.get("/read-json/{file_path:path}")
async def read_json_file(file_path: str):
    """Serve a local JSON file (e.g., story-graph.json) so the frontend can load it."""
    # Try as absolute path first
    full_path = Path("/") / file_path
    if not full_path.is_file():
        # Try relative to cwd (handles paths like "output/session_id/project/story-graph.json")
        full_path = (Path.cwd() / file_path).resolve()
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    if full_path.suffix != ".json":
        raise HTTPException(status_code=403, detail="Only JSON files are served")
    return FileResponse(
        str(full_path),
        media_type="application/json",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


def serialize_wire_message(msg: Any) -> dict:
    """Convert a WireMessage to a JSON-serializable dict."""
    envelope = WireMessageEnvelope.from_wire_message(msg)
    return envelope.model_dump(mode="json")


def _get_session_dir(session_id: str) -> Path:
    """Get the web session directory for a given session_id."""
    d = WEB_SESSIONS_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_session_meta(session_id: str, agent_name: str, mode: str) -> None:
    """Save session metadata (agent, mode, timestamps)."""
    meta_path = _get_session_dir(session_id) / "meta.json"
    meta: dict[str, Any] = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    if "created_at" not in meta:
        meta["created_at"] = time.time()
    meta.update({
        "session_id": session_id,
        "agent": agent_name,
        "mode": mode,
        "updated_at": time.time(),
    })
    meta_path.write_text(json.dumps(meta, ensure_ascii=False))


def _build_session_summary(session_id: str) -> dict[str, Any]:
    """Build a summary of an existing session for display on resume."""
    summary: dict[str, Any] = {"session_id": session_id}

    session_output_dir = Path.cwd() / "output" / session_id
    if not session_output_dir.is_dir():
        return summary

    # Find project directory (video project with story-graph.json, etc.)
    # Scan for key files
    story_graph_path = None
    shot_plan_path = None
    project_name = None
    for p in session_output_dir.rglob("story-graph.json"):
        story_graph_path = p
        # project_name = parent directory name (e.g. output/{session_id}/{project_name}/story-graph.json)
        if p.parent != session_output_dir:
            project_name = p.parent.name
        break
    for p in session_output_dir.rglob("shot-plan.json"):
        shot_plan_path = p
        break

    if project_name:
        summary["project_name"] = project_name

    # Story graph summary
    if story_graph_path and story_graph_path.exists():
        try:
            sg_data = json.loads(story_graph_path.read_text(encoding="utf-8"))
            n_chars = len(sg_data.get("characters", []))
            n_locs = len(sg_data.get("locations", []))
            n_events = len(sg_data.get("events", []))

            # Count entity reference images (characters, locations, props)
            all_entities = sg_data.get("characters", []) + sg_data.get("locations", []) + sg_data.get("props", [])
            n_entity_refs = sum(1 for c in all_entities if c.get("reference_image"))

            # Count state reference images
            all_states = (
                sg_data.get("character_appearances", [])
                + sg_data.get("location_states", [])
                + sg_data.get("prop_states", [])
            )
            n_state_refs = sum(1 for s in all_states if s.get("reference_image"))
            n_total_entities = len(all_entities)
            n_total_states = len(all_states)

            # Check if camera_directives and audio_states are populated
            has_camera = bool(sg_data.get("camera_directives"))
            has_audio = bool(sg_data.get("audio_states"))

            # Extract production style info
            prod_styles = sg_data.get("production_styles", [])
            style_info = None
            if prod_styles:
                ps = prod_styles[0]
                style_info = {
                    "style_prefix": ps.get("style_prefix", ""),
                    "aspect_ratio": ps.get("aspect_ratio", "16:9"),
                }

            summary["story_graph"] = {
                "path": str(story_graph_path),
                "characters": n_chars,
                "locations": n_locs,
                "events": n_events,
                "entity_reference_images": n_entity_refs,
                "state_reference_images": n_state_refs,
                "total_entities": n_total_entities,
                "total_states": n_total_states,
                "has_camera_directives": has_camera,
                "has_audio_states": has_audio,
                "production_style": style_info,
            }
        except Exception:
            pass

    # Shot plan summary
    if shot_plan_path and shot_plan_path.exists():
        try:
            sp_data = json.loads(shot_plan_path.read_text(encoding="utf-8"))
            n_shots = sp_data.get("total_shots", 0)
            summary["shot_plan"] = {
                "path": str(shot_plan_path),
                "total_shots": n_shots,
            }
        except Exception:
            pass

    # Count generated clips (exclude small placeholders < 1MB)
    clips = list(session_output_dir.rglob("*.mp4"))
    real_clips = [c for c in clips if c.stat().st_size > 1_000_000]  # > 1MB
    if clips:
        summary["clips"] = {"total": len(clips), "valid": len(real_clips)}

    # Count generated images
    images = list(session_output_dir.rglob("*.png")) + list(session_output_dir.rglob("*.jpg"))
    if images:
        summary["images"] = len(images)

    # Check for final output
    output_dir = session_output_dir / (project_name or "") / "output"
    final_videos = list(output_dir.glob("*.mp4")) if output_dir.is_dir() else []
    if final_videos:
        summary["final_video"] = str(final_videos[0])

    # Last user message from chat log
    chat_path = _get_session_dir(session_id) / "chat.jsonl"
    if chat_path.exists():
        last_user_msg = None
        for line in chat_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("role") == "user":
                    last_user_msg = entry.get("content", "")
            except Exception:
                pass
        if last_user_msg:
            summary["last_user_message"] = last_user_msg[:200]

    return summary


def _build_resume_context(summary: dict[str, Any]) -> str:
    """Build an actionable resume context string from a session summary.

    This tells the director agent exactly what exists on disk and which step to resume from,
    so it doesn't need to call subagents just to scan the project state.
    """
    if not summary.get("story_graph") and not summary.get("project_name"):
        return ""

    lines = ["[Session resumed. Project state scanned from disk — no need to call subagents to check files.]"]

    project_name = summary.get("project_name", "unknown")
    lines.append(f"Project name: {project_name}")
    lines.append(f"Session IDs: graph_{project_name}, create_{project_name}, eval_{project_name}")

    sg = summary.get("story_graph")
    if sg:
        lines.append(f"Story Graph: {sg['path']}")
        lines.append(f"  - {sg['characters']} characters, {sg['locations']} locations, {sg['events']} events")
        lines.append(f"  - camera_directives: {'present' if sg['has_camera_directives'] else 'EMPTY'}")
        lines.append(f"  - audio_states: {'present' if sg['has_audio_states'] else 'EMPTY'}")
        if sg.get("production_style"):
            ps = sg["production_style"]
            lines.append(f"  - style: {ps.get('style_prefix', '')[:80]}, aspect_ratio: {ps.get('aspect_ratio', '16:9')}")
        lines.append(f"  - Entity reference images: {sg['entity_reference_images']}/{sg['total_entities']}")
        lines.append(f"  - State reference images: {sg['state_reference_images']}/{sg['total_states']}")

    if summary.get("shot_plan"):
        lines.append(f"Shot Plan: {summary['shot_plan']['total_shots']} shots (path: {summary['shot_plan']['path']})")

    clips = summary.get("clips")
    if clips:
        lines.append(f"Video Clips: {clips['total']} files, {clips['valid']} valid (>1MB)")

    if summary.get("final_video"):
        lines.append(f"Final video: {summary['final_video']}")

    # Determine the resume step
    if not sg:
        resume_step = "Step 1.5 (build story structure)"
    elif not sg["has_camera_directives"]:
        resume_step = "Step 1.6 (design camera directives & audio — story structure is done)"
    elif sg["entity_reference_images"] < sg["total_entities"] or sg["state_reference_images"] < sg["total_states"]:
        resume_step = "Step 1.8 (generate reference images — story graph is complete)"
    elif not clips or clips["valid"] == 0:
        resume_step = "Step 2 (generate video clips — reference images are ready)"
    elif summary.get("final_video"):
        resume_step = "Complete — final video exists. Ask user what they want to do next."
    else:
        resume_step = "Step 2 (continue video generation / assembly)"

    lines.append(f"\nResume from: {resume_step}")
    lines.append("Do NOT re-ask the user for topic/style/duration — these are already confirmed in chat history.")

    return "\n".join(lines) + "\n\n"


def _append_chat_log(session_id: str, role: str, agent: str, content: Any) -> None:
    """Append a chat entry to the session's chat.jsonl."""
    chat_path = _get_session_dir(session_id) / "chat.jsonl"
    entry = {
        "timestamp": time.time(),
        "role": role,
        "agent": agent,
        "content": content,
    }
    with open(chat_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def create_cli(agent_name: str, session_id: str | None = None) -> tuple[KimiCLI, bool]:
    """Create a KimiCLI instance for the given agent, optionally resuming an existing session.

    Returns (cli, resumed) where resumed=True if an existing session was loaded.

    Each session gets its own work_dir under output/{session_id}/ so that
    project files (video clips, scripts, etc.) are isolated per session.
    """
    work_dir = WORK_DIR
    agent_file = AGENT_FILES[agent_name]
    resumed = False

    # Try to resume existing session
    if session_id:
        existing = await Session.find(work_dir, session_id)
        if existing and not existing.is_empty():
            session_output_dir = Path.cwd() / "output" / session_id
            session_output_dir.mkdir(parents=True, exist_ok=True)
            cli = await KimiCLI.create(
                existing,
                agent_file=agent_file,
                session_output_dir=str(session_output_dir),
                yolo=True,
            )
            return cli, True

    # Create new session
    if session_id is None:
        session_id = str(uuid.uuid4())
    session_output_dir = Path.cwd() / "output" / session_id
    session_output_dir.mkdir(parents=True, exist_ok=True)

    session = await Session.create(work_dir, session_id=session_id)
    cli = await KimiCLI.create(
        session,
        agent_file=agent_file,
        session_output_dir=str(session_output_dir),
        yolo=True,
    )

    return cli, False


# ─── Session REST APIs ───────────────────────────────────────────────


@app.get("/api/sessions")
async def list_sessions():
    """List all web sessions, sorted by most recent."""
    sessions = []
    if WEB_SESSIONS_DIR.exists():
        for d in WEB_SESSIONS_DIR.iterdir():
            meta_path = d / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                sessions.append(meta)
    sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session metadata and chat history."""
    session_dir = WEB_SESSIONS_DIR / session_id
    if not session_dir.is_dir():
        raise HTTPException(status_code=404, detail="Session not found")
    meta_path = session_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    chat_path = session_dir / "chat.jsonl"
    messages = []
    if chat_path.exists():
        for line in chat_path.read_text().splitlines():
            if line.strip():
                messages.append(json.loads(line))
    return {"meta": meta, "messages": messages}


async def handle_question(websocket: WebSocket, msg: QuestionRequest, pending: dict):
    """Send a QuestionRequest to the frontend and wait for the user's answer."""
    questions = []
    for q in msg.questions:
        qdata: dict[str, Any] = {"question": q.question}
        if q.options:
            qdata["options"] = [{"label": o.label} for o in q.options]
        questions.append(qdata)
    qid = id(msg)
    pending[qid] = msg
    await websocket.send_json({
        "type": "question",
        "id": qid,
        "questions": questions,
    })


@app.websocket("/ws/chat/{agent_name}")
async def ws_chat(websocket: WebSocket, agent_name: str):
    """
    WebSocket endpoint for chatting with a single agent.

    Protocol:
    - Client sends: {"type": "message", "content": "...", "session_id": "..."} (session_id optional, only used on first message to resume)
    - Client sends: {"type": "answer", "id": ..., "answers": {...}}
    - Server sends: {"type": "session", "session_id": "..."}  (sent once after init)
    - Server sends: {"type": "wire", "data": {...}}  (wire message envelope)
    - Server sends: {"type": "question", "id": ..., "questions": [...]}
    - Server sends: {"type": "status", "status": "ready"|"thinking"|"done"|"error"}
    - Server sends: {"type": "error", "message": "..."}
    """
    if agent_name not in AGENT_FILES:
        await websocket.close(code=4000, reason=f"Unknown agent: {agent_name}")
        return

    await websocket.accept()
    await websocket.send_json({"type": "status", "status": "initializing"})

    # Wait for first message to check for session_id
    first_raw = await websocket.receive_json()
    requested_session_id = first_raw.get("session_id")

    try:
        cli, resumed = await create_cli(agent_name, session_id=requested_session_id)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Failed to create agent: {e}"})
        await websocket.close()
        return

    session_id = cli.session.id
    _save_session_meta(session_id, agent_name, mode="chat")
    await websocket.send_json({"type": "session", "session_id": session_id})

    resume_context = ""
    if resumed:
        summary = _build_session_summary(session_id)
        await websocket.send_json({"type": "resumed", "summary": summary})
        # Build a rich context hint so the agent knows exactly where to resume
        resume_context = _build_resume_context(summary)

    await websocket.send_json({"type": "status", "status": "ready"})

    pending_questions: dict[int, QuestionRequest] = {}
    incoming_queue: asyncio.Queue = asyncio.Queue()

    # Re-inject the first message into the queue
    if resumed and resume_context:
        # On resume, always send resume_context (+ user content if any) as the first message
        first_raw = dict(first_raw)
        user_content = first_raw.get("content", "")
        if user_content:
            first_raw["content"] = resume_context + user_content
        else:
            first_raw["content"] = resume_context + "继续"
            first_raw["type"] = "message"
        resume_context = ""  # already injected
        await incoming_queue.put(first_raw)
    elif not resumed and first_raw.get("content"):
        await incoming_queue.put(first_raw)

    async def ws_reader():
        """Read from websocket and put messages into the queue."""
        try:
            while True:
                raw = await websocket.receive_json()
                await incoming_queue.put(raw)
        except WebSocketDisconnect:
            await incoming_queue.put(None)  # sentinel

    reader_task = asyncio.create_task(ws_reader())

    try:
        while True:
            raw = await incoming_queue.get()
            if raw is None:
                break

            # Handle answers to pending questions
            if raw.get("type") == "answer":
                qid = raw.get("id")
                qmsg = pending_questions.pop(qid, None)
                if qmsg:
                    answers = raw.get("answers", {})
                    qmsg.resolve(answers)
                continue

            if raw.get("type") != "message":
                continue

            content = raw.get("content", "")
            if not content:
                continue

            # Inject resume context hint into the first user message after resume
            if resume_context:
                content = resume_context + content
                resume_context = ""  # only inject once

            _append_chat_log(session_id, "user", "user", content)
            await websocket.send_json({"type": "status", "status": "thinking"})
            cancel_event = asyncio.Event()

            async def run_agent():
                try:
                    async for msg in cli.run(content, cancel_event, merge_wire_messages=True):
                        try:
                            data = serialize_wire_message(msg)
                            await websocket.send_json({"type": "wire", "data": data})
                            _append_chat_log(session_id, "assistant", agent_name, data)
                        except Exception:
                            pass

                        if isinstance(msg, ApprovalRequest):
                            msg.resolve("approve")

                        if isinstance(msg, QuestionRequest):
                            await handle_question(websocket, msg, pending_questions)

                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                _save_session_meta(session_id, agent_name, mode="chat")
                await websocket.send_json({"type": "status", "status": "ready"})

            agent_task = asyncio.create_task(run_agent())

            # While agent is running, keep processing incoming messages (answers)
            while not agent_task.done():
                try:
                    raw2 = await asyncio.wait_for(incoming_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                if raw2 is None:
                    cancel_event.set()
                    break
                if raw2.get("type") == "answer":
                    qid = raw2.get("id")
                    qmsg = pending_questions.pop(qid, None)
                    if qmsg:
                        qmsg.resolve(raw2.get("answers", {}))

            await agent_task

    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()


@app.websocket("/ws/auto")
async def ws_auto(websocket: WebSocket):
    """
    WebSocket endpoint for auto-interaction mode.

    The client sends an initial prompt to video-auto-eval, which will then
    autonomously interact with video-director via ChatWithAgent tool.
    All wire events (including SubagentEvents) are streamed to the client.

    Protocol:
    - Client sends: {"type": "message", "content": "...", "session_id": "..."} (session_id optional)
    - Server sends: {"type": "session", "session_id": "..."}  (sent once after init)
    - Server sends: {"type": "wire", "agent": "video-auto-eval", "data": {...}}
    - Server sends: {"type": "status", "status": "ready"|"thinking"|"done"|"error"}
    """
    await websocket.accept()
    await websocket.send_json({"type": "status", "status": "initializing"})

    # Wait for first message to check for session_id
    first_raw = await websocket.receive_json()
    requested_session_id = first_raw.get("session_id")

    try:
        cli, resumed = await create_cli("video-auto-eval", session_id=requested_session_id)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Failed to create agent: {e}"})
        await websocket.close()
        return

    session_id = cli.session.id
    _save_session_meta(session_id, "video-auto-eval", mode="auto")
    await websocket.send_json({"type": "session", "session_id": session_id})

    resume_context = ""
    if resumed:
        summary = _build_session_summary(session_id)
        await websocket.send_json({"type": "resumed", "summary": summary})
        hints = []
        if summary.get("story_graph"):
            sg = summary["story_graph"]
            hints.append(f"Story Graph: {sg['characters']} characters, {sg['locations']} locations, {sg['events']} events, {sg['reference_images']} ref images (path: {sg['path']})")
        if summary.get("shot_plan"):
            hints.append(f"Shot Plan: {summary['shot_plan']['total_shots']} shots")
        if summary.get("clips"):
            hints.append(f"Video Clips: {summary['clips']} generated")
        if summary.get("images"):
            hints.append(f"Images: {summary['images']} generated")
        if hints:
            resume_context = "[Session resumed. Current project state:\n" + "\n".join(f"- {h}" for h in hints) + "\n]\n\n"

    await websocket.send_json({"type": "status", "status": "ready"})

    # Process the first message content
    first_content = first_raw.get("content", "") if first_raw.get("type") == "message" else ""
    messages_to_process = [first_content] if first_content else []

    try:
        while True:
            if not messages_to_process:
                raw = await websocket.receive_json()
                if raw.get("type") != "message":
                    continue
                content = raw.get("content", "")
                if not content:
                    continue
            else:
                content = messages_to_process.pop(0)

            # Inject resume context hint into the first user message after resume
            if resume_context:
                content = resume_context + content
                resume_context = ""

            _append_chat_log(session_id, "user", "user", content)
            await websocket.send_json({"type": "status", "status": "thinking"})
            cancel_event = asyncio.Event()

            try:
                async for msg in cli.run(content, cancel_event, merge_wire_messages=True):
                    try:
                        agent_label = "video-auto-eval"
                        # Detect SubagentEvents to label them as from the sub-agent
                        if isinstance(msg, SubagentEvent):
                            agent_label = "video-director"

                        data = serialize_wire_message(msg)
                        await websocket.send_json({
                            "type": "wire",
                            "agent": agent_label,
                            "data": data,
                        })
                        _append_chat_log(session_id, "assistant", agent_label, data)
                    except Exception:
                        pass

                    if isinstance(msg, ApprovalRequest):
                        msg.resolve("approve")
                    if isinstance(msg, QuestionRequest):
                        answers = {}
                        for q in msg.questions:
                            answers[q.question] = q.options[0].label if q.options else ""
                        msg.resolve(answers)

            except Exception as e:
                tb = traceback.format_exc()
                await websocket.send_json({"type": "error", "message": f"{e}\n{tb}"})

            _save_session_meta(session_id, "video-auto-eval", mode="auto")
            await websocket.send_json({"type": "status", "status": "ready"})

    except WebSocketDisconnect:
        pass


# Chat room: build @mention mapping from AGENT_FILES
# e.g. "video-director" -> mention alias "Director", "video-auto-eval" -> "Evaluator"
AGENT_MENTION_ALIASES: dict[str, str] = {}
for _agent_key in AGENT_FILES:
    # "video-director" -> "Director", "video-auto-eval" -> "Evaluator"
    _alias = _agent_key.split("-")[-1].capitalize()
    # Special case: "auto-eval" -> "Evaluator"
    if _agent_key == "video-auto-eval":
        _alias = "Evaluator"
    AGENT_MENTION_ALIASES[_alias.lower()] = _agent_key

# Build regex from aliases: @Director|@Evaluator|@All|...
_mention_pattern = "|".join(re.escape(a) for a in AGENT_MENTION_ALIASES)
MENTION_RE = re.compile(rf"@({_mention_pattern}|all)\b", re.IGNORECASE)


@app.get("/api/room/agents")
async def get_room_agents():
    """Return the list of agents available in the chat room."""
    agents = []
    for alias, agent_name in AGENT_MENTION_ALIASES.items():
        agents.append({"alias": alias.capitalize(), "name": agent_name})
    return {"agents": agents}


def _build_room_context(my_alias: str, all_agents: list[dict]) -> str:
    """Build a chat room context string to prepend to agent system prompts."""
    others = [a for a in all_agents if a["name"] != my_alias]
    other_list = ", ".join(f'@{a["alias"]}({a["name"]})' for a in others)
    all_list = ", ".join(f'@{a["alias"]}' for a in all_agents)
    return f"""
[CHAT ROOM CONTEXT]
You are in a multi-agent chat room with a human user (@User) and other agents: {other_list}.
Your name/alias in this room: @{next(a["alias"] for a in all_agents if a["name"] == my_alias)}.

Rules:
- Use @User when replying to or addressing the human user.
- Use {all_list} to address or reference other agents.
- The user may send messages to you specifically (via @mention), or broadcast to all agents.
- Keep your responses focused on your role. Don't repeat what other agents said.
- When you see messages from @User that also mention other agents, be aware they will also receive the same message.
[END CHAT ROOM CONTEXT]

"""


@app.websocket("/ws/room")
async def ws_room(websocket: WebSocket):
    """
    Multi-agent chat room WebSocket endpoint.

    Users can @mention agent aliases to target specific agents.
    Without @mention, the message is broadcast to all agents.

    Protocol:
    - Client sends: {"type": "message", "content": "...", "session_id": "..."} (session_id optional, first msg only)
    - Server sends: {"type": "session", "session_id": "..."}  (sent once after init)
    - Server sends: {"type": "wire", "agent": "<agent-name>", "data": {...}}
    - Server sends: {"type": "status", "agent": "<agent-name>", "status": "ready"|"thinking"|...}
    - Server sends: {"type": "error", "message": "..."}
    """
    await websocket.accept()
    await websocket.send_json({"type": "status", "status": "initializing"})

    # Wait for first message to check for session_id
    first_raw = await websocket.receive_json()
    requested_session_id = first_raw.get("session_id")

    # Build agent list for the room
    agent_list = [
        {"alias": alias.capitalize(), "name": name}
        for alias, name in AGENT_MENTION_ALIASES.items()
    ]

    # Use a shared session_id for the room
    session_id = requested_session_id or str(uuid.uuid4())

    clis: dict[str, KimiCLI] = {}
    try:
        for agent_name in AGENT_FILES:
            cli, _ = await create_cli(agent_name)
            clis[agent_name] = cli
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Failed to create agents: {e}"})
        await websocket.close()
        return

    _save_session_meta(session_id, "room", mode="room")
    await websocket.send_json({"type": "session", "session_id": session_id})

    # Inject chat room context into each agent's system prompt
    for agent_name, cli in clis.items():
        room_ctx = _build_room_context(agent_name, agent_list)
        agent = cli._soul._agent
        new_prompt = agent.system_prompt + "\n" + room_ctx
        object.__setattr__(agent, "system_prompt", new_prompt)

    await websocket.send_json({"type": "agents", "agents": agent_list})
    await websocket.send_json({"type": "status", "status": "ready"})

    # Background task management: agents run in background so user is never blocked
    running_tasks: set[asyncio.Task] = set()
    send_lock = asyncio.Lock()

    async def safe_send(data: dict):
        """Send JSON to websocket with a lock to prevent interleaved writes."""
        async with send_lock:
            await websocket.send_json(data)

    async def run_agent(agent_name: str, content: str):
        """Run a single agent and stream its wire messages to the client."""
        await safe_send({
            "type": "status", "agent": agent_name, "status": "thinking",
        })
        cancel_event = asyncio.Event()
        try:
            async for msg in clis[agent_name].run(content, cancel_event, merge_wire_messages=True):
                try:
                    data = serialize_wire_message(msg)
                    await safe_send({
                        "type": "wire", "agent": agent_name, "data": data,
                    })
                    _append_chat_log(session_id, "assistant", agent_name, data)
                except Exception:
                    pass

                if isinstance(msg, ApprovalRequest):
                    msg.resolve("approve")
                if isinstance(msg, QuestionRequest):
                    answers = {}
                    for q in msg.questions:
                        answers[q.question] = q.options[0].label if q.options else ""
                    msg.resolve(answers)
        except Exception as e:
            tb = traceback.format_exc()
            await safe_send({
                "type": "error", "agent": agent_name, "message": f"{e}\n{tb}",
            })
        _save_session_meta(session_id, "room", mode="room")
        await safe_send({
            "type": "status", "agent": agent_name, "status": "ready",
        })

    def _on_task_done(task: asyncio.Task):
        running_tasks.discard(task)

    # Queue of messages to process (first_raw is already received)
    pending_messages = []
    if first_raw.get("type") == "message" and first_raw.get("content", "").strip():
        pending_messages.append(first_raw)

    try:
        while True:
            if pending_messages:
                raw = pending_messages.pop(0)
            else:
                raw = await websocket.receive_json()
            if raw.get("type") != "message":
                continue

            content = raw.get("content", "").strip()
            if not content:
                continue

            _append_chat_log(session_id, "user", "user", content)

            # Parse @mentions to determine target agents
            mentions = set(m.lower() for m in MENTION_RE.findall(content))
            if 'all' in mentions:
                targets = list(clis.keys())
            elif mentions:
                targets = [AGENT_MENTION_ALIASES[m] for m in mentions if m in AGENT_MENTION_ALIASES]
            else:
                targets = list(clis.keys())

            # Launch agents in background - user can send more messages immediately
            for t in targets:
                task = asyncio.create_task(run_agent(t, content))
                running_tasks.add(task)
                task.add_done_callback(_on_task_done)

    except WebSocketDisconnect:
        # Cancel all running tasks on disconnect
        for task in running_tasks:
            task.cancel()
        await asyncio.gather(*running_tasks, return_exceptions=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
