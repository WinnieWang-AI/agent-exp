"""
Web server for interacting with video-director and video-auto-eval agents.

Provides:
- WebSocket endpoints for real-time agent communication
- Three modes: chat with director, chat with auto-eval, auto-interaction mode
"""

from __future__ import annotations

import asyncio
import json
import re
import traceback
from pathlib import Path
from typing import Any

import mimetypes

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from kaos.path import KaosPath

from kimi_cli.agentspec import VIDEO_DIRECTOR_AGENT_FILE, VIDEO_AUTO_EVAL_AGENT_FILE, AGENT_OPTIMIZER_AGENT_FILE
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

WORK_DIR = KaosPath.unsafe_from_local_path(Path.cwd())

AGENT_FILES = {
    "video-director": VIDEO_DIRECTOR_AGENT_FILE,
    "video-auto-eval": VIDEO_AUTO_EVAL_AGENT_FILE,
    "agent-optimizer": AGENT_OPTIMIZER_AGENT_FILE,
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


def serialize_wire_message(msg: Any) -> dict:
    """Convert a WireMessage to a JSON-serializable dict."""
    envelope = WireMessageEnvelope.from_wire_message(msg)
    return envelope.model_dump(mode="json")


async def create_cli(agent_name: str) -> KimiCLI:
    """Create a KimiCLI instance for the given agent."""
    agent_file = AGENT_FILES[agent_name]
    session = await Session.create(WORK_DIR)
    cli = await KimiCLI.create(
        session,
        agent_file=agent_file,
        yolo=True,  # auto-approve in web UI
    )
    return cli


@app.websocket("/ws/chat/{agent_name}")
async def ws_chat(websocket: WebSocket, agent_name: str):
    """
    WebSocket endpoint for chatting with a single agent.

    Protocol:
    - Client sends: {"type": "message", "content": "..."}
    - Server sends: {"type": "wire", "data": {...}}  (wire message envelope)
    - Server sends: {"type": "status", "status": "ready"|"thinking"|"done"|"error"}
    - Server sends: {"type": "error", "message": "..."}
    """
    if agent_name not in AGENT_FILES:
        await websocket.close(code=4000, reason=f"Unknown agent: {agent_name}")
        return

    await websocket.accept()
    await websocket.send_json({"type": "status", "status": "initializing"})

    try:
        cli = await create_cli(agent_name)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Failed to create agent: {e}"})
        await websocket.close()
        return

    await websocket.send_json({"type": "status", "status": "ready"})

    try:
        while True:
            raw = await websocket.receive_json()
            if raw.get("type") != "message":
                continue

            content = raw.get("content", "")
            if not content:
                continue

            await websocket.send_json({"type": "status", "status": "thinking"})
            cancel_event = asyncio.Event()

            try:
                async for msg in cli.run(content, cancel_event, merge_wire_messages=True):
                    try:
                        data = serialize_wire_message(msg)
                        await websocket.send_json({"type": "wire", "data": data})
                    except Exception:
                        pass  # skip unserializable messages

                    # Auto-approve any approval requests
                    if isinstance(msg, ApprovalRequest):
                        msg.resolve("approve")

                    # Auto-answer question requests
                    if isinstance(msg, QuestionRequest):
                        answers = {}
                        for q in msg.questions:
                            answers[q.question] = q.options[0].label if q.options else ""
                        msg.resolve(answers)

            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})

            await websocket.send_json({"type": "status", "status": "ready"})

    except WebSocketDisconnect:
        pass


@app.websocket("/ws/auto")
async def ws_auto(websocket: WebSocket):
    """
    WebSocket endpoint for auto-interaction mode.

    The client sends an initial prompt to video-auto-eval, which will then
    autonomously interact with video-director via ChatWithAgent tool.
    All wire events (including SubagentEvents) are streamed to the client.

    Protocol:
    - Client sends: {"type": "message", "content": "..."}
    - Server sends: {"type": "wire", "agent": "video-auto-eval", "data": {...}}
    - Server sends: {"type": "status", "status": "ready"|"thinking"|"done"|"error"}
    """
    await websocket.accept()
    await websocket.send_json({"type": "status", "status": "initializing"})

    try:
        cli = await create_cli("video-auto-eval")
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Failed to create agent: {e}"})
        await websocket.close()
        return

    await websocket.send_json({"type": "status", "status": "ready"})

    try:
        while True:
            raw = await websocket.receive_json()
            if raw.get("type") != "message":
                continue

            content = raw.get("content", "")
            if not content:
                continue

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
    - Client sends: {"type": "message", "content": "..."}
    - Server sends: {"type": "wire", "agent": "<agent-name>", "data": {...}}
    - Server sends: {"type": "status", "agent": "<agent-name>", "status": "ready"|"thinking"|...}
    - Server sends: {"type": "error", "message": "..."}
    """
    await websocket.accept()
    await websocket.send_json({"type": "status", "status": "initializing"})

    # Build agent list for the room
    agent_list = [
        {"alias": alias.capitalize(), "name": name}
        for alias, name in AGENT_MENTION_ALIASES.items()
    ]

    clis: dict[str, KimiCLI] = {}
    try:
        for agent_name in AGENT_FILES:
            clis[agent_name] = await create_cli(agent_name)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Failed to create agents: {e}"})
        await websocket.close()
        return

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
        await safe_send({
            "type": "status", "agent": agent_name, "status": "ready",
        })

    def _on_task_done(task: asyncio.Task):
        running_tasks.discard(task)

    try:
        while True:
            raw = await websocket.receive_json()
            if raw.get("type") != "message":
                continue

            content = raw.get("content", "").strip()
            if not content:
                continue

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
