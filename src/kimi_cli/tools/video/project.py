import json
from pathlib import Path
from typing import Any

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.soul.agent import Runtime
from kimi_cli.tools.utils import ToolResultBuilder, load_desc


class Params(BaseModel):
    action: str = Field(description='Action to perform: "init", "status", or "update_metadata"')
    project_path: str = Field(description="Path to the video project directory")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Project metadata (used with init and update_metadata actions)",
    )


# Standard project directory structure
_PROJECT_DIRS = [
    "assets/shots",
    "assets/images",
    "assets/frames",
    "assets/audio",
    "output",
]

_PROJECT_FILES: list[str] = []


class ManageVideoProject(CallableTool2[Params]):
    name: str = "ManageVideoProject"
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        super().__init__(description=load_desc(Path(__file__).parent / "project.md"))
        self._work_dir = runtime.session.work_dir

    async def __call__(self, params: Params) -> ToolReturnValue:
        project = Path(params.project_path)
        if not project.is_absolute():
            project = Path(str(self._work_dir)) / project

        match params.action:
            case "init":
                return await self._init_project(project, params.metadata)
            case "status":
                return await self._get_status(project)
            case "update_metadata":
                return await self._update_metadata(project, params.metadata)
            case _:
                builder = ToolResultBuilder()
                return builder.error(
                    message=f'Unknown action: "{params.action}". Use "init", "status", or "update_metadata".',
                    brief="Unknown action",
                )

    async def _init_project(
        self, project: Path, metadata: dict[str, Any]
    ) -> ToolReturnValue:
        builder = ToolResultBuilder()
        project.mkdir(parents=True, exist_ok=True)

        for d in _PROJECT_DIRS:
            (project / d).mkdir(parents=True, exist_ok=True)

        for f in _PROJECT_FILES:
            fp = project / f
            if not fp.exists():
                fp.write_text("[]", encoding="utf-8")

        project_json = project / "project.json"
        project_name = project.name
        project_data = {
            "name": project_name,
            "status": "initialized",
            "story_graph_path": str(project / "story-graph.json"),
            "shot_plan_path": str(project / "shot-plan.json"),
            "session_ids": {
                "graph": f"graph_{project_name}",
                "create_image": f"create_image_{project_name}",
                "create": f"create_{project_name}",
                "create_audio": f"create_audio_{project_name}",
                "eval": f"eval_{project_name}",
            },
            **metadata,
        }
        project_json.write_text(
            json.dumps(project_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        builder.write(f"Project initialized at: {project}\n")
        builder.write("Created directories:\n")
        for d in _PROJECT_DIRS:
            builder.write(f"  - {d}/\n")
        builder.write("Created files:\n")
        for f in [*_PROJECT_FILES, "project.json"]:
            builder.write(f"  - {f}\n")
        return builder.ok(message="Project initialized successfully.")

    async def _get_status(self, project: Path) -> ToolReturnValue:
        builder = ToolResultBuilder()

        project_json = project / "project.json"
        if not project_json.exists():
            return builder.error(
                message=f"Not a video project directory: {project} (project.json not found)",
                brief="Not a project",
            )

        data = json.loads(project_json.read_text(encoding="utf-8"))
        builder.write(f"Project: {project}\n")
        builder.write(f"Metadata: {json.dumps(data, ensure_ascii=False, indent=2)}\n\n")

        shots_dir = project / "assets" / "shots"
        images_dir = project / "assets" / "images"
        frames_dir = project / "assets" / "frames"
        audio_dir = project / "assets" / "audio"
        output_dir = project / "output"

        for label, d in [
            ("Shots", shots_dir),
            ("Images", images_dir),
            ("Frames", frames_dir),
            ("Audio", audio_dir),
            ("Output", output_dir),
        ]:
            if d.exists():
                files = list(d.iterdir())
                builder.write(f"{label}: {len(files)} file(s)\n")
                for f in files[:10]:
                    builder.write(f"  - {f.name}\n")
            else:
                builder.write(f"{label}: directory not found\n")

        return builder.ok(message="Project status retrieved.")

    async def _update_metadata(
        self, project: Path, metadata: dict[str, Any]
    ) -> ToolReturnValue:
        builder = ToolResultBuilder()

        project_json = project / "project.json"
        if not project_json.exists():
            return builder.error(
                message=f"Not a video project directory: {project}",
                brief="Not a project",
            )

        data = json.loads(project_json.read_text(encoding="utf-8"))
        data.update(metadata)
        project_json.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        builder.write(f"Updated metadata: {json.dumps(data, ensure_ascii=False, indent=2)}\n")
        return builder.ok(message="Metadata updated successfully.")
