# 视频制作 Agent 体系重构

## 背景

旧架构中 video-director 一个 agent 承担了用户沟通、项目管理、创作指导、工作流调度等所有职责，导致：
- 职责混乱，无法产出高一致性视频
- 视频和音频分开规划，缺少统一的视听规划环节
- 编剧在做摄影指导和声音设计的工作
- 导演不做创作决策，只是机械转发
- story-graph.json 格式过载，既存叙事又存镜头又存资源路径
- 修改成本高，改一处需要重新生成大量内容

## 设计原则

仿照现实影视制作分工，每个 agent 对应一个明确的工种角色：

| 角色 | Agent | 职责 | 决策权 |
|------|-------|------|--------|
| **制片人 (Producer)** | video-producer | 用户沟通、需求确认、调度协调、进度管理 | 做不做、做什么 |
| **编剧 (Screenwriter)** | video-screenwriter | 故事结构、角色设定、场景设计、对白 | 故事怎么讲 |
| **导演 (Director)** | video-director | 事件拆解、状态规划、镜头设计、视听统一规划 | 怎么拍 |
| **美术 (Art Designer)** | art-designer | 视觉风格、参考图生成 | 画面什么样 |
| **摄影 (Camera)** | video-camera | 逐 shot 视频生成（画面+同期声）、prompt 组合、生成模式决策 | 画面怎么生成 |
| **作曲 (Composer)** | video-composer | BGM 创作、音乐 prompt 编写 | 音乐什么样 |
| **剪辑 (Editor)** | video-editor | 成片组装、转场、BGM 叠加、字幕 | 怎么剪 |

## 架构总览

```
video-producer (制片人)
  ├── video-screenwriter (编剧)        — 剧本创作
  ├── video-director (导演)            — 制作计划
  ├── video-audience (观众)            — 制作计划审查
  ├── art-designer (美术)              — 参考图生成
  ├── video-camera (摄影)              — 逐 shot 视频生成
  ├── video-composer (作曲)            — BGM 生成
  └── video-editor (剪辑)             — 后期组装
```

**数据流：**

```
用户需求
  → Producer: 需求确认、项目初始化
  → Screenwriter: meta.json / entities.json / outline.json / act-N.json
  → Director: events.json / states.json / shots.json / assets/images/
  → Camera + Composer (并行):
      Camera: shots.json + states.json + 参考图 → assets/shots/{shot_id}.mp4
      Composer: shots.json + meta.json → assets/audio/bgm_*.mp3
  → Editor: 视频片段 + BGM → output/attempt_{N}.mp4
```

**关键设计点：**
- 对白和音效由视频模型在生成时通过 prompt 一并产出（同期声），不走 TTS。Camera agent 在 prompt 中写入对白文本和音效描述
- BGM 是独立的音乐生成（Suno），与视频生成并行，由 Composer 负责 prompt 编写和候选挑选
- Editor 负责最终组装：拼接视频、叠加 BGM、生成并烧录字幕

## 实施策略

增量实施，从顶层到底层：
1. Producer（已完成）
2. Screenwriter（已完成）
3. Director + Art Designer（已完成）
4. Camera + Composer + Editor（下一步）

## 已完成

### 1. Video Producer (`src/kimi_cli/agents/video-producer/`)

顶层 agent，与用户直接对话。

**文件：**
- `agent.yaml` — 工具：Task, ReadFile, WriteFile, Glob, Grep, ManageVideoProject；subagent：video-screenwriter, video-director, video-audience, art-designer, video-camera, video-composer, video-editor
- `system.md` — L0 身份层，制片人角色定义
- `compact.md` — 上下文压缩模板
- `workflow-setup.md` — L1 流程：需求确认 → 项目初始化 → 调度编剧
- `workflow-production.md` — L1 流程：调度导演 → 观众审查 → 调度美术
- `workflow-execution.md` — L1 流程：调度摄影+作曲（并行）→ 剪辑 → 交付
- `workflow-modify.md` — L1 流程：用户反馈修改策略（路由→执行→传播）
- `workflow-resume.md` — L1 流程：会话恢复（项目定位→进度推断→session 恢复）

**核心规则：**
- 不做创作决策，不替子 agent 定格式
- 只确认主题、风格、画面比例、语言、时长
- 调度编剧时只传创意简报，不指定数据结构

**待实现的 L1 文件：**
- `workflow-execution.md` — 调度摄影 + 作曲（并行）→ 调度剪辑 → 交付

### 2. Video Screenwriter (`src/kimi_cli/agents/video-screenwriter/`)

编剧 agent，接收创意简报，产出结构化剧本。

**文件：**
- `agent.yaml` — 工具：ReadFile, WriteFile, Glob, Grep；无 subagent
- `system.md` — L0 身份层
- `workflow-write.md` — L1：编写新故事流程（估算容量 → 设计世界设定 → 设计大纲 → 编写场景详情 → 自检）
- `workflow-edit.md` — L1：修改已有故事流程
- `guide-schema.md` — L2：screenplay schema 完整定义
- `guide-complex-story.md` — L2：复杂故事写作指南

**产出格式（Screenplay Schema）：**

编剧在项目目录下生成 4 类 JSON 文件：

| 文件 | 内容 |
|------|------|
| `meta.json` | 标题、视频规格（比例/时长/语言）、风格（style_prefix/negative_prefix） |
| `entities.json` | 角色（fixed_traits, tags, relationships）、场景（areas）、道具 |
| `outline.json` | 故事大纲：acts → scenes（摘要级，含 location, characters, mood, time_of_day） |
| `act-{N}.json` | 各幕场景详情：description, character_states, location_state, prop_states, beats |

**Schema 设计要点：**
- 从简单到复杂可伸缩：短视频（30s, 2-3 场景）到长故事（百年孤独级别）
- 简单故事只用基础字段，复杂故事按需启用扩展字段：
  - `parts` — 超长故事分部（部 → 幕 → 场景）
  - `tags` — 多维角色分组（替代单一 group）
  - `thread` — 多线叙事
  - `narrative_mode` — 非线性叙事（flashback / flash_forward / parallel）
  - `period` — 跨时代标记
  - `from` / `until` — 关系演变的时间范围
- 状态变化显式声明：character_states.appearance, location_state, prop_states
- AI 生成约束：每场景 ≤ 4 角色同时在场，角色需视觉可区分

### 3. 前端改动 (`web/static/index.html`)

- 新增 **Producer** tab（默认激活，排在最前）
- Producer 面板带 **screenplay sticky bar**：检测到编剧写入 meta.json / entities.json / outline.json / act-*.json 时自动出现
- 点击 "Show Screenplay" 打开全屏 **剧本预览 overlay**：
  - 大纲视图：按幕展开，场景卡片显示地点、时间、角色、情绪标签
  - 场景详情：beats（动作/对白/旁白）、地点状态、角色状态
  - 右侧实体栏：角色、场景、道具可展开查看详情和关系
  - 支持新 schema 全部字段（tags, areas, from/until, mood, period, thread, parts 等）
- 删除旧的独立剧本页面（screenplay.html / screenplay.css / screenplay.js）
- `/screenplay` 路由改为重定向到首页

### 4. 前端 Screenplay Sidebar (`web/static/screenplay-viewer.js`)

Producer 面板内的 screenplay 侧边栏（取代旧的全屏 overlay）：
- 检测编剧 WriteFile 写入 screenplay 文件时自动打开侧边栏
- Resume session 时从 chat history 恢复 screenplay 路径并自动加载
- 大纲视图：按幕折叠，场景卡片显示地点、角色数、时间、情绪标签
- 场景详情：beats（动作/对白/旁白）、地点状态、角色状态卡片（可展开）
- 支持新旧 schema（fixed_traits / tags / relationships 和旧版 wardrobe / appearance / traits）
- 侧边栏可拖拽调整宽度、关闭后显示 reopen tab

### 5. Video Director (`src/kimi_cli/agents/video-director/`)

导演 agent，将编剧的剧本转化为可执行的制作计划。

**文件：**
- `agent.yaml` — 工具：ReadFile, WriteFile, Glob, Grep, ValidateDirectorOutput；无 subagent
- `system.md` — L0 身份层，导演角色定义
- `workflow-breakdown.md` — L1：事件拆解（剧本 → events.json）
- `workflow-states.md` — L1：实体状态规划（events.json → states.json）
- `workflow-shots.md` — L1：镜头设计 + 时长分配
- `workflow-validate.md` — L1：跨文件一致性校验
- `guide-events-schema.md` — L2：Event / Interaction / StateChange / Dialogue / EventSequence 字段定义
- `guide-states-schema.md` — L2：CharacterAppearance / CharacterMind / PropState / LocationState / active_during 字段定义
- `guide-shots-schema.md` — L2：镜头数据格式定义

**工作流（4 步）：**
1. 事件拆解：读取剧本 → 将场景/beats 拆解为事件序列 → 写 events.json
2. 实体状态规划：逐实体（角色→场景→道具）规划跨事件状态变化 → 写 states.json
3. 镜头设计：为每个事件设计 shots（画面 + 音频 + 时长）
4. 校验：用 ValidateDirectorOutput 做跨文件一致性检查

**核心规则：**
- 开始工作前先 ReadFile 加载 workflow 和 schema 文件
- 创作决策有剧本依据，不凭空发明
- 不碰上游（编剧产出）和下游（参考图由 producer 调度 art-designer 生成）
- ID 引用必须正确

### 6. 示例数据更新 (`web/static/screenplay-sample/`)

示例数据（小红帽）已适配新 schema：
- `entities.json` — group → tags, relationships 用 from/until, 场景增加 areas
- `outline.json` — 场景增加 mood 和 area
- `act-1.json` / `act-2.json` / `act-3.json` — appearance_change → appearance, 增加 location_state 和 prop_states

## 待实现

### 7. Video Camera (`src/kimi_cli/agents/video-camera/`)

摄影 agent，逐 shot 生成视频片段（画面 + 同期声）。

**输入：** `shots.json` + `states.json`（reference_image 路径）+ `meta.json`（style_prefix / aspect_ratio）

**输出：** `assets/shots/{shot_id}.mp4` + `generation-status.json`（per-shot 状态）

**工具：** GenerateVideoSync, ExtractFrame, GenerateImage, ReadFile

**核心职责：**
- **Prompt 组合**：将 shots.json 的结构化字段（shot_type, angle, movement, content, focus_on）+ states.json 的视觉描述 + meta.json 的 style_prefix/negative_prefix → 组合为 GenerateVideoSync 的 prompt 字符串
- **生成模式决策**：per-shot 判断使用 text_to_video / reference_to_video / image_to_video
  - event 首 shot + 有参考图 → reference_to_video
  - event 非首 shot（尾帧接续）→ image_to_video
  - 无参考图 → text_to_video
  - 可选：先 GenerateImage 生成首帧 → image_to_video
- **尾帧接续**：同 event 内连续 shot，提取前一 shot 的 last frame 作为下一个的 first_frame_path
- **声音描述**：在 prompt 中写入对白文本和音效描述（Sound: 段），视频模型同时生成画面和声音
- **reference_image 引用**：从 focus_on → states.json → reference_image 路径，通过 `<<<image_N>>>` 标记关联到 prompt
- **并行规则**：同 event 内 shot 串行（尾帧依赖），不同 event 可并行（每批 3-5 个）
- **断点续跑**：通过 generation-status.json 跟踪 per-shot 状态，跳过已完成的 shot

**文件规划：**
- `agent.yaml`
- `system.md` — L0 身份层
- `workflow-shoot.md` — L1：逐 shot 生成流程（决策、尾帧提取、首帧生成、生成调用、状态回写）
- `guide-prompt-video.md` — L2：视频 prompt 组合规则（结构化字段 → prompt 字符串的映射规范、`<<<image_N>>>` 标记规则）
- `guide-shot-strategy.md` — L2：生成模式决策树（text_to_video / reference_to_video / image_to_video 的选择条件）

### 8. Video Composer (`src/kimi_cli/agents/video-composer/`)

作曲 agent，生成 BGM。

**输入：** `shots.json`（bgm 字段）+ `meta.json`

**输出：** `assets/audio/bgm_*.mp3`

**工具：** GenerateMusic, CheckMusicJob, ReadFile

**核心职责：**
- **BGM 分段**：从 shots.json 的 `bgm` 字段聚合出音乐分段（连续相同 bgm 的 shot 合为一段）
- **Music prompt 编写**：将 bgm 描述转化为适合音乐生成 API 的 prompt（情绪、乐器、节奏、风格，Suno 限 300 字符）
- **异步生成管理**：提交 GenerateMusic → 轮询 CheckMusicJob → 从候选中选最合适的
- **时长不精确控制**：Suno 生成的音乐时长不可精确指定，由 Editor 在组装时 trim/loop 适配

**文件规划：**
- `agent.yaml`
- `system.md` — L0 身份层
- `workflow-compose.md` — L1：BGM 分段聚合 → 异步生成 → 轮询 → 候选挑选流程
- `guide-music-prompt.md` — L2：music prompt 编写规范（情绪词汇表、乐器描述、Suno 300 字符限制下的写法）

### 9. Video Editor (`src/kimi_cli/agents/video-editor/`)

剪辑 agent，后期组装成片。

**输入：** `shots.json`（shot 顺序 / 转场 / 时长）+ `assets/shots/*.mp4` + `assets/audio/bgm_*.mp3`

**输出：** `output/attempt_{N}.mp4` + `subtitles.srt`

**工具：** VideoEdit (concat/transition/add_audio/add_subtitles/trim/mix_audio), ReadFile, WriteFile

**核心职责：**
- **全局排序**：shots.json 的 `shot_order` 定义了最终播放顺序（导演已将 event DAG 线性化）
- **拼接 + 转场**：按 shot_order 拼接视频片段，应用 transition_in/transition_out（fade/dissolve/wipe/cut）
- **BGM 叠加**：将 BGM 音频叠加到视频上，跨段 crossfade，loop 到视频时长
- **字幕生成**：从 shots.json 的 dialogues 生成 SRT 文件（累加时间偏移），烧录到视频
- **时长校准**：生成的视频实际时长可能与 duration_seconds 不完全吻合，trim 修正累积误差

**文件规划：**
- `agent.yaml`
- `system.md` — L0 身份层
- `workflow-assemble.md` — L1：组装流水线（排序 → 拼接转场 → BGM 叠加 → 字幕生成烧录 → 时长校准）
- `guide-timeline.md` — L2：时间轴计算公式、转场参数表、音频混合参数参考

### Producer 扩展

- `workflow-execution.md` — L1：调度摄影 + 作曲（并行）→ 调度剪辑 → 交付
- `agent.yaml` 新增 3 个 subagent：video-camera, video-composer, video-editor

### Director 扩展

- `shots.json` 增加顶层 `shot_order: [shot_id, ...]`，导演在镜头设计阶段将 event DAG 线性化为最终播放顺序（含 PARALLEL event 的交叉剪辑决策）

### 待办

**已完成：**
- [x] Producer → Screenwriter 完整链路（需求确认 → 编剧产出 → 前端预览）
- [x] 前端 Screenplay Sidebar 交互验证
- [x] Producer workflow-production.md（调度导演）
- [x] Director + art-designer 实现

**进行中：**
- [ ] Producer → Director 完整链路测试
- [ ] Producer → art-designer 参考图生成链路测试

**已实现（执行阶段）：**
- [x] 实现 video-camera agent
- [x] 实现 video-composer agent（agent.yaml + system.md + workflow-compose.md + guide-music-prompt.md）
- [x] 实现 video-editor agent（agent.yaml + system.md + workflow-assemble.md + guide-timeline.md）
- [x] Producer workflow-execution.md（调度摄影+作曲并行 → 剪辑 → 交付）
- [x] Director shots.json 增加 shot_order（已在 guide-shots-schema.md 和 workflow-shots.md 中定义）
- [x] Producer agent.yaml 增加 video-composer / video-editor subagent

**下一步：**
- [ ] Producer → Camera + Composer → Editor 完整链路测试

**远期：**
- [ ] 质量反馈回路（评估 → 修改 → 再评估）
- [ ] 跨模态一致性管理
