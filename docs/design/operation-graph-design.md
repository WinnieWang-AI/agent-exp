# Operation Graph：Agent 执行记忆与思维框架

## 1. 核心理念

Operation Graph 是 agent 的**思考载体**。agent 不再用自由文本思考，而是在图上规划、执行、反思。

```
规划（建图）→ 执行（遍历图）→ 反思（读图）
      ↑                              ↓
      └──────── 经验沉淀 ←───────────┘
```

### 与 Story Graph 的关系

| | Story Graph | Operation Graph |
|---|---|---|
| 描述的是 | 故事内容（角色、事件、镜头） | 制作过程（操作、资源、依赖） |
| 谁产生的 | screenwriter agent | video-creator agent（及其他执行 agent） |
| 用途 | 定义"做什么" | 规划和记录"怎么做" |
| 生命周期 | 用户确认后基本稳定 | 随执行动态演进 |

Story Graph 是 Operation Graph 的**输入之一**——agent 读取 story graph 来规划 operation graph。

## 2. 数据模型

### 2.1 任务节点（Task Node）

任务是 Operation Graph 的最高层抽象。每个任务代表一个有明确目的的工作单元，包含执行标准和验证机制。

```json
{
  "id": "task_gen_ref_images",
  "name": "生成角色参考图",
  "purpose": "为所有角色生成风格一致的参考图，用于后续视频生成时保持角色一致性",
  "check_criteria": [
    "每张参考图的画风必须与 style_guide 一致（水彩绘本风格）",
    "角色外貌必须与 story-graph.json 中的描述匹配",
    "图片质量清晰，无明显畸变（如多余手指、扭曲五官）",
    "所有角色都有对应的参考图，不能遗漏"
  ],
  "status": "planned | running | done | failed | verified | rejected",
  "operations": ["op_gen_char_red", "op_gen_char_wolf"],
  "inputs": ["res_story_graph", "res_style_guide"],
  "outputs": ["res_char_red_img", "res_char_wolf_img"],
  "depends_on": [],
  "verification": {
    "status": "pending | passed | failed",
    "method": "ReadMediaFile 逐张检查",
    "checked_at": 1710000050,
    "issues": [
      {
        "resource": "res_char_wolf_img",
        "issue": "大灰狼图片生成失败，content_policy 拦截",
        "severity": "critical"
      }
    ],
    "summary": "4/5 通过，1 张生成失败需重试"
  }
}
```

任务状态流转：

```
planned → running → done → verified（验证通过）
                  ↘ failed（执行失败）
                        done → rejected（验证不通过）→ running（重试）
```

- `planned`：已规划，未开始执行
- `running`：正在执行内部操作
- `done`：所有操作执行完毕，等待验证
- `verified`：验证通过，任务真正完成
- `rejected`：验证不通过，需要重试或调整
- `failed`：执行失败且无法恢复

**任务层（第一层）** 展示任务节点及其依赖关系，可以快速看到整体进度。
**执行层（第二层）** 点击任务节点后展开，展示内部的具体操作链路（资源节点 + 操作边）。

### 2.2 资源节点（Resource Node）

图中的节点代表资源——用户输入、中间产物、最终输出。

```json
{
  "id": "res_char_red_img",
  "type": "image",
  "path": "assets/images/char_red.png",
  "status": "planned | generating | done | failed",
  "plan": {
    "description": "小红帽角色参考图",
    "expected": {
      "style": "watercolor",
      "aspect_ratio": "3:4",
      "content": "7-8岁小女孩，圆脸，棕色卷发，红色斗篷"
    }
  },
  "actual": {
    "created_at": 1710000000,
    "size_bytes": 245000,
    "mime": "image/png"
  },
  "metadata": {}
}
```

资源类型：

| type | 说明 | 举例 |
|---|---|---|
| `input` | 用户提供的输入 | 故事描述文本、上传的参考图 |
| `json` | 结构化数据文件 | story-graph.json、style_guide.json、shot-plan.json |
| `image` | 图片 | 参考图、首帧图、尾帧截图 |
| `video` | 视频片段 | 单个 shot clip、最终成片 |
| `audio` | 音频 | BGM、音效、旁白 |

### 2.2 操作边（Operation Edge）

图中的边代表操作——从输入资源到输出资源的转换。

```json
{
  "id": "op_gen_char_red",
  "tool": "GenerateImage",
  "agent": "video-creator",
  "status": "planned | running | done | failed",
  "plan": {
    "description": "生成小红帽角色参考图",
    "params": {
      "prompt": "A 7-8 year old girl with round face...",
      "style": "watercolor",
      "aspect_ratio": "3:4"
    }
  },
  "actual": {
    "params": { "...实际调用参数..." },
    "started_at": 1710000000,
    "finished_at": 1710000012,
    "duration_s": 12,
    "result": "success",
    "error": null
  },
  "inputs": ["res_story_graph", "res_style_guide"],
  "outputs": ["res_char_red_img"],
  "attempts": [
    {
      "attempt": 1,
      "status": "failed",
      "error": "content_policy_violation",
      "params": { "prompt": "..." },
      "duration_s": 3
    },
    {
      "attempt": 2,
      "status": "done",
      "params": { "prompt": "...(modified)..." },
      "duration_s": 12
    }
  ]
}
```

### 2.3 约束节点（Constraint Node）

用户反馈和历史经验沉淀为约束，持久化在图中。

```json
{
  "id": "constraint_001",
  "type": "constraint",
  "source": "user_feedback | auto_reflect",
  "scope": "global | tool:GenerateImage | agent:video-creator",
  "rule": "不要使用写实风格，用水彩绘本风格",
  "created_at": 1710000000,
  "related_ops": ["op_gen_char_red"]
}
```

## 3. Agent 思维流程

### 3.1 规划阶段（Plan）

Agent 读取 story graph 和已有约束，在 operation graph 上规划：

```
输入：story-graph.json（5个角色、3个场景、8个事件、12个镜头）
约束：[不要写实风格]、[gemini拒绝暴力内容]

Agent 建图：
  res_story_graph ──GenImage──→ res_char_red_img（计划：水彩，3:4）
                  ──GenImage──→ res_char_wolf_img（计划：水彩，3:4）
                  ──GenImage──→ res_loc_forest_img（计划：水彩，16:9）
                  ...
  res_char_red_img + res_loc_forest ──GenVideo──→ res_shot_1（计划：5s，tracking）
  res_shot_1 ──ExtractFrame──→ res_shot_1_tail（计划：last frame）
  res_shot_1_tail ──GenVideo(i2v)──→ res_shot_2（计划：5s，接续）
  ...
```

规划阶段 agent 可以：
- 看到总工作量（多少个节点需要生成）
- 识别关键路径（哪些有依赖必须串行）
- 应用约束（这个 prompt 要避开 gemini 的审核策略）
- 预估时间和成本

### 3.2 执行阶段（Execute）

Agent 按拓扑序遍历图，逐节点执行：

```
Agent: OperationGraph(action="execute", node_id="op_gen_char_red")

中间层自动：
  1. 从图中读取 op_gen_char_red 的计划参数
  2. 检查约束（有没有相关限制）
  3. 检查输入资源是否 ready
  4. 调用 GenerateImage(...)
  5. 结果写回图：status=done, actual={...}
  6. 返回执行结果给 agent
```

如果失败：

```
中间层自动：
  1. 记录失败到 attempts 数组
  2. 更新 status=failed
  3. 返回失败信息给 agent

Agent 可以：
  - 修改计划参数后重试
  - 跳过该节点，标记为 skipped
  - 调整下游节点的计划
```

### 3.3 反思阶段（Reflect）

执行完成后（或阶段性完成后），agent 读图对比：

```
Agent: OperationGraph(action="reflect")

返回摘要：
  总计划: 25 个操作
  已完成: 20（80%）
  失败:   3（12%）
  跳过:   2（8%）

  偏差:
  - op_gen_shot_5: 计划用 i2v 但实际退回 t2v（原因：尾帧质量差）
  - op_gen_bgm: 计划 30s 但实际生成 25s（原因：provider 限制）

  失败模式:
  - GenerateImage + gemini + prompt含"刀": 3次失败（content_policy）
    → 建议约束: gemini 不接受武器相关内容

  耗时分析:
  - 参考图平均 10s/张，视频平均 45s/个
  - 总耗时 15min，其中 40% 花在视频生成
```

Agent 根据反思结果产出约束，写入图中，供下一轮使用。

## 4. 工具接口设计

给 agent 提供一个统一工具 `OperationGraph`：

```python
class OperationGraphParams(BaseModel):
    action: Literal["plan", "execute", "reflect", "query", "update"]

    # plan: 批量添加计划节点和边
    nodes: list[ResourceNode] | None = None
    edges: list[OperationEdge] | None = None
    constraints: list[Constraint] | None = None

    # execute: 执行指定操作
    operation_id: str | None = None

    # query: 查询图状态
    query: str | None = None  # "pending_ops" | "failed_ops" | "resource:res_xxx" | "constraints"

    # update: 更新节点/边状态（用于手动修正）
    target_id: str | None = None
    updates: dict | None = None
```

### 4.1 action="plan"

Agent 提交一批计划节点和边，系统验证依赖关系后写入图。

```
OperationGraph(
  action="plan",
  nodes=[
    { id: "res_char_red_img", type: "image", plan: { description: "...", expected: {...} } },
    { id: "res_char_wolf_img", type: "image", plan: { description: "...", expected: {...} } },
  ],
  edges=[
    { id: "op_gen_char_red", tool: "GenerateImage", inputs: ["res_story_graph"], outputs: ["res_char_red_img"], plan: { params: {...} } },
    { id: "op_gen_char_wolf", tool: "GenerateImage", inputs: ["res_story_graph"], outputs: ["res_char_wolf_img"], plan: { params: {...} } },
  ]
)
```

返回：计划摘要（总节点数、关键路径、预估工作量）。

### 4.2 action="execute"

Agent 指定要执行的操作节点，中间层负责实际调用。

```
OperationGraph(action="execute", operation_id="op_gen_char_red")
```

中间层：
1. 读取 `op_gen_char_red` 的 `plan.params`
2. 检查 `inputs` 中所有资源的 status 是否为 `done`
3. 检查相关 `constraints`
4. 根据 `tool` 字段调用对应工具（GenerateImage / GenerateVideo / ...）
5. 记录 `actual` 和 `attempts`
6. 更新输出资源节点的 `status`
7. 返回执行结果

### 4.3 action="reflect"

Agent 请求图的状态摘要和偏差分析。

```
OperationGraph(action="reflect")
```

返回：
- 完成率、失败率
- 失败模式聚类（哪些操作、哪些参数、哪些 provider 容易失败）
- 计划 vs 实际的偏差列表
- 建议的新约束

### 4.4 action="query"

按需查询图中的特定信息。

```
OperationGraph(action="query", query="pending_ops")        # 还有哪些操作没执行
OperationGraph(action="query", query="resource:res_xxx")    # 某个资源的状态
OperationGraph(action="query", query="failed_ops")          # 所有失败的操作
OperationGraph(action="query", query="constraints")         # 当前所有约束
```

### 4.5 action="update"

手动修正图中的信息（比如用户确认某个资源可用、或者 agent 决定跳过某个操作）。

```
OperationGraph(action="update", target_id="op_gen_shot_5", updates={ "status": "skipped", "reason": "用户要求跳过" })
```

## 5. 持久化与生命周期

### 5.1 存储

```
output/{session_id}/{project_name}/
  ├── story-graph.json        # 故事内容图
  ├── operation-graph.json    # 操作执行图（本方案）
  ├── style_guide.json
  └── assets/
      ├── images/
      ├── clips/
      └── audio/
```

### 5.2 Session Resume

恢复 session 时，agent 读取 operation-graph.json：
- 哪些资源已经生成（不需要重做）
- 哪些操作失败了（需要换策略）
- 哪些约束存在（不要再犯）

这解决了当前 session resume 的痛点——agent 不再需要猜测"做到哪了"，图上写得清清楚楚。

### 5.3 跨 Session 经验积累

约束节点可以提取为全局经验库（独立于单个 session）：

```
~/.agent-exp/experience/
  ├── provider_constraints.json   # gemini 不接受暴力内容、某 provider 限制 30s...
  ├── tool_patterns.json          # GenerateImage 首次成功率 70%、i2v 比 t2v 慢 3x...
  └── user_preferences.json       # 用户偏好水彩风、不喜欢 BGM 太响...
```

新 session 开始时，加载全局经验作为初始约束。

## 6. 前端可视化

### 6.1 整体架构

复用现有 Cytoscape.js 基础设施。Operation Graph 与 Director tab 绑定（因为它是 video-director 执行过程中产生的，和 director 的 session 生命周期一致），交互方式与 Story Graph 完全对齐：

1. **Director 聊天区**出现 operation graph 的 mini 预览卡片（和 story graph 卡片并列）
2. 点击展开 overlay，overlay header 增加 **Story / Operation 视图切换**按钮
3. 两个视图共享同一个 overlay 容器、detail panel、交互模式

```
Director tab 聊天区
  ├── [Story Graph mini 预览卡片]   ← 已有
  ├── [Operation Graph mini 预览卡片] ← 新增
  └── ...

overlay（点击任一卡片展开）
  ├── overlay-header
  │     ├── [Story] [Operation]          ← 视图切换
  │     ├── 过滤器（根据当前视图动态变化）
  │     └── 工具栏（布局、缩放、导出）
  ├── overlay-body
  │     ├── cytoscape 画布（根据当前视图渲染不同的图）
  │     └── detail panel（右侧抽屉）
  └── overlay-footer
        └── 状态摘要栏（总操作数、完成率、失败数、耗时）
```

### 6.2 节点与边的视觉映射

#### 资源节点（Resource Node）

| 资源类型 | 形状 | 颜色 | 说明 |
|---------|------|------|------|
| `input` | 菱形 | `#94a3b8`（灰蓝） | 用户输入，不可操作 |
| `json` | 圆角方形 | `#60a5fa`（蓝） | 结构化数据 |
| `image` | 圆形 | `#34d399`（绿） | 图片资源 |
| `video` | 圆形 | `#818cf8`（紫蓝） | 视频片段 |
| `audio` | 圆形 | `#fbbf24`（黄） | 音频资源 |

节点状态叠加：

| 状态 | 边框 | 角标 | 说明 |
|------|------|------|------|
| `planned` | 2px 灰色虚线 | `○` | 尚未开始 |
| `generating` | 3px 橙色实线 + 橙色光晕 | `⟳` | 正在生成 |
| `done` | 3px 绿色实线 | `✓` | 完成 |
| `failed` | 3px 红色实线 + 红色光晕 | `✗` | 失败（**高亮显示**） |
| `skipped` | 2px 灰色实线 + 半透明 | `—` | 被跳过 |

#### 操作边（Operation Edge）

| 状态 | 线型 | 颜色 | 标签 |
|------|------|------|------|
| `planned` | 虚线 | `#6b7280` | 工具名 |
| `running` | 实线 + 动画流动 | `#f59e0b` | 工具名 |
| `done` | 实线 | `#10b981` | 工具名 + 耗时（如 `GenImage 12s`） |
| `failed` | 实线 | `#ef4444` | 工具名 + `FAILED` |

边的粗细可按重试次数加粗：1 次 = 2px，2 次 = 3px，3+ 次 = 4px。

#### 约束节点（Constraint Node）

- 形状：八边形（或六边形），区别于资源节点
- 颜色：`#f87171`（红）虚线边框
- 连接到相关的操作边，用红色虚线连线
- 标签显示约束规则摘要

### 6.3 错误分析视图

这是 Operation Graph 可视化的**核心价值**——帮助用户快速定位和分析错误。

#### 6.3.1 错误高亮模式

工具栏增加 **"Show Errors"** 切换按钮。开启后：

- 所有 `done` / `planned` 节点降低透明度（opacity: 0.2）
- 所有 `failed` 节点 + 相关边保持完全不透明 + 红色高亮
- 失败节点的上游输入节点也适当高亮（帮助追溯输入是否有问题）
- 产生的约束节点（如果有）跟在失败节点旁边

效果：一眼看出整个流程中哪些环节失败了，以及失败的上下文。

#### 6.3.2 错误详情面板

点击失败的操作边（或失败的资源节点），右侧 detail panel 显示：

```
┌─────────────────────────────────┐
│ ✗ op_gen_shot_5                 │
│ GenerateImage → FAILED          │
├─────────────────────────────────┤
│ PLAN                            │
│ prompt: "A wolf lurking..."     │
│ provider: gemini                │
│ style: watercolor               │
├─────────────────────────────────┤
│ ATTEMPTS (3)                    │
│                                 │
│ #1  ✗  3s  content_policy       │
│   prompt: "A wolf lurking       │
│   with sharp teeth..."          │
│   error: "Blocked by safety     │
│   filter: violence"             │
│                                 │
│ #2  ✗  2s  content_policy       │
│   prompt: "A friendly wolf      │
│   in the forest..."             │
│   error: "Blocked by safety     │
│   filter"                       │
│                                 │
│ #3  ✗  4s  timeout              │
│   prompt: "A cartoon wolf..."   │
│   error: "Request timed out"    │
│                                 │
├─────────────────────────────────┤
│ INPUTS                          │
│ ○ res_story_graph (done)        │
│ ○ res_style_guide (done)        │
├─────────────────────────────────┤
│ DOWNSTREAM IMPACT               │
│ ⚠ res_shot_5_clip (blocked)    │
│ ⚠ res_shot_6_clip (blocked)    │
├─────────────────────────────────┤
│ CONSTRAINT GENERATED            │
│ "gemini 拒绝含有牙齿/爪子       │
│  描述的动物图片"                 │
└─────────────────────────────────┘
```

#### 6.3.3 失败模式聚合视图

在 overlay footer 或单独的 panel 中，显示失败操作的自动聚类：

```
┌─────────────────────────────────────────────┐
│ FAILURE PATTERNS                            │
├─────────────────────────────────────────────┤
│ ◆ content_policy (5 ops, 8 attempts)        │
│   tool: GenerateImage                       │
│   provider: gemini                          │
│   common keywords: wolf, teeth, dark        │
│   → constraint: 避免 gemini 生成动物攻击场景 │
│                                             │
│ ◆ timeout (2 ops, 2 attempts)               │
│   tool: GenerateVideo                       │
│   provider: kling                           │
│   avg duration before timeout: 120s         │
│   → constraint: kling 视频 > 8s 容易超时     │
│                                             │
│ ◆ quality_reject (1 op, 3 attempts)         │
│   tool: GenerateImage → ReadMediaFile       │
│   reason: agent 判断质量不达标               │
│   → suggestion: 调整 prompt 或换 provider   │
└─────────────────────────────────────────────┘
```

点击每个 pattern 可以高亮图中对应的所有失败节点。

#### 6.3.4 时间线视图（Timeline）

除了图视图之外，增加一个可切换的**时间线视图**，按执行时间排列所有操作：

```
时间 ──────────────────────────────────────────→
 |  [GenImage char_red ✓ 10s]
 |  [GenImage char_wolf ✗ 3s] [retry ✗ 2s] [retry ✓ 12s]
 |  [GenImage loc_forest ✓ 8s]
 |       [GenVideo shot_1 ✓ 45s]
 |            [ExtractFrame ✓ 1s]
 |            [GenVideo shot_2 ✓ 50s]
 |  [GenImage loc_house ✓ 9s]
 |       [GenVideo shot_3 ✗ 120s timeout]
```

- 横轴是时间，纵轴是并行度
- 红色块表示失败，绿色块表示成功
- 块的宽度对应耗时
- 鼠标 hover 显示详情
- 可以快速看出：哪些操作耗时最长、哪些阶段有瓶颈、失败发生在什么时间点

### 6.4 过滤与搜索

工具栏过滤器：

- **按资源类型**：image / video / audio / json / input（toggle 按钮，复用 story graph 的 sg-toggle 样式）
- **按状态**：planned / running / done / failed / skipped
- **按 agent**：video-creator / video-director / ...
- **按工具**：GenerateImage / GenerateVideo / ExtractFrame / ...
- **搜索框**：输入关键词匹配节点 ID / 描述 / 错误信息

常用组合提供快捷入口：
- "Show Failed Only" = 状态过滤 failed + 错误高亮模式
- "Show Running" = 状态过滤 running（监控当前进度）
- "Show All" = 重置所有过滤

### 6.5 实时更新

复用现有 WebSocket + 轮询双机制：

1. **WebSocket 事件驱动**：agent 调用 OperationGraph 工具时，通过 SubagentEvent 链推送到前端，更新对应节点/边的状态
2. **轮询兜底**：每 3 秒 fetch `operation-graph.json`，对比差异更新（和 story graph 相同机制）
3. **增量更新**：只更新变化的节点，不全量重建图（Cytoscape 支持 `ele.data()` 局部更新）

### 6.6 文件结构

```
web/static/
  ├── story-graph.js          # 现有 story graph 渲染
  ├── story-graph.css         # 现有 story graph 样式
  ├── operation-graph.js      # 新增：operation graph 渲染
  ├── operation-graph.css     # 新增：operation graph 样式
  └── index.html              # 增加视图切换逻辑
```

`operation-graph.js` 导出的核心函数：

```js
// 解析 operation-graph.json → cytoscape elements
function parseOperationGraph(data) → { nodes, edges }

// 构建 cytoscape 样式
function buildOpGraphStyles() → styles[]

// 应用状态类（和 story graph 的 applyImageStatusClasses 类似）
function applyOpStatusClasses(cy)

// 错误高亮模式切换
function toggleErrorHighlight(cy, enabled)

// 构建详情面板 HTML
function buildOpDetailHtml(eleData) → html

// 失败模式聚合分析
function analyzeFailurePatterns(data) → patterns[]

// 时间线数据转换
function buildTimelineData(data) → timelineItems[]
```

## 7. 实现路径

### Phase 1：数据模型 + 工具骨架
- 定义 `OperationGraph` 数据模型（Pydantic）
- 实现 `OperationGraph` 工具（plan / query / update）
- JSON 持久化读写

### Phase 2：execute 中间层
- 实现 execute action，自动调用底层工具
- 自动记录 attempts、actual、status
- 约束检查（执行前自动匹配相关约束）

### Phase 3：reflect 分析
- 实现 reflect action，自动聚类失败模式
- 生成建议约束
- 偏差分析（planned vs actual）

### Phase 4：前端可视化
- Cytoscape 渲染 operation graph
- 实时状态更新（复用现有 WebSocket 机制）

### Phase 5：跨 session 经验
- 约束提取为全局经验库
- 新 session 自动加载
