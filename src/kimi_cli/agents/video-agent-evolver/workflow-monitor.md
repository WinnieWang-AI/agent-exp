# 知识注入效果监测

## 前置条件

本流程在 workflow-extract.md 的分析完成后执行。需要以下文件存在：

- `{session_dir}/knowledge-injected.yaml` — Task 中间层记录的注入日志
- `{session_dir}/chat.jsonl` — session 对话日志

如果 knowledge-injected.yaml 不存在，说明本 session 未注入任何知识，跳过本流程。

## 输入

knowledge-injected.yaml 格式：
```yaml
- subagent: video-camera
  role: camera
  knowledge_ids: [k_abc123_001, k_abc123_002]
  timestamp: 1712345678.0
```

## 步骤

### Step 1: 读取注入记录

ReadFile 读取 `{session_dir}/knowledge-injected.yaml`，获取本 session 中被注入的知识条目 ID 列表。

### Step 2: 读取知识原文

对每个 knowledge_id，从知识库中读取对应条目的 `rule`，以便后续在对话中定位相关行为。

知识库路径：
- `knowledge/public/{role}.yaml`
- `knowledge/users/{user_id}/{role}.yaml`

### Step 3: 检查用户反馈

对每个注入的知识条目，在 chat.jsonl 中检查：

1. **定位相关行为**：找到该知识被注入的子 agent 阶段（通过 timestamp 和 subagent 对应到 op graph 中的 delegation）
2. **检查用户对该阶段结果的反馈**：在 delegation 完成后的用户消息中，查找：
   - **正面信号**：用户确认、继续下一步、无修改要求
   - **负面信号**：用户要求重做、表达不满、明确指出问题
   - **无关**：用户的反馈与该知识的内容无关

判定规则：
- 如果用户在该阶段后**未给出任何负面反馈**且流程正常继续 → `positive`
- 如果用户**明确要求重做该阶段的产出**或**指出与该知识规则相关的问题** → `negative`
- 如果用户的反馈**与该知识的 rule 内容无关** → `neutral`

### Step 4: 写入反馈记录

用 WriteFile 将反馈写入 `{session_dir}/knowledge-feedback.yaml`：

```yaml
- knowledge_id: k_abc123_001
  role: camera
  rule: "人物特写镜头使用 reference_to_video 模式"
  feedback: positive | negative | neutral
  evidence: "用户确认了结果，继续下一步" | "用户说'面部还是不对，重新生成'"
  session: "{uuid}"
  timestamp: 1712345678.0
```

**注意**：
- 每个 knowledge_id 在本 session 中只产生一条 feedback 记录
- `evidence` 字段引用用户原文（简短摘要），便于追溯
- 如果无法判断反馈（如 session 中途中断），标记为 `neutral`

## 输出

- `{session_dir}/knowledge-feedback.yaml`

## 错误处理

- knowledge-injected.yaml 不存在 → 跳过，不报错
- 知识库中找不到对应 ID 的条目 → 跳过该条目（可能已被删除）
- chat.jsonl 中找不到对应阶段的用户反馈（如 session 中断）→ 标记 neutral
