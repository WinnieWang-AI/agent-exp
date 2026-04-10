# 会话日志分析与记录提取

## 输入

用户提供的 session 路径或 UUID。如果未提供，扫描 `output/.sessions/` 下所有 session。

chat.jsonl 每行格式：
```json
{"timestamp": N, "role": "user"|"assistant", "agent": "user"|"video-producer"|..., "content": "string" | {"type": "...", "payload": {...}}}
```

关注的 content type：
- `role=user, agent=user`：用户指令和反馈
- `type=ContentPart`：agent 的文本回复
- `type=ToolCall` / `type=ToolResult`：agent 的工具调用和结果
- `type=SubagentEvent`：子 agent 调度事件，包含子 session 引用

## 步骤

### Step 1: 定位 session 目录

如果用户提供了 UUID：

```
ReadFile("output/.sessions/{uuid}/chat.jsonl")
```

如果未提供，扫描所有 session：

```
Glob("output/.sessions/*/chat.jsonl")
```

对每个 session 执行后续步骤。

### Step 2: 读取主 session 日志

ReadFile 读取 chat.jsonl，从中提取：

1. **用户消息**：所有 `role=user, agent=user` 的条目——用户的指令、反馈、修正
2. **系统回复**：所有 `type=ContentPart` 的条目——agent 回复给用户的文本
3. **工具调用**：所有 `type=ToolCall` + 对应的 `type=ToolResult`——系统实际执行了什么
4. **子 agent 事件**：所有 `type=SubagentEvent`——记录哪些子 agent 被调度、对应的 session_id

### Step 3: 读取子 agent session

从 Step 2 中的 SubagentEvent 提取子 agent 的 session 路径，ReadFile 读取其 chat.jsonl。

重点关注以下子 agent 的对话（创作决策和生成执行发生在这里）：
- `video-director`：镜头设计、状态规划决策
- `video-camera`：视频生成 prompt、生成模式选择
- `video-editor`：组装参数、转场选择
- `art-designer`：参考图生成
- `video-composer`：BGM 设计

每个子 agent session 同样提取用户消息（来自 producer 的调度 prompt）、工具调用和结果。

### Step 4: 构建用户意图清单

从主 session 的用户消息中，提取所有明确的指令和期望：

- **创作指令**：主题、风格、时长、画面比例、语言
- **具体要求**：角色数量、场景数量、特定镜头要求（如三视图、特写）
- **修正反馈**：用户在后续轮次中的纠正（"我要的是 X 不是 Y"、"这不对"）
- **满意/不满表达**：用户对中间结果的评价

将每条意图记录为：`{内容, 时间戳, 原文}`

### Step 5: 提取 Bug 记录

逐条检查用户的修正反馈和不满表达，判断是否为 Bug：

**判定条件（必须全部满足）：**
1. 用户在之前的消息中明确给出了指令 A
2. 系统的产出或行为是 B，且 B 与 A 明确矛盾
3. 这个矛盾是客观的——任何用户都会认为 B 不符合指令 A

**不是 Bug 的情况：**
- 用户对质量不满但没有明确指令被违反（"画面太暗"——除非用户之前说过"要明亮风格"）
- 用户的偏好未被满足但未事先声明（"我不喜欢这个配色"——之前没说过配色要求）
- 工具/API 的能力限制导致的降级（"视频只有 4 秒不是 5 秒"——生成模型的固有限制）

对每个 Bug 生成记录：

```yaml
- id: b_{session前6位}_{序号}
  description: "一句话描述：用户要求 X，系统做了 Y"
  user_instruction: "用户原文（引用）"
  system_output: "系统实际行为描述"
  source:
    session: "{uuid}"
    user_message_timestamp: {用户指令的时间戳}
    evidence_timestamp: {矛盾证据的时间戳}
    extracted_at: "{当前日期 YYYY-MM-DD}"
```

### Step 6: 提取知识记录

从对话中识别以下模式，提取为知识条目：

1. **用户明确表达的改进建议**："下次应该这样做"、"如果能 XX 就更好了"
2. **用户的偏好声明**："我喜欢 XX 风格"、"不要 XX"
3. **重复修正模式**：用户在多个 shot/事件上给出同类反馈，说明系统缺少某个通用规则
4. **agent 的成功策略**：子 agent 在重试后找到的有效方案（从 ToolCall 的 attempts 中发现）

对每条知识生成条目：

```yaml
- id: k_{session前6位}_{序号}
  rule: "在[什么情况]下，[怎么做]，因为[为什么]"
  rationale: "这条规则背后的原因（从 session 证据总结，让没看过 session 的人也能理解）"
  problem: "该知识解决什么问题（用于检索匹配）"
  eval_method: "评估方式（验证时按此方法评估效果）"
  tags: [角色tag, 主题tag]
  source:
    session: "{uuid}"
    evidence: "关键证据引用（用户反馈原文 或 agent 行为前后对比）"
    extracted_at: "{当前日期 YYYY-MM-DD}"
  status: pending
  score: null
  validation: null
```

**关于 problem 和 eval_method**：
- `problem`：描述这条知识针对的具体问题，便于后续匹配优化点
- `eval_method`：明确如何验证效果。常见的评估方式：
  - `metrics: error_count` — 对比错误数
  - `metrics: retry_count` — 对比重试次数
  - `metrics: duration` — 对比耗时
  - `vlm: {评估维度}` — 用 VLM 评估生成质量（如面部一致性、风格匹配度）
- 如果无法定义清晰的 eval_method，说明这条知识不可验证，不要提取

**tags 词汇表：**
- 角色 tag：`screenwriter`, `director`, `camera`, `composer`, `editor`, `art-designer`
- 主题 tag：`prompt`, `生成模式`, `构图`, `运镜`, `色彩`, `风格`, `转场`, `音频`, `字幕`, `时长`, `状态一致性`, `角色设计`, `场景设计`

每条 rule 必须：
- 包含三要素：**什么情况下** + **怎么做** + **为什么**（如："人物特写镜头中，使用 reference_to_video 模式替代 text_to_video，因为前者面部一致性显著更好"）
- 让没看过 session 的人也能理解——不能只写结论，要写清前提条件
- 不包含 session 特有的信息（角色名、项目名等）
- 抽象为可复用的通用规则

### Step 7: 提取优化点

优化点记录 session 中具体哪个步骤出了什么问题，为后续知识验证提供基础数据。

遍历 op graph 中的每个 delegation 节点，识别以下情况：
1. **子 agent 有错误/重试**：tool_call 中 is_error=true，或同一操作重复调用
2. **用户给出负面反馈**：在该 delegation 完成后用户表达不满
3. **agent 改变策略**：子 agent 在重试时修改了参数（从 args_preview 对比前后差异）

对每个优化点记录：

```yaml
- id: opt_{session前6位}_{序号}
  session: "{uuid}"
  delegation_id: "delegation_N"
  agent: "{子agent名}"
  problem: "具体发生了什么问题"
  expected_benefit: "如果优化成功，预期改善什么"
  eval_method: "评估方法（与匹配的知识条目对应）"
  baseline_metrics:
    error_count: N
    tool_call_count: N
    duration_s: N
  task_params:
    prompt: "原始 Task 调用的 prompt（从 op graph delegation 节点的 intent 字段提取）"
    context_files: ["从 op graph 中 consumed_by 边关联的 resource 节点的 path 提取"]
```

**提取 task_params 的方法**：
- `prompt`：delegation 节点的 `prompt_preview` 或 `intent` 字段
- `context_files`：找到该 delegation 下所有 tool_call 通过 `consumed_by` 边关联的 resource 节点，提取其 `path`

### Step 8: 写入输出文件

用 WriteFile 将结果写入 session 目录：

- Bug 记录 → `output/.sessions/{uuid}/bugs.yaml`
- 知识条目 → `output/.sessions/{uuid}/knowledge-pending.yaml`
- 优化点 → `output/.sessions/{uuid}/optimization-points.yaml`

如果没有提取到任何 Bug，写入空列表 `[]`。知识和优化点同理。

写入完成后，汇总报告：
- 分析的 session UUID
- 提取的 Bug 数量，逐条列出 description
- 提取的知识数量，逐条列出 rule
- 提取的优化点数量，逐条列出 problem

## 输出

每个分析的 session 产出三个文件：
- `output/.sessions/{uuid}/bugs.yaml`
- `output/.sessions/{uuid}/knowledge-pending.yaml`
- `output/.sessions/{uuid}/optimization-points.yaml`

## 错误处理

- **session 目录不存在**：报告 UUID 未找到，跳过。
- **chat.jsonl 为空或格式错误**：报告文件路径，跳过该 session。
- **session 无用户消息**：可能是纯 subagent session，跳过（只分析含 `role=user, agent=user` 的 session）。
- **日志过长无法一次读取**：分段 ReadFile（使用 offset + limit），逐段分析。
