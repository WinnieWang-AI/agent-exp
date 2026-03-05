# Video Creator Agent 设计文档

## 1. 设计思路

设计一个新 Agent 的思考路径：

```
1. 角色定位（体系层）      → 这个 Agent 在 Agent 体系中的位置
2. 能力边界（功能层）      → 需要什么新工具、什么领域知识
3. 子 Agent 策略（协作层） → 被谁调度、调度谁、隔离策略
4. 工具设计（实现层）      → Params、DI、返回值、Approval、SkipThisTool
5. 状态与交互（编排层）    → 异步状态流转、用户确认节点、工作流阶段
6. 配置 + Provider（基础设施层） → 外部服务配置、多后端抽象
```

### 1.1 角色定位

Video Creator Agent 是一个**领域专用 Agent**，继承 default agent 的通用能力（文件操作、Shell、搜索），新增视频创作领域的专用工具和工作流知识。

关键决策：`extend: default` — 获得所有基础工具，只新增 4 个视频专用工具。

### 1.2 能力边界

| 能力 | 是否需要新工具 | 原因 |
|------|:---:|------|
| 写脚本/分镜 JSON | 否 | LLM + 已有 WriteFile 工具 |
| 调用视频生成 API | **是** | 新的外部系统交互 |
| 查询生成任务状态 | **是** | 异步轮询外部 API |
| FFmpeg 剪辑 | **是** | 需要结构化参数，不宜暴露原始 FFmpeg 命令 |
| 管理项目目录 | **是** | 标准化目录结构 + 项目状态追踪 |

### 1.3 子 Agent 策略

**被调度（sub.yaml）**：video-creator 可以被其他 Agent（如 marketing Agent）通过 Task 工具调用。sub.yaml 继承 agent.yaml，排除 Task/SetTodoList 防止嵌套，注入子 Agent 角色说明。

**调度他人（subagents）**：继承 default 的 coder 子 Agent。视频创作主流程由 Agent 自身完成，不需要定义额外的专属子 Agent。coder 子 Agent 可以在需要时处理辅助性的代码/文件任务。

**隔离策略**：子 Agent 使用独立的 LaborMarket（`copy_for_fixed_subagent`），不继承视频工具——coder 子 Agent 不需要也不应该直接调用视频 API。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                  video-creator Agent                     │
│  (extends default, 继承基础工具 + 新增视频专用工具)        │
├─────────────────────────────────────────────────────────┤
│  System Prompt: 定义视频创作 3 阶段工作流                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │ 脚本 & 分镜   │ │ 素材生成     │ │ 剪辑 & 合成      │ │
│  │ (LLM+WriteFile)│ │ (GenerateVideo│ │ (VideoEdit      │ │
│  │              │ │  CheckVideoJob)│ │  via FFmpeg)     │ │
│  └──────────────┘ └──────┬───────┘ └──────────────────┘ │
│                          │                               │
│              ┌───────────▼────────────┐                  │
│              │  Video Provider 抽象层  │                  │
│              │  (Kling/Runway/Sora/...)│                  │
│              └────────────────────────┘                  │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 文件清单

### 3.1 新增文件

```
src/kimi_cli/
├── agents/video-creator/
│   ├── agent.yaml          # Agent 配置，extends default
│   ├── system.md           # 系统提示词，3 阶段工作流
│   └── sub.yaml            # 子 Agent 配置
└── tools/video/
    ├── __init__.py          # 导出 4 个工具类
    ├── generate.py          # GenerateVideo 工具
    ├── generate.md          # GenerateVideo 描述
    ├── check_job.py         # CheckVideoJob 工具
    ├── check_job.md         # CheckVideoJob 描述
    ├── edit.py              # VideoEdit 工具
    ├── edit.md              # VideoEdit 描述
    ├── project.py           # ManageVideoProject 工具
    ├── project.md           # ManageVideoProject 描述
    └── providers/
        ├── __init__.py      # Provider 工厂函数
        ├── base.py          # 抽象接口 + 数据模型
        ├── kling.py         # 可灵实现
        ├── runway.py        # Runway 实现（占位）
        ├── sora.py          # Sora 实现（占位）
        └── pika.py          # Pika 实现（占位）
```

### 3.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `src/kimi_cli/config.py` | 新增 `VideoProviderConfig`，Config 类新增 `video_providers` 字段 |
| `src/kimi_cli/agentspec.py` | 新增 `VIDEO_CREATOR_AGENT_FILE` 常量 |
| `src/kimi_cli/tools/__init__.py` | `extract_key_argument` 中添加 4 个视频工具的 case |

---

## 4. 配置设计

### 4.1 Config 模型

在 `config.py` 中新增：

```python
class VideoProviderConfig(BaseModel):
    """Video generation provider configuration."""

    type: str  # "kling" | "runway" | "sora" | "pika"
    """Provider type."""
    base_url: str = ""
    """API base URL."""
    api_key: SecretStr
    """API key."""
    custom_headers: dict[str, str] | None = None
    """Custom headers to include in API requests."""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()
```

Config 类新增字段：

```python
class Config(BaseModel):
    # ... 已有字段 ...
    video_providers: dict[str, VideoProviderConfig] = Field(
        default_factory=dict, description="Video generation providers"
    )
```

### 4.2 用户配置示例

```toml
# ~/.kimi/config.toml
[video_providers.kling]
type = "kling"
base_url = "https://api.klingai.com"
api_key = "sk-..."

[video_providers.runway]
type = "runway"
base_url = "https://api.dev.runwayml.com"
api_key = "rk-..."
```

---

## 5. Provider 抽象层

### 5.1 抽象接口（`providers/base.py`）

```python
from abc import ABC, abstractmethod
from enum import Enum
from pydantic import BaseModel


class VideoJobState(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationRequest(BaseModel):
    mode: str          # "text_to_video" | "image_to_video"
    prompt: str
    duration_seconds: float
    aspect_ratio: str  # "16:9" | "9:16" | "1:1"
    reference_image_path: str = ""
    style: str = ""
    negative_prompt: str = ""


class VideoJobSubmission(BaseModel):
    job_id: str
    provider: str
    estimated_seconds: float


class VideoJobStatus(BaseModel):
    job_id: str
    state: VideoJobState
    progress_percent: float = 0.0
    result_url: str = ""
    error_message: str = ""


class VideoProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def submit_job(self, request: GenerationRequest) -> VideoJobSubmission: ...

    @abstractmethod
    async def check_job(self, job_id: str) -> VideoJobStatus: ...

    @abstractmethod
    async def download_result(self, result_url: str, output_path: str) -> None: ...
```

### 5.2 工厂函数（`providers/__init__.py`）

参考 `llm.py` 的 `create_llm()` 模式：

```python
from kimi_cli.config import VideoProviderConfig
from .base import VideoProvider


def create_video_provider(name: str, config: VideoProviderConfig) -> VideoProvider:
    match config.type:
        case "kling":
            from .kling import KlingProvider
            return KlingProvider(name=name, config=config)
        case "runway":
            from .runway import RunwayProvider
            return RunwayProvider(name=name, config=config)
        case "sora":
            from .sora import SoraProvider
            return SoraProvider(name=name, config=config)
        case "pika":
            from .pika import PikaProvider
            return PikaProvider(name=name, config=config)
        case _:
            raise ValueError(f"Unknown video provider type: {config.type}")
```

---

## 6. 四个工具设计

### 6.1 GenerateVideo

**职责**：向视频生成 API 提交异步任务，立即返回 job_id（不阻塞）。

```python
class Params(BaseModel):
    prompt: str = Field(description="Detailed description of the video content.")
    mode: str = Field(default="text_to_video", description='"text_to_video" or "image_to_video"')
    duration_seconds: float = Field(default=5.0, ge=1.0, le=60.0, description="Video duration.")
    aspect_ratio: str = Field(default="16:9", description='"16:9", "9:16", or "1:1"')
    provider: str = Field(description="Provider name matching config, e.g. 'kling'.")
    reference_image_path: str = Field(default="", description="Reference image for image_to_video mode.")
    style: str = Field(default="", description='Style hint: "cinematic", "anime", "realistic", etc.')
    negative_prompt: str = Field(default="", description="Content to exclude.")
```

**DI 依赖**：`Config`（读取 video_providers）、`Approval`（请求用户确认，视频生成有 API 成本）

**Approval**：每次提交前请求用户确认 — `"Generate video with {provider}: {prompt[:50]}..."`

**SkipThisTool**：`if not config.video_providers: raise SkipThisTool()`

**返回值**：`ToolOk(output=json.dumps({"job_id": ..., "provider": ..., "estimated_seconds": ...}))`

### 6.2 CheckVideoJob

**职责**：查询生成任务状态，完成时可自动下载到本地。

```python
class Params(BaseModel):
    job_id: str = Field(description="Job ID returned by GenerateVideo.")
    provider: str = Field(description="Provider name.")
    download_path: str = Field(default="", description="Download path when completed. Empty to only check status.")
```

**DI 依赖**：`Config`（读取 provider 配置创建 provider 实例）

**SkipThisTool**：与 GenerateVideo 相同条件

**返回值**：`ToolOk(output=json.dumps({"job_id": ..., "state": ..., "progress_percent": ..., "downloaded_to": ...}))`

### 6.3 VideoEdit

**职责**：通过 FFmpeg 执行结构化视频编辑操作。使用 discriminated union 区分 5 种操作。

```python
class ConcatOp(BaseModel):
    operation: Literal["concat"] = "concat"
    input_files: list[str] = Field(min_length=2, description="Video files to concatenate in order.")
    output_file: str

class TrimOp(BaseModel):
    operation: Literal["trim"] = "trim"
    input_file: str
    start_time: str = Field(description='Start time, e.g. "00:00:05" or "5.0"')
    end_time: str = Field(description='End time, e.g. "00:00:15" or "15.0"')
    output_file: str

class AddAudioOp(BaseModel):
    operation: Literal["add_audio"] = "add_audio"
    video_file: str
    audio_file: str
    output_file: str
    mix: bool = Field(default=False, description="Mix with existing audio instead of replacing.")

class AddSubtitlesOp(BaseModel):
    operation: Literal["add_subtitles"] = "add_subtitles"
    video_file: str
    subtitle_file: str  # SRT file path
    output_file: str

class TransitionOp(BaseModel):
    operation: Literal["transition"] = "transition"
    input_file_1: str
    input_file_2: str
    output_file: str
    transition_type: str = Field(default="fade", description='"fade", "dissolve", "wipe", etc.')
    duration: float = Field(default=1.0, description="Transition duration in seconds.")

class Params(BaseModel):
    operation: ConcatOp | TrimOp | AddAudioOp | AddSubtitlesOp | TransitionOp = Field(
        discriminator="operation"
    )
```

**DI 依赖**：`Approval`（确认执行 FFmpeg 命令）

**Approval**：展示将要执行的操作描述（不暴露原始 FFmpeg 命令）

**内部实现**：每种操作构建对应的 FFmpeg 命令，通过 `kaos.exec` 执行子进程

### 6.4 ManageVideoProject

**职责**：初始化项目目录结构、查询项目状态、更新元数据。

```python
class Params(BaseModel):
    action: str = Field(description='"init", "status", or "update_metadata"')
    project_name: str = Field(description="Project name (used as directory name).")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata for update_metadata action.")
```

**DI 依赖**：无额外依赖（纯文件操作）

**init 创建的目录结构**：

```
<project_name>/
  project.json          # 项目元数据（标题、创建时间、状态等）
  script.json           # 视频脚本（LLM 通过 WriteFile 写入）
  storyboard.json       # 分镜头脚本（LLM 通过 WriteFile 写入）
  assets/
    clips/              # 生成的视频片段
    images/             # 参考图片
    audio/              # 音乐、配音、音效
  output/               # 最终输出视频
```

---

## 7. Agent 定义

### 7.1 agent.yaml

```yaml
version: 1
agent:
  extend: default
  name: "video-creator"
  system_prompt_path: ./system.md
  system_prompt_args:
    ROLE_ADDITIONAL: ""
  tools:
    # 继承 default 的所有工具
    - "kimi_cli.tools.multiagent:Task"
    - "kimi_cli.tools.ask_user:AskUserQuestion"
    - "kimi_cli.tools.todo:SetTodoList"
    - "kimi_cli.tools.shell:Shell"
    - "kimi_cli.tools.file:ReadFile"
    - "kimi_cli.tools.file:ReadMediaFile"
    - "kimi_cli.tools.file:Glob"
    - "kimi_cli.tools.file:Grep"
    - "kimi_cli.tools.file:WriteFile"
    - "kimi_cli.tools.file:StrReplaceFile"
    - "kimi_cli.tools.web:SearchWeb"
    - "kimi_cli.tools.web:FetchURL"
    # 视频专用工具
    - "kimi_cli.tools.video:GenerateVideo"
    - "kimi_cli.tools.video:CheckVideoJob"
    - "kimi_cli.tools.video:VideoEdit"
    - "kimi_cli.tools.video:ManageVideoProject"
  subagents:
    coder:
      path: ../default/sub.yaml
      description: "Good at general software engineering tasks."
```

### 7.2 sub.yaml

```yaml
version: 1
agent:
  extend: ./agent.yaml
  system_prompt_args:
    ROLE_ADDITIONAL: |
      You are now running as a subagent. All the `user` messages are sent by the main agent.
      The main agent cannot see your context, it can only see your last message when you finish the task.
      You need to provide a comprehensive summary on what you have done and learned in your final message.
      If you wrote or modified any files, you must mention them in the summary.
  exclude_tools:
    - "kimi_cli.tools.multiagent:Task"
    - "kimi_cli.tools.todo:SetTodoList"
  subagents:
```

### 7.3 system.md 核心结构

```markdown
You are Kimi Video Creator, a specialized AI agent for end-to-end video production.

${ROLE_ADDITIONAL}

# Video Creation Workflow

You create videos in 3 phases. Always follow this order.

## Phase 1 - Script & Storyboard

1. Understand the user's requirements (topic, style, duration, audience).
2. Use AskUserQuestion if anything is unclear.
3. Use ManageVideoProject(init) to create the project directory.
4. Write `script.json` via WriteFile — overall narrative structure.
5. Write `storyboard.json` via WriteFile — per-shot breakdown with prompts.
6. **STOP and present the storyboard to the user. Wait for confirmation before Phase 2.**

## Phase 2 - Asset Generation

1. For each shot in storyboard, call GenerateVideo (submit in parallel where possible).
2. Poll with CheckVideoJob until all jobs complete.
3. Download completed clips to `assets/clips/`.
4. Use ReadMediaFile to verify clip quality.
5. If a clip is unsatisfactory, regenerate with adjusted prompts.

## Phase 3 - Editing & Assembly

1. VideoEdit(concat) — assemble clips in sequence.
2. VideoEdit(add_audio) — add background music / voiceover.
3. VideoEdit(add_subtitles) — burn in SRT subtitles if needed.
4. VideoEdit(transition) — add transitions between scenes if needed.
5. Export to `output/`.
6. Use ReadMediaFile to verify the final video.
7. **Report completion to the user with the output file path.**

# User Confirmation Points

- After Phase 1 (storyboard review) — confirm before spending API credits.
- After Phase 3 (final video) — confirm the result is acceptable.

# [继承 default system.md 的通用部分: Prompt and Tool Use, Working Environment, etc.]
```

---

## 8. 状态与交互设计

### 8.1 异步状态流转

```
GenerateVideo → 返回 {job_id, provider} → LLM 上下文记住
                                            ↓
CheckVideoJob(job_id, provider) → 返回 {state, progress}
                                            ↓
                                   state == completed?
                                   ├── yes → download_path → 文件路径进入 LLM 上下文
                                   └── no  → Agent 等待后重新查询
```

job_id 的状态由 LLM 上下文自然维护。`project.json` 作为持久化备份，Agent 可以通过 `ManageVideoProject(status)` 恢复中断的项目。

### 8.2 用户确认节点

| 节点 | 触发方式 | 原因 |
|------|---------|------|
| 分镜确认 | Agent 主动展示 storyboard 并等待回复 | 确认创意方向再花钱 |
| 视频生成 | Approval 系统拦截每次 GenerateVideo 调用 | API 成本控制 |
| FFmpeg 执行 | Approval 系统拦截每次 VideoEdit 调用 | 确认编辑操作 |

---

## 9. 实施计划

### Phase 1: 配置 + Provider 抽象层

**涉及文件**：`config.py`, `tools/video/providers/`

1. 在 `config.py` 中新增 `VideoProviderConfig` 和 `Config.video_providers`
2. 创建 `tools/video/providers/base.py` — 抽象接口 + 数据模型
3. 创建 `tools/video/providers/__init__.py` — 工厂函数
4. 创建 `tools/video/providers/kling.py` — 第一个完整实现
5. 创建 `tools/video/providers/runway.py`, `sora.py`, `pika.py` — 占位实现

### Phase 2: 核心工具 (GenerateVideo, CheckVideoJob, ManageVideoProject)

**涉及文件**：`tools/video/`

1. 创建 `tools/video/__init__.py` — 导出 4 个工具类
2. 实现 `GenerateVideo`（generate.py + generate.md）
3. 实现 `CheckVideoJob`（check_job.py + check_job.md）
4. 实现 `ManageVideoProject`（project.py + project.md）

### Phase 3: VideoEdit 工具

**涉及文件**：`tools/video/edit.py`, `tools/video/edit.md`

1. 定义 5 种操作的 Params 模型（discriminated union）
2. 实现每种操作的 FFmpeg 命令构建
3. 通过 `kaos.exec` 执行子进程

### Phase 4: Agent 接入

**涉及文件**：`agents/video-creator/`, `agentspec.py`, `tools/__init__.py`

1. 创建 `agents/video-creator/agent.yaml`
2. 创建 `agents/video-creator/system.md`
3. 创建 `agents/video-creator/sub.yaml`
4. 在 `agentspec.py` 中新增 `VIDEO_CREATOR_AGENT_FILE` 常量
5. 在 `tools/__init__.py` 的 `extract_key_argument` 中添加 4 个视频工具
