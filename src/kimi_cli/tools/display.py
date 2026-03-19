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


class StoryGraphVideoInfo(BaseModel):
    """Global video specs — singular, not per-event."""

    aspect_ratio: str = ""
    duration: str = ""
    language: str = ""


class StoryGraphProductionStyle(BaseModel):
    id: str
    description: str = ""
    style_prefix: str = ""
    negative_prefix: str = ""


class StoryGraphState(BaseModel):
    """State node under an entity (appearance / location_state / prop_state)."""

    id: str
    phase: str = ""
    reference_image: str = ""
    description: str = ""
    generation_prompt: str = ""


class StoryGraphEntity(BaseModel):
    id: str
    name: str
    kind: Literal["character", "location", "prop"]
    reference_image: str = ""
    description: str = ""
    generation_prompt: str = ""
    states: list[StoryGraphState] = []


class StoryGraphShot(BaseModel):
    shot_id: str
    order: int
    shot_type: str = ""
    angle: str = ""
    movement: str = ""
    intent: str = ""
    focus_on: list[str] = []
    is_continuation: bool = False
    sequence_prev_shot_id: str = ""
    sequence_tail_frame: str = ""
    mode: str = ""
    prompt: str = ""
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


class StoryGraphMind(BaseModel):
    """Character mind/emotion state active during an event."""

    id: str
    entity: str = ""
    entity_name: str = ""
    phase: str = ""
    emotion: str = ""
    behavior: str = ""


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
    active_appearance_ids: list[str] = []
    minds: list[StoryGraphMind] = []
    shots: list[StoryGraphShot] = []
    interactions: list[StoryGraphInteraction] = []
    audio_states: list[StoryGraphAudioState] = []


class StoryGraphViewDisplayBlock(DisplayBlock):
    """Display block for the Story Graph visualization."""

    type: str = "story_graph_view"
    phase: str = "skeleton"
    video_info: StoryGraphVideoInfo | None = None
    production_styles: list[StoryGraphProductionStyle] = []
    entities: list[StoryGraphEntity] = []
    timeline: list[StoryGraphEvent] = []
    parallel_groups: list[list[str]] = []
    summary: dict[str, Any] = {}
    outputs: list[StoryGraphOutput] = []


# ---------------------------------------------------------------------------
# Agent Graph View
# ---------------------------------------------------------------------------


class AgentGraphNode(BaseModel):
    """A node in the agent topology graph."""

    id: str
    name: str
    tools: list[str] = []
    tool_count: int = 0
    subagent_count: int = 0


class AgentGraphEdge(BaseModel):
    """An edge between agents in the topology graph."""

    source: str
    target: str
    edge_type: Literal["SUBAGENT", "CHAT_WITH"]
    description: str = ""


class AgentGraphTopology(BaseModel):
    """Full agent topology."""

    nodes: list[AgentGraphNode]
    edges: list[AgentGraphEdge]


class WorkflowStep(BaseModel):
    """A step in an agent's workflow."""

    id: str
    label: str
    kind: Literal["begin", "end", "task", "decision", "user_confirm"]
    agent_call: str | None = None
    description: str = ""


class WorkflowEdge(BaseModel):
    """A connection between workflow steps."""

    source: str
    target: str
    label: str = ""
    is_loop: bool = False


class WorkflowConstraint(BaseModel):
    """An explicit constraint extracted from the agent's prompt."""

    id: str
    rule: str
    applies_to: list[str] = []
    check_type: Literal["keyword", "parameter", "count", "semantic"] = "semantic"


class AgentWorkflow(BaseModel):
    """An agent's extracted workflow."""

    agent_id: str
    steps: list[WorkflowStep]
    edges: list[WorkflowEdge]
    constraints: list[WorkflowConstraint] = []
    max_loops: dict[str, int] = {}
    warnings: list[str] = []


class TraceDeviation(BaseModel):
    """A deviation annotated on a specific trace call."""

    constraint_id: str = ""
    rule: str
    severity: Literal["info", "warning", "error"]
    expected: str = ""
    actual: str = ""
    evidence: str = ""


class TraceCall(BaseModel):
    """A single call in a step trace."""

    seq: int
    role: Literal["assistant", "tool", "user"]
    thinking: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = {}
    tool_result: str = ""
    token_usage: int = 0
    deviations: list[TraceDeviation] = []


class StepTrace(BaseModel):
    """Execution trace for one iteration of a workflow step."""

    step_id: str
    iteration: int = 1
    calls: list[TraceCall]
    expected_intent: str = ""
    applicable_rules: list[str] = []
    total_tool_calls: int = 0
    total_tokens: int = 0


class StepDeviation(BaseModel):
    """A step-level deviation (Layer 1: flow ordering)."""

    step_id: str
    deviation_type: Literal["skipped", "out_of_order", "loop_exceeded", "missing", "unexpected"]
    severity: Literal["info", "warning", "error"]
    description: str
    expected: str = ""
    actual: str = ""


class DeviationReport(BaseModel):
    """Full deviation report combining all layers."""

    agent_id: str
    step_deviations: list[StepDeviation] = []
    summary: dict[str, int] = {}


class AgentGraphViewDisplayBlock(DisplayBlock):
    """Display block for the Agent Graph visualization."""

    type: str = "agent_graph_view"
    topology: AgentGraphTopology = AgentGraphTopology(nodes=[], edges=[])
    workflow: AgentWorkflow | None = None
    deviation_report: DeviationReport | None = None
    traces: dict[str, list[StepTrace]] = {}
    summary: dict[str, Any] = {}
