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


class StoryGraphProductionStyle(BaseModel):
    id: str
    description: str = ""
    style_prefix: str = ""
    negative_prefix: str = ""
    aspect_ratio: str = "16:9"
    duration: str = ""


class StoryGraphState(BaseModel):
    """State node under an entity (appearance / location_state / prop_state)."""

    id: str
    phase: str = ""
    reference_image: str = ""


class StoryGraphEntity(BaseModel):
    id: str
    name: str
    kind: Literal["character", "location", "prop"]
    reference_image: str = ""
    states: list[StoryGraphState] = []


class StoryGraphShot(BaseModel):
    shot_id: str
    order: int
    shot_type: str = ""
    intent: str = ""
    focus_on: list[str] = []
    techniques: list[str] = []
    video_clip: str = ""
    reference_images: list[str] = []
    first_frame: str = ""
    tail_frame: str = ""


class StoryGraphAudioState(BaseModel):
    """Audio state active during an event."""

    id: str
    layer: str = ""
    phase: str = ""
    text: str = ""
    speaker: str = ""
    audio_file: str = ""


class StoryGraphInteraction(BaseModel):
    """Interaction between characters within an event."""

    between: list[str] = []
    style: str = ""


class StoryGraphOutput(BaseModel):
    """An assembled output video."""

    stage: str = ""
    video_path: str = ""
    label: str = ""


class StoryGraphEvent(BaseModel):
    id: str
    description: str = ""
    happens_at: str = ""
    character_ids: list[str] = []
    shots: list[StoryGraphShot] = []
    interactions: list[StoryGraphInteraction] = []
    audio_states: list[StoryGraphAudioState] = []


class StoryGraphViewDisplayBlock(DisplayBlock):
    """Display block for the Story Graph visualization."""

    type: str = "story_graph_view"
    phase: str = "skeleton"
    production_styles: list[StoryGraphProductionStyle] = []
    entities: list[StoryGraphEntity] = []
    timeline: list[StoryGraphEvent] = []
    parallel_groups: list[list[str]] = []
    summary: dict[str, Any] = {}
    outputs: list[StoryGraphOutput] = []
