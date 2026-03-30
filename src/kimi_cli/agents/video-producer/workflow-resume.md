# 会话恢复

当用户说"继续"或消息以 `[Session resumed.` 开头时，加载本文件。

## 输入

中断的对话，项目可能处于任何阶段。

## 步骤

### Step 1: 定位项目

用 Glob 查找项目目录：

```
Glob("{working_dir}/projects/*/meta.json")
```

- 只找到一个：直接使用。
- 找到多个：列出让用户选择。
- 找不到：可能还没开始，从 workflow-setup Step 1 开始。

### Step 2: 推断进度

项目进度从文件系统直接推断，不依赖额外状态文件：

| 已有文件 | 当前阶段 | 恢复动作 |
|----------|---------|---------|
| 无 `meta.json` | 未开始 | 加载 workflow-setup，从 Step 1 开始 |
| 有 `meta.json` + `entities.json` + `outline.json` + `act-*.json`，无 `events.json` | 剧本已完成 | 加载 workflow-production，从 Step 1 开始 |
| 有 `shots.json`，无 `assets/images/*.png` | 制作计划已完成，参考图未开始 | 加载 workflow-production，从 Step 4（调度美术）开始 |
| 有 `shots.json` + `assets/images/*.png`，无 `generation-status.json` | 参考图已完成 | 加载 workflow-execution，从 Step 1 开始 |
| 有 `generation-status.json` 或 `music-status.json` | 执行进行中 | ReadFile 查看状态文件，判断哪些完成哪些未完成，恢复执行 |
| 有 `output/attempt_*.mp4` | 已有成片 | 向用户展示最新成片，等待反馈 |

### Step 3: 恢复 session

用 ReadFile 读取 `{project_path}/project.json`，获取 session_ids。如果 project.json 不存在，按命名约定 `{role}_{project_name}` 构造。

子 agent 的对话历史文件如果还在，session_id 会自动恢复其记忆。如果对话历史已丢失，session_id 会创建新的空 session——此时需要重传 context_files。

### Step 4: 汇报并继续

向用户简要说明：
- 检测到项目 `{project_name}`
- 当前在 XX 阶段
- 即将继续 XX

然后加载对应的 workflow 文件，从恢复点继续执行。

## 输出

恢复到正确的工作流阶段，继续制作。

## 错误处理

- 项目目录存在但关键文件缺失（如有 events.json 但无 entities.json）→ 告知用户项目状态异常，列出已有和缺失文件，由用户决定。
- session 对话历史丢失 → 重传 context_files，在 prompt 中说明这是恢复执行。
