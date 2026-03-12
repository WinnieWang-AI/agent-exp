from typing import Any, Literal

from kosong.tooling import DisplayBlock
from pydantic import BaseModel


class DiffDisplayBlock(DisplayBlock):
    """Display block describing a file diff."""

    type: str = "diff"
    path: str
    old_text: str
    new_text: str


class TodoDisplayItem(BaseModel):
    title: str
    status: Literal["pending", "in_progress", "done"]


class TodoDisplayBlock(DisplayBlock):
    """Display block describing a todo list update."""

    type: str = "todo"
    items: list[TodoDisplayItem]


class ShellDisplayBlock(DisplayBlock):
    """Display block describing a shell command."""

    type: str = "shell"
    language: str
    command: str


# ---------------------------------------------------------------------------
# Story Graph View
# ---------------------------------------------------------------------------


class StoryGraphEntity(BaseModel):
    id: str
    name: str
    kind: Literal["character", "location", "prop"]
    reference_image: str = ""


class StoryGraphShot(BaseModel):
    shot_id: str
    order: int
    shot_type: str = ""
    intent: str = ""
    focus_on: list[str] = []
    techniques: list[str] = []
    video_clip: str = ""


class StoryGraphEvent(BaseModel):
    id: str
    description: str = ""
    happens_at: str = ""
    character_ids: list[str] = []
    shots: list[StoryGraphShot] = []


class StoryGraphViewDisplayBlock(DisplayBlock):
    """Display block for the Story Graph visualization."""

    type: str = "story_graph_view"
    phase: str = "skeleton"
    entities: list[StoryGraphEntity] = []
    timeline: list[StoryGraphEvent] = []
    parallel_groups: list[list[str]] = []
    summary: dict[str, Any] = {}
