# Agent 自动迭代系统

## 背景

用户通过 video producer 系统创作视频时，会在对话中表达个人喜好、对生成结果的满意度等。从这些对话中可以提取三类信息：

1. **通用 bug**：对所有用户都是错误的系统问题（如用户要求三视图，系统给出单视图）
2. **通用领域知识**：对所有用户都适用的经验，能提升视频制作质量
3. **个性化偏好**：仅对特定用户适用的偏好信息

## 两条处理线

### Bug 线 (1)

提取 → 记录 → 统计报表（供系统开发人员参考）

报表形式：
- 每日报表：昨日新增 bug 列表 + 量级
- 全量报表：历史未解决问题列表 + 量级

不自动修复，供人工决策。

### 知识线 (2)(3)

提取 → 待验证知识库 → 离线验证（在已有项目上验证收益）→ 上线（写入公共/个人知识库）→ 线上监测用户反馈

## 设计决策

- 新建独立 agent（非扩展 optimizer），专门针对 video producer 系统
- bug 不做去重归并，每次出现独立计数，频率即严重程度信号
- 数据源：producer 的 chat.jsonl + 所有子 agent 的执行日志
- 触发方式：项目完成后自动触发分析

## 知识验证

依赖 Operation Graph（见 operation-graph-design.md）作为前置实现。

验证方式：在同一个项目上，对比注入知识前后的 op graph 指标：
- 错误步骤数（failed ops）
- 重试次数（attempts）
- 总耗时
- token 消耗（需在 op graph Operation Edge 的 actual 中补 token_usage 字段）

### 前置：op graph 补充 token_usage

在 Operation Edge 的 actual 中增加：
```json
"actual": {
  "token_usage": {
    "input_tokens": 1200,
    "output_tokens": 350
  }
}
```

## 知识注入

### 注入方式

- **bug**：不注入。只出报表，人工修复后改 guide/workflow 文件
- **领域知识 + 个性化偏好**：存入知识库，运行时按需注入

### 注入机制：中间层自动注入

在 Task 工具执行层，根据 `subagent_name` + `user_id` 自动从知识库检索相关条目，追加到 `context_files`。producer 和子 agent 均无感知。

### 检索方式：tag 匹配

每条知识条目标注 tag，中间层按 tag 过滤：
- **角色 tag**：匹配 subagent_name（如 `camera`、`director`、`editor`）
- **主题 tag**：匹配知识主题（如 `构图`、`运镜`、`色彩`）
- 公共知识按角色 tag 过滤
- 个人知识按角色 tag + user_id 过滤

暂不做语义检索。

### 知识库存储结构

每个角色一个 YAML 文件，内含多条条目：

```
knowledge/
  public/                    # 公共知识（所有用户共享）
    camera.yaml              # 按角色分文件
    director.yaml
    ...
  users/                     # 个人知识（per user）
    {user_id}/
      camera.yaml
      director.yaml
      ...
```

### 注入上限

每次调度子 agent 最多注入 20 条知识。超出时按知识条目的 `score`（验证收益分数）排序，取 top 20。

## 知识条目格式

```yaml
- id: k_001
  rule: "人物特写镜头使用 reference_to_video 模式比 text_to_video 面部一致性更好"
  problem: "人物特写使用 t2v 时面部不一致导致重试"
  eval_method: "VLM 对比参考图与视频帧的人脸匹配度"
  tags: [camera, 生成模式]
  source: { session: "abc123", extracted_at: "2026-04-08" }
  status: pending  # pending → verified → online → deprecated
  score: null      # 验证收益分数，verified 后填入，用于注入排序
  validation: null  # 验证结果，verified 后填入
```

- `rule`：一句话可操作规则，注入时只取此字段
- `problem`：该知识解决什么问题（用于匹配优化点、检索相关知识）
- `eval_method`：评估方式（验证时按此方法评估效果）。如果提取时无法定义清晰的评估方式，该知识不具备可验证性，不应进入 pending 库
- `tags`：角色 tag + 主题 tag，用于检索
- `source`：可追溯来源
- `status`：生命周期状态
- `score`：验证收益量化值，超出注入上限时按此排序

## 优化点格式

evolver 分析每个 session 时，除了 bug 和 knowledge，还提取**优化点**——记录哪里出了什么问题、预期什么收益、怎么评估。优化点是知识验证的基础数据。

```yaml
- id: opt_abc123_001
  session: "abc123"
  delegation_id: "delegation_5"
  agent: camera
  problem: "人物特写使用了 t2v，面部不一致导致 2 次重试"
  expected_benefit: "使用 ref2v 可避免面部不一致，减少重试"
  eval_method: "VLM 对比参考图与视频帧人脸匹配度"
  baseline_metrics:
    error_count: 2
    tool_call_count: 5
    duration_s: 120.5
  task_params:
    prompt: "生成 shot_3 的视频..."
    context_files: ["output/abc123/project/story-graph.json", "..."]
```

- `session` / `delegation_id`：定位到 op graph 中的具体步骤
- `problem`：具体发生了什么问题
- `expected_benefit`：如果优化成功，预期改善什么
- `eval_method`：评估方法（与知识条目的 eval_method 对应）
- `baseline_metrics`：该步骤的原始 metrics（从 op graph 提取）
- `task_params`：原始 Task 调用参数（prompt + context_files），用于重放

产出文件：`output/.sessions/{uuid}/optimization-points.yaml`

## 知识验证流程

验证是机械化的，evolver 已在提取阶段完成了分析判断。

1. **取一条 pending knowledge**（含 problem、eval_method）
2. **从 optimization points 中匹配**：按 problem + tags 找到相关优化点（优化点已包含：用哪个 session、重跑哪个阶段、baseline metrics、原始 task_params）
3. **重跑一次**：用优化点的 task_params 调用对应子 agent，注入这条 knowledge 的 rule
4. **评估**：按 eval_method 评估重跑结果（metrics 对比、VLM 评估等）
5. **计算 score**：对比 baseline_metrics，量化收益
6. **更新知识条目**：score > 阈值 → status=verified；多个优化点取平均
7. **通用/个性化判定**：跨 10 个不同用户的 session 验证有效 → `knowledge/public/`；仅个别用户有效 → `knowledge/users/{user_id}/`

## 线上监测

### 数据流

```
Session 运行中:
  Task 注入知识 → 写入 {session_dir}/knowledge-injected.yaml
                    (记录 subagent, role, knowledge_ids, timestamp)

Session 结束后:
  Evolver workflow-monitor.md:
    读取 knowledge-injected.yaml + chat.jsonl
    → 检查每条注入知识对应阶段的用户反馈
    → 写入 {session_dir}/knowledge-feedback.yaml

定期执行:
  scripts/knowledge-monitor.py:
    扫描所有 session 的 knowledge-feedback.yaml
    → 按 knowledge_id 聚合 positive/negative/neutral 计数
    → negative_count ≥ 3 且 total ≥ 3 → 自动 deprecated
    → 输出 knowledge/monitor-report.yaml
```

### 反馈判定规则

- **positive**：用户在该阶段后无负面反馈，流程正常继续
- **negative**：用户明确要求重做该阶段产出，或指出与该知识 rule 相关的问题
- **neutral**：用户反馈与该知识内容无关，或 session 中断无法判断

### 自动降级

- 负面计数 ≥ 3 且总反馈 ≥ 3 → status 改为 deprecated
- deprecated 的条目在 Task 注入时被 `status=online` 过滤掉，不再注入
- 降级报告写入 `knowledge/monitor-report.yaml`，便于人工审查

## 三类信息的定义与判定

| 类型 | 定义 | 判断标准 |
|------|------|---------|
| bug | 系统产出与用户指令明确矛盾 | 对所有用户都是错误、不可接受 |
| 领域知识 | 让产出更好的经验 | 跨用户离线验证均有效 |
| 个性化偏好 | 让产出更好的经验 | 仅对个别用户离线验证有效 |

### 提取流程

分析 agent 从对话中提取时，先区分 bug 和知识：
- **bug**：系统产出与用户指令明确矛盾（答非所问、功能缺失），直接归为 bug
- **知识**：用户表达的改进方向（更好的做法、偏好），提取后统一先存入待验证库

### 领域知识 vs 个性化偏好的判定

提取阶段不区分。通过离线验证阶段判定：
- 同一条知识在多个用户的项目上验证均有效 → 领域知识 → 写入公共知识库
- 只对个别用户有效 → 个性化偏好 → 写入该用户的个人知识库

## 分析 agent 定位

- 独立离线 agent，不挂在 producer 下
- 触发方式：项目完成后由外部调用（脚本或 API），传入 session 路径
- 可批量分析多个 session（跨用户聚合需要）

### 需要的能力

- 读取 producer + 所有子 agent 的 chat.jsonl
- 读取 op graph（operation-graph.json）
- 读写知识库（knowledge/）
- 读写 bug 记录

具体 agent.yaml、system.md、工具集待设计。

## Bug 报表机制

- **记录**：分析 agent 每次 session 分析后，将 bug 写入本地文件
- **报表**：定时脚本每天汇总生成，不用 agent
  - 每日报表：昨日新增 bug 列表 + 量级
  - 全量报表：历史未解决问题列表 + 量级

## 离线验证流程

一条知识提取后先存入待验证库（status=pending），通过离线验证后才上线。

验证标准：
- **个人知识**：在该用户的 3 个已有项目上验证，均有收益 → verified → 写入个人知识库
- **通用知识**：在 10 个不同用户的项目上验证，均有收益 → verified → 写入公共知识库

验证执行：自动选取项目、自动重跑、自动对比，无人工介入。

按知识涉及的阶段分级控制成本：
- **纯 LLM 阶段**（编剧、导演、剪辑规划）：只重跑该阶段，成本低
- **生成 API 阶段**（摄影、美术、作曲）：只挑与该知识相关的 1-2 个 shot/资源验证，不跑整个项目

对比指标：注入知识前后的 op graph 指标（failed ops、attempts、耗时、token）。

## 触发条件

分析 agent 由 **op graph 实时解析层** 检测 session 状态变化后触发，采用**增量分析**机制：记录每个 session 已分析到的 chat.jsonl offset，每次只分析新增部分。

### 两层分析架构

**第一层：op graph 实时轻量分析（无 LLM 开销）**
- 从已解析的 op graph 中自动检测：error_count 升高、同一工具反复重试、duration 异常
- 纯代码逻辑，随轮询实时更新

**第二层：evolver LLM 增量分析（由三类信号触发）**
- 每次只分析上次 offset 之后的新增对话
- 提取 bug / knowledge / optimization points，追加到已有产出文件

### 触发信号

三类信号均可触发增量分析：

| 信号类型 | 检测方式 | 示例 |
|---------|---------|------|
| 用户显式反馈 | chat.jsonl 中新增用户消息（offset 之后出现 role=user 的修改/评价类消息） | "颜色太暗"、"转场太快"、要求重做某阶段 |
| 系统失败 | op graph 中新增 error / 重试（offset 之后出现 is_error=true 或同一 tool_call 连续重试 ≥ 2 次） | tool_call 失败、degraded shot、子 agent 报错 |
| 阶段完成 | op graph 中检测到新产出或 session 结束 | video_N.mp4 产出、用户下载、空闲超时 |

设计理由：
- **用户反馈**是最有价值的分析素材（含 bug 信号、偏好信号），不应依赖"是否产出新成片"才触发。用户可能给完反馈就离开，不走到下一轮生成。
- **系统失败**是隐式反馈——用户没说什么，但 error / 重试已暴露问题。这些信号不需要等 session 结束才分析。
- **阶段完成**保留原有兜底能力。

### 增量分析机制

**offset 记录**：`_evolver_state: dict[str, int]`，key 为 session_id，value 为已分析到的 chat.jsonl 行号。

**触发条件**：检测到上述任一信号，且 chat.jsonl 当前行数 > 已记录 offset + 阈值（避免每条消息都触发，默认阈值 5 行）。

**分析范围**：evolver 只读取 offset 之后的新增对话，但可引用 offset 之前的上下文（如项目文件、之前的分析产出）来理解新增内容。

**产出追加**：新提取的 bug 追加到 `bugs.yaml`，新知识追加到 `knowledge/pending/`，新优化点追加到 `optimization-points.yaml`。

### 实现细节

**触发链路**：
```
前端 2s 轮询 → GET /api/sessions/{sid}/op-graph
             → 解析 chat.jsonl（mtime 缓存，文件未变时不重新解析）
             → _detect_analysis_signal() 每次轮询都执行
               → 检测三类信号 + offset 差值 > 阈值
               → 满足条件 → asyncio.create_task(_run_evolver(session_id, offset))
               → 更新 _evolver_state[session_id] = current_line

下载按钮 → GET /api/download/ → 同样走上述逻辑（兜底）
```

**防抖**：同一 session 的 evolver 不并发执行。如果上一次增量分析仍在运行，跳过本次触发，等下次轮询再检测。

**空闲超时窗口**：只对空闲 10min ~ 24h 的 session 触发。超过 24h 的历史 session 不触发，避免服务启动时批量触发 evolver。

**op graph metrics 字段**（用于第一层实时分析和后续知识验证对比）：
- `metrics.total_tokens`：input_other / output / input_cache_read / input_cache_creation
- `metrics.total_input_tokens` / `metrics.total_output_tokens`：汇总值
- `metrics.total_duration_s`：session 首尾消息时间差
- `metrics.error_count`：is_error=true 的 tool_call 数
- `metrics.token_by_agent`：按 agent 名分组的 token 消耗
- 每个 delegation 节点附带 `duration_s` 和 `token_usage`
- 每个 tool_call 节点附带 `duration_s`

## 实现计划

两条并行流 + 合流，共 7 个阶段。

### 流 A：提取 + 记录（不依赖 op graph）

**A1. 分析 agent 基础**

实现内容：
- `src/kimi_cli/agents/video-agent-evolver/agent.yaml` — 工具：ReadFile, WriteFile, Glob, Grep
- `src/kimi_cli/agents/video-agent-evolver/system.md` — 角色定义、三类信息判定标准
- `src/kimi_cli/agents/video-agent-evolver/workflow-extract.md` — 从 chat.jsonl 提取 bug + 知识

验证方式：
- 准备 3 个已有 session（含明显 bug、含领域知识信号、含个性化偏好信号各一个）
- 手动运行分析 agent，检查提取结果：bug 是否准确识别、知识是否合理提取、两者不混淆

**A2. Bug 记录 + 报表脚本**

实现内容：
- bug 记录存储格式定义（本地 YAML 文件，由 workflow-extract.md Step 5 写入 `output/.sessions/{uuid}/bugs.yaml`）
- `scripts/bug-report.sh` — 汇总脚本，扫描所有 session 的 bugs.yaml，生成：
  - `reports/bugs/daily-{YYYY-MM-DD}.md` — 当日日报（按 extracted_at 筛选）
  - `reports/bugs/full-report.md` — 全量报表（按 session 分组）

验证方式：
- 用 A1 的测试 session 跑完分析 agent，检查 bug 记录文件是否正确写入
- 手动写入多条 bug 记录（模拟多日多 session），运行报表脚本，检查日报和全量报表的计数、排序是否正确

**A3. 知识提取 → 待验证库**

实现内容：
- 待验证知识库目录结构（`knowledge/pending/`）
- 分析 agent 写入知识条目的逻辑（生成 id、tags、source，status=pending）
- 知识条目去重逻辑（同一条 rule 不重复写入，但记录多次出现的 source）

验证方式：
- 用测试 session 跑分析 agent，检查待验证库中条目格式是否正确、tags 是否合理
- 跑两个含相似知识信号的 session，检查去重是否生效

### 流 B：Operation Graph（前置依赖）

**B1. Op graph 数据模型 + 工具实现**

实现内容：
- 见 operation-graph-design.md Phase 1-3
- 额外：Operation Edge 的 actual 中补 `token_usage` 字段

验证方式：
- 单元测试：数据模型序列化/反序列化
- 集成测试：在一个测试项目上跑完整 producer pipeline，检查 operation-graph.json 是否正确记录所有步骤、时间、token

### 合流：验证 + 注入 + 监测（依赖 A + B）

**C1. 离线验证流程**

实现内容：
- 更新 `workflow-extract.md`：evolver 分析 session 时额外提取 optimization-points.yaml（含 problem、expected_benefit、eval_method、baseline_metrics、task_params）
- 知识条目增加 `problem` 和 `eval_method` 字段
- `src/kimi_cli/agents/video-agent-evolver/workflow-validate.md` — 验证流程（供 evolver 参考，实际执行由脚本完成）
- `scripts/knowledge-validate.py` — 验证脚本：
  - 读取 pending knowledge + optimization points
  - 按 problem/tags 匹配知识 ↔ 优化点
  - 用 KimiCLI 重跑对应子 agent 阶段（注入知识）
  - 按 eval_method 评估（metrics 对比 / VLM 评估）
  - 计算 score，回写 status 到知识条目
  - 跨用户聚合：通用 → knowledge/public/，个性化 → knowledge/users/

验证方式：
- 手动构造一条确定有效的知识 + 对应的优化点，放入 pending 库
- 运行验证脚本，检查：是否正确匹配优化点、是否正确重跑、eval_method 是否执行、score 是否合理、status 是否更新
- 手动构造一条无效知识，检查验证后 score 低于阈值

**C2. Task 中间层知识注入**

实现内容：
- 修改 `src/kimi_cli/tools/multiagent/task.py` — Task 执行时按 subagent_name + user_id 从知识库检索 status=online 的条目
- tag 匹配 + score 排序 + top 20 截断
- 将匹配的 rule 列表生成临时文件，追加到 context_files

验证方式：
- 在知识库中写入几条 status=online 的测试条目（不同 tags）
- 调度不同子 agent，检查：camera 只收到 camera 相关知识、director 只收到 director 相关知识
- 写入 25 条知识，检查是否只注入 top 20
- 知识库为空时，检查不影响正常调度

**C3. 线上监测**

实现内容：
- `src/kimi_cli/agents/video-agent-evolver/workflow-monitor.md` — evolver 子流程，检查本次 session 中被注入知识的用户反馈，写入 knowledge-feedback.yaml
- `scripts/knowledge-monitor.py` — 聚合脚本，扫描所有 session 的 feedback，按 knowledge_id 累计 positive/negative/neutral 计数，negative ≥ 3 自动 deprecated
- 注入日志由 C2 的 Task 中间层写入 `{session_dir}/knowledge-injected.yaml`
- 输出 `knowledge/monitor-report.yaml` 汇总报告

验证方式：
- 手动构造一个 session，其中用户对某个注入知识给出明确负面反馈
- 运行监测脚本，检查该条目负面计数是否 +1
- 模拟连续 3 次负面反馈（3 个 session），检查 status 是否自动变为 deprecated
- 再次调度子 agent，检查 deprecated 条目不再被注入（被 status=online 过滤掉）

### 实现顺序

```
Week 1-2:  A1（分析 agent 基础）+ B1（op graph）并行
Week 3:    A2（bug 报表）+ A3（知识提取）
Week 4:    C2（知识注入中间层）
Week 5:    C1（离线验证）
Week 6:    C3（线上监测）
```
