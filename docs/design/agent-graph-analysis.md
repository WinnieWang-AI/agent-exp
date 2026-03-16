# Agent Graph 结构分析与可视化 — 设计文档

## 1. 概述

为 agent-optimizer 新增 **Agent Graph 分析**能力：自动解析任意 agent 的定义和运行日志，生成结构化的拓扑图与工作流图，并在前端可视化展示。支持静态分析（从 agent.yaml + system.md）和动态分析（从 JSONL 日志），两者结合可发现 agent 实际行为与 prompt 设计意图的偏差。

### 1.1 目标

- 通用：适用于任意 agent，不要求 agent 的 system.md 遵循特定格式
- 多粒度：从全局拓扑到单步 trace，支持逐层下钻
- 偏差检测：自动对比 prompt 意图 vs 日志行为，标注偏差

### 1.2 非目标

- 不修改现有 agent 的 system.md 格式
- 不替代 agent-optimizer 已有的文本分析能力（补充，非替代）

## 2. 分析层次

```
全局拓扑（多 agent）
  └── 单 agent 工作流图
        └── Step 总览（三层偏差检测）
              └── Step Trace 下钻（逐调用明细）
```

### 2.1 全局拓扑

输入一组 agent（或 `*` 全部），输出所有 agent 之间的静态关系图。

**数据来源**：递归解析 `src/kimi_cli/agents/*/agent.yaml`

**输出内容**：
- Agent 节点（名称、工具数量、子 agent 数量）
- Agent 间的边（SUBAGENT 关系 via Task，CHAT_WITH 关系 via ChatWithAgent）
- 可选：边上叠加日志聚合指标（调用频次、平均 token）

**示例**（video-director 所在的 agent 集群）：

```
video-director
├── [SUBAGENT] screenwriter        (4 tools, 0 subagents)
├── [SUBAGENT] video-creator       (16 tools, 1 subagent)
│   └── [SUBAGENT] coder
└── [SUBAGENT] video-evaluator     (4 tools, 0 subagents)

agent-optimizer
└── [SUBAGENT] paper-researcher
```

### 2.2 单 Agent 工作流图

对单个 agent 提取其工作流程，输出为 DAG。

**数据来源**：用 LLM 解析 agent 的 system.md 中的 Workflow/How You Work 等章节。

**输出内容**：
- 步骤节点（task / decision / user_confirm / begin / end）
- 步骤间的边（顺序、条件分支、循环）
- 每个步骤关联的 subagent 调用

**示例**（video-director）：

```
BEGIN
  -> Step 1: 理解需求（可能 AskUser）
  -> Step 1.5: screenwriter 阶段一
  -> {用户确认?} --修改--> Step 1.5 (循环)
  -> Step 1.6: screenwriter 阶段二
  -> {用户确认?}
  -> Step 1.8: video-creator 参考图
  -> {用户确认?}
  -> Step 2: video-creator 生成视频
  -> Step 3: video-evaluator 评估
  -> {APPROVED?} --No, <=5轮--> Step 2 (循环)
  -> {APPROVED?} --Yes 或 5轮用完--> END
```

### 2.3 偏差检测（三层）

将日志与工作流图对比，从粗到细三层检测：

#### Layer 1: 流程级（Step Ordering）

纯规则检测，不需要 LLM。

| 检测项 | 说明 | 示例 |
|--------|------|------|
| 步骤跳过 | 工作流中的必经步骤未执行 | 跳过 Step 1.5 直接进 Step 2 |
| 步骤乱序 | 实际执行顺序与工作流不一致 | 先 video-creator 再 screenwriter |
| 循环越界 | 超出 prompt 规定的最大迭代次数 | prompt 规定最多 5 轮，实际跑了 7 轮 |
| 缺失步骤 | 某个步骤在所有日志中从未出现 | 生成完没调 evaluator |

**实现方式**：从日志的 `Task(subagent_name=...)` 调用序列提取，与工作流图的拓扑序对比。

#### Layer 2: 约束级（Constraint Violation）

检测 prompt 中的显式规则（"必须"/"禁止"/"总是"）是否被遵守。混合实现：简单约束用规则匹配，语义约束用 LLM。

| 约束示例 | 检测方式 |
|---------|---------|
| "Always use session_id" | 检查每个 Task 调用是否传了 session_id 参数 |
| "Always relay the full feedback" | LLM 对比 evaluator 返回内容 vs 传给 creator 的 prompt 长度和内容 |
| "禁止降级为本地生成" | 关键词匹配：creator 的 prompt 中是否含 ffmpeg/Ken Burns/animatic |
| "错误最多重试 2 次" | 统计连续失败的同类 tool call 次数 |

#### Layer 3: 意图级（Semantic Intent）

检测 agent 行为是否符合 prompt 的语义意图（非显式规则）。必须用 LLM。

| 检测项 | 示例 |
|--------|------|
| 角色越界 | director 自己写了 story graph 而不是交给 screenwriter |
| 虚假进展 | 报告"正在刷新凭证"但实际没有任何操作 |
| 过度询问 | prompt 说"直接执行不要追问"，但 agent 连续问了 3 个确认 |

### 2.4 Step Trace 下钻

用户可对任意 workflow step 的任意一轮执行，查看完整的调用明细。

**内容**：
- 该 step 的 prompt 意图摘要
- 该 step 适用的 prompt 约束列表
- 按时间顺序的每一次 tool call（assistant thinking + tool name + args + result）
- 偏差标注直接标在具体的 tool call 上
- 统计（tool call 数、token 用量、耗时）

**示例**（Step 3 第 4 轮）：

```
Step 3: 评估与迭代 - 第 4/5 轮

Prompt 意图：
  调用 video-evaluator 评估成片，NEEDS_REVISION 则将完整反馈传给 video-creator，不等用户确认

适用规则：
  - "Always relay the full feedback"
  - "最多 5 轮"
  - "NEEDS_REVISION -> 立即传给 creator，不要等用户确认"

Trace:
  #1 [assistant] thinking: "第 4 轮，上轮评分 6.5..."
  #2 [tool] Task -> video-evaluator (session_id="eval_ocean")
     返回: "Overall: 7.2/10. NEEDS_REVISION. 画面质量提升，但第3场景..." (1847 chars)
  #3 [assistant] thinking: "7.2 分，还差一点。把反馈传给 creator。"
  #4 [tool] Task -> video-creator (session_id="create_ocean")
     prompt: "Round 4 feedback: 画面质量OK，角色服装需要修复" (127 chars)
     DEVIATION [error]: "relay full feedback"
       evaluator 返回 1847 chars，实际传递 127 chars，丢失了具体场景编号和帧范围

统计: 3 tool calls / 4,521 tokens / 45s
```

## 3. 数据模型

### 3.1 静态拓扑

```python
class AgentNode(BaseModel):
    """拓扑图中的一个 agent 节点"""
    id: str                          # "video-director"
    name: str                        # "video-director"
    tools: list[str] = []            # ["Task", "SetTodoList", "ReadFile", ...]
    tool_count: int = 0
    subagent_count: int = 0


class AgentEdge(BaseModel):
    """agent 之间的关系边"""
    source: str                      # "video-director"
    target: str                      # "screenwriter"
    edge_type: Literal["SUBAGENT", "CHAT_WITH"]
    description: str = ""            # subagent 的 description


class AgentTopology(BaseModel):
    """全局拓扑"""
    nodes: list[AgentNode]
    edges: list[AgentEdge]
```

### 3.2 工作流图

```python
class WorkflowStep(BaseModel):
    """工作流中的一个步骤"""
    id: str                          # "step_1_5"
    label: str                       # "调用 screenwriter 阶段一"
    kind: Literal["begin", "end", "task", "decision", "user_confirm"]
    agent_call: str | None = None    # "screenwriter" — 关联到哪个 subagent
    description: str = ""            # 更详细的描述


class WorkflowEdge(BaseModel):
    """步骤间的连接"""
    source: str                      # "step_1_5"
    target: str                      # "uc_1"
    label: str = ""                  # "Yes" / "No" / "修改"
    is_loop: bool = False            # 是否为循环边


class WorkflowConstraint(BaseModel):
    """从 prompt 提取的显式约束"""
    id: str                          # "c_full_feedback"
    rule: str                        # "Always relay the full feedback from evaluator to creator"
    applies_to: list[str] = []       # ["step_3"] — 适用于哪些步骤
    check_type: Literal["keyword", "parameter", "count", "semantic"]
    # keyword: 关键词匹配
    # parameter: 检查 tool call 参数
    # count: 计数检查（如重试次数）
    # semantic: 需要 LLM 判断


class AgentWorkflow(BaseModel):
    """单 agent 的工作流"""
    agent_id: str
    steps: list[WorkflowStep]
    edges: list[WorkflowEdge]
    constraints: list[WorkflowConstraint]
    max_loops: dict[str, int] = {}   # {edge_id: max_iterations}
```

### 3.3 执行 Trace 与偏差

```python
class TraceCall(BaseModel):
    """trace 中的一次调用"""
    seq: int                         # 调用序号
    role: Literal["assistant", "tool"]
    thinking: str = ""               # agent 的推理文本
    tool_name: str = ""              # "Task"
    tool_args: dict = {}             # {"subagent_name": "video-evaluator", ...}
    tool_result: str = ""            # tool 返回内容
    token_usage: int = 0
    timestamp: str = ""
    deviations: list["TraceDeviation"] = []


class TraceDeviation(BaseModel):
    """标注在具体 call 上的偏差"""
    constraint_id: str               # 关联到 WorkflowConstraint.id
    rule: str                        # 人类可读的规则描述
    severity: Literal["info", "warning", "error"]
    expected: str                    # prompt 说应该做什么
    actual: str                      # 实际做了什么
    evidence: str                    # 具体证据


class StepTrace(BaseModel):
    """某个 workflow step 的一次执行 trace"""
    step_id: str
    iteration: int = 1              # 循环场景下的轮次
    calls: list[TraceCall]
    expected_intent: str            # 该步骤的 prompt 意图摘要
    applicable_rules: list[str]     # 适用的约束 ID 列表
    total_tool_calls: int = 0
    total_tokens: int = 0
    duration_ms: int = 0


class StepDeviation(BaseModel):
    """步骤级别的偏差（Layer 1 流程级）"""
    step_id: str
    deviation_type: Literal["skipped", "out_of_order", "loop_exceeded", "missing"]
    severity: Literal["info", "warning", "error"]
    description: str
    expected: str = ""
    actual: str = ""


class DeviationReport(BaseModel):
    """完整的偏差报告"""
    agent_id: str
    # Layer 1
    step_deviations: list[StepDeviation]
    # Layer 2 + 3 的偏差分布在各 StepTrace 的 TraceCall.deviations 中
    summary: dict[str, int]          # {"error": 2, "warning": 3, "info": 1}
```

### 3.4 前端展示数据（DisplayBlock）

```python
class AgentGraphViewDisplayBlock(DisplayBlock):
    """传给前端的完整数据"""
    type: str = "agent_graph_view"

    # 全局拓扑（多 agent 时有多个节点）
    topology: AgentTopology

    # 工作流（单 agent 分析时填充，全局模式下为空）
    workflow: AgentWorkflow | None = None

    # 偏差报告（有日志时填充）
    deviation_report: DeviationReport | None = None

    # Step traces（按需加载，初始为空，用户下钻时通过 API 请求）
    traces: dict[str, list[StepTrace]] = {}
    # key = step_id, value = [第1轮trace, 第2轮trace, ...]
```

## 4. 工作流提取（LLM）

### 4.1 提取流程

```
system.md ──LLM──> 原始工作流 JSON ──验证──> AgentWorkflow
                                       ↑
                              agent.yaml (subagent 列表用于验证)
```

### 4.2 LLM Prompt 设计

给 LLM 输入：
1. agent 的 system.md 全文
2. agent.yaml 中的 subagents 列表和 tools 列表
3. 输出格式 schema

要求 LLM 输出：
- steps：识别所有工作流步骤，分类为 task/decision/user_confirm/begin/end
- edges：步骤间的连接，标注条件和循环
- constraints：从 Rules/规则等章节提取显式约束
- max_loops：循环边的最大迭代次数

### 4.3 验证机制

LLM 输出后经过三层验证：

| 验证 | 检查内容 | 失败处理 |
|------|---------|---------|
| 结构验证 | 复用 `validate_flow()`：有且仅有一个 begin/end，end 从 begin 可达，decision 节点的出边有 label | 拒绝，附带错误信息要求 LLM 重试（最多 2 次） |
| 一致性验证 | 工作流中引用的 agent name 必须存在于 agent.yaml 的 subagents 中 | 自动移除不存在的引用，标记 warning |
| 覆盖度验证 | agent.yaml 中声明的每个 subagent 至少在工作流中出现一次 | 标记 warning："{name} 在配置中声明但未出现在主工作流中，可能存在未识别的分支路径" |

## 5. 日志分析

### 5.1 日志定位

```
~/.kimi/sessions/{work_dir_hash}/{session_id}/
├── context.jsonl                            # 主 agent 对话
├── dialogue_{session_id}.jsonl              # Task 子 agent 对话
└── chat_{agent_name}_{session_id}.jsonl     # ChatWithAgent 对话
```

`work_dir_hash` = `md5(KIMI_WORK_DIR)`

### 5.2 日志切段

将 JSONL 日志按 workflow step 归属切段：

```
1. 扫描 context.jsonl 中所有 tool_calls
2. 识别 Task / ChatWithAgent 调用，提取 subagent_name
3. 根据 subagent_name 匹配到 workflow step（step.agent_call == subagent_name）
4. 同一 step 的连续调用归为同一轮（iteration）
5. 被其他 step 打断后再次出现 -> 新一轮 iteration
6. 辅助性 tool call（ReadFile、Glob 等）归属到最近的 step context
7. 无法归属的 call -> 标记为 "unmatched"，可能是工作流未覆盖的行为
```

### 5.3 偏差检测实现

**Layer 1（流程级）**：
```
1. 从切段结果提取 step 执行序列：[step_1, step_1_5, step_1_6, ...]
2. 与工作流图的拓扑序对比
3. 检测跳过、乱序、循环次数
```

**Layer 2（约束级）**：
```
对每个 WorkflowConstraint，根据 check_type 执行：
- keyword: 在相关 step 的 tool_args/tool_result 中搜索关键词
- parameter: 检查 tool call 的参数是否存在/符合要求
- count: 统计特定模式的出现次数
- semantic: 将 rule + 相关 trace 片段发送给 LLM 判断
```

**Layer 3（意图级）**：
```
对每个 step，将以下内容发送给 LLM：
- step 的 prompt 意图摘要
- step 的实际 trace
- agent 的角色定义（system.md 前几段）
要求 LLM 判断是否存在角色越界、虚假进展、过度询问等问题
```

## 6. 前端可视化

### 6.1 技术选型

仿照 Story Graph 的双轨模式：

| 视图 | 技术 | 用途 |
|------|------|------|
| Chat 内嵌 | React 组件 (`agent-graph-view.tsx`) | 卡片式摘要，嵌入对话流 |
| 独立面板 | Cytoscape.js (`agent-graph.js`) | 交互式 node-graph，支持下钻 |

### 6.2 Chat 内嵌视图

卡片式布局，分区展示：

```
+-- Agent Graph: video-director -----------------------+
|  4 agents  /  15 tools  /  7 steps  /  2 loops       |
+------------------------------------------------------+
| [Agent 拓扑]                                          |
|  screenwriter(4t)  video-creator(16t)  evaluator(4t) |
+------------------------------------------------------+
| [工作流]                                              |
|  > Step 1: 理解需求                                   |
|  > Step 1.5: screenwriter 阶段一 -> 确认 (loop)      |
|  > Step 1.6: screenwriter 阶段二 -> 确认             |
|  > Step 1.8: video-creator 参考图 -> 确认            |
|  > Step 2-3: 生成 -> 评估 -> 迭代 (<=5轮, loop)     |
+------------------------------------------------------+
| [偏差] 2 errors / 1 warning                          |
|  [error] Step 3: 迭代 7 轮，超出 5 轮上限            |
|  [error] Step 3#4: evaluator 反馈被截断              |
|  [warn]  Step 1: 用户已提供风格，agent 仍追问        |
+------------------------------------------------------+
```

每个 step 行可展开查看 trace 详情。

### 6.3 Cytoscape 独立面板

**节点样式**：

```javascript
const NODE_STYLES = {
  agent:        { bg: '#3b82f6', border: '#1d4ed8', shape: 'round-rectangle' },
  tool:         { bg: '#10b981', border: '#059669', shape: 'ellipse' },
  task:         { bg: '#f59e0b', border: '#d97706', shape: 'round-rectangle' },
  decision:     { bg: '#8b5cf6', border: '#7c3aed', shape: 'diamond' },
  user_confirm: { bg: '#f472b6', border: '#ec4899', shape: 'hexagon' },
  begin:        { bg: '#6b7280', border: '#4b5563', shape: 'ellipse' },
  end:          { bg: '#6b7280', border: '#4b5563', shape: 'ellipse' },
};
```

**边样式**：

```javascript
const EDGE_STYLES = {
  SUBAGENT:  { color: '#3b82f6', style: 'solid',  width: 2.5, arrow: 'triangle' },
  CHAT_WITH: { color: '#8b5cf6', style: 'dashed', width: 2,   arrow: 'triangle' },
  TOOL:      { color: '#6b7280', style: 'dotted', width: 1.5, arrow: 'none' },
  FLOW:      { color: '#f59e0b', style: 'solid',  width: 2,   arrow: 'triangle' },
  LOOP:      { color: '#ef4444', style: 'dashed', width: 2,   arrow: 'triangle' },
  DEVIATION: { color: '#ef4444', style: 'solid',  width: 3,   arrow: 'triangle' },
};
```

**Toolbar**：
- 节点过滤：`[Agent]` `[Tool]` `[Workflow]` `[Decision]`
- 偏差高亮开关
- 视图切换：`[拓扑]` `[工作流]` `[合并]`

**交互**：
- 单击节点 -> 右侧 detail panel 显示详细信息
- 双击 workflow step 节点 -> detail panel 展开该 step 的 trace
- 循环步骤的 detail panel 顶部有轮次切换器：`[1] [2] [3] [4!] [5]`
- 有偏差的节点：边框变红/黄，hover 显示偏差摘要
- 有偏差的 trace call：左侧带红/黄竖条，点击展开对比视图

**全局拓扑模式**：
- 展示所有 agent 节点和关系
- 点击某个 agent 节点 -> 展开该 agent 的工作流子图（inline subgraph 或跳转）

## 7. 文件结构

### 7.1 后端

```
src/kimi_cli/tools/agent_graph/
  __init__.py                    # 暴露 AnalyzeAgentGraph tool
  static.py                      # 静态拓扑分析（解析 agent.yaml）
  workflow.py                    # 工作流提取（LLM 解析 system.md）
  log_analyzer.py                # 日志分析（切段 + 偏差检测）
  trace.py                       # Step Trace 构建
  view.py                        # 组装 AgentGraphViewDisplayBlock

src/kimi_cli/tools/display.py   # 新增 AgentGraphViewDisplayBlock 等模型
```

### 7.2 前端

```
web/src/features/tool/components/
  agent-graph-view.tsx            # Chat 内嵌卡片视图（新建）
  display-content.tsx             # 新增 case "agent_graph_view" 路由

web/static/
  agent-graph.js                  # Cytoscape 独立面板（新建）
  agent-graph.css                 # 样式（新建）
```

### 7.3 Agent 配置

```
src/kimi_cli/agents/agent-optimizer/
  system.md                       # 新增「模式 4：结构分析」章节
  agent.yaml                      # tools 中新增 AnalyzeAgentGraph
```

## 8. Tool 接口设计

### 8.1 AnalyzeAgentGraph

optimizer 调用的主入口 tool。

```python
class AnalyzeAgentGraph(BaseTool):
    """分析 agent 结构并生成可视化 graph"""

    class Args(BaseModel):
        # 目标 agent，可以是单个名称或列表
        agents: list[str]            # ["video-director"] 或 ["*"] 表示全部

        # 分析模式
        mode: Literal["topology", "workflow", "full"] = "full"
        # topology: 只做静态拓扑
        # workflow: 静态拓扑 + 工作流提取
        # full: 静态 + 工作流 + 日志分析

        # 日志相关（mode=full 时有效）
        session_id: str | None = None   # 指定分析哪个 session，None 则取最新
        max_sessions: int = 1           # 分析最近 N 个 session

        # 下钻（可选，指定后只返回特定 step 的 trace）
        drill_step: str | None = None   # step_id
        drill_iteration: int | None = None  # 轮次

    class Result(BaseModel):
        success: bool
        display: AgentGraphViewDisplayBlock | None = None
        error: str = ""
```

### 8.2 使用示例

```python
# 全局拓扑
AnalyzeAgentGraph(agents=["*"], mode="topology")

# 单 agent 完整分析
AnalyzeAgentGraph(agents=["video-director"], mode="full")

# 下钻到某一步
AnalyzeAgentGraph(
    agents=["video-director"],
    mode="full",
    drill_step="step_3",
    drill_iteration=4,
)
```

## 9. 执行计划

### Phase 1: 静态拓扑

1. 定义数据模型（AgentNode, AgentEdge, AgentTopology）
2. 实现 `static.py`：递归解析 agent.yaml
3. 实现 `view.py`：组装 AgentGraphViewDisplayBlock（仅 topology 部分）
4. 实现 `__init__.py`：AnalyzeAgentGraph tool（mode=topology）
5. 前端：agent-graph-view.tsx 的拓扑卡片部分
6. 前端：display-content.tsx 路由
7. 验证：对所有现有 agent 生成拓扑图

### Phase 2: 工作流提取

1. 定义数据模型（WorkflowStep, WorkflowEdge, WorkflowConstraint, AgentWorkflow）
2. 实现 `workflow.py`：LLM 提取 + 三层验证
3. 扩展 view.py：填充 workflow 部分
4. 前端：agent-graph-view.tsx 的工作流部分
5. 前端：agent-graph.js Cytoscape 基础渲染
6. 验证：对 video-director 提取工作流，人工核对

### Phase 3: 日志分析与偏差检测

1. 定义数据模型（TraceCall, StepTrace, StepDeviation, DeviationReport 等）
2. 实现 `log_analyzer.py`：日志切段 + Layer 1 检测
3. 实现 `trace.py`：Step Trace 构建
4. 扩展 log_analyzer.py：Layer 2 + Layer 3 检测
5. 扩展 view.py：填充 deviation_report 和 traces
6. 前端：偏差标注渲染（节点着色、trace 内偏差标记）
7. 前端：Step Trace 下钻交互
8. 验证：用 video-director 的真实日志做端到端测试

### Phase 4: 打磨

1. Cytoscape 独立面板完善（toolbar、过滤、布局优化）
2. 全局拓扑 + 日志聚合指标
3. 更新 agent-optimizer 的 system.md，增加模式 4
4. 更新 agent-optimizer 的 agent.yaml，注册 AnalyzeAgentGraph tool
