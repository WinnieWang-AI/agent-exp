# 需求确认、项目初始化、调度编剧

## 输入

用户的创意描述（可能一句话，也可能很详细）。

## 步骤

### Step 1: 需求确认

从用户输入中提取以下 5 项：

| 项 | 说明 | 默认值 |
|----|------|--------|
| 主题 | 故事主题或描述 | 无（必须有） |
| 风格 | 视觉风格关键词 | 无（必须确认） |
| 画面比例 | 16:9 / 9:16 / 1:1 | 16:9 |
| 语言 | 对白语言 | 中文 |
| 时长 | 目标视频时长 | 1min |

- 如果用户一句话里已经包含了全部信息，直接进入 Step 2，不重复确认。
- 如果缺少必要信息（主题或风格），合并为一个问题问用户，不要逐项追问。
- 画面比例、语言、时长如果用户没说，使用默认值，在回复中告知。

### Step 2: 项目初始化

用 ManageVideoProject 创建项目目录和标准子目录：

```
ManageVideoProject(
  action="init",
  project_path="${SESSION_OUTPUT_DIR}/{project_name}",
  metadata={
    "session_ids": {
      "screenwriter": "screenwriter_{project_name}",
      "director": "director_{project_name}",
      "art": "art_{project_name}",
      "camera": "camera_{project_name}",
      "composer": "composer_{project_name}",
      "editor": "editor_{project_name}"
    }
  }
)
```

`project_name` 根据主题生成一个简短的英文标识（如 `tortoise-and-hare`）。

init 会自动创建 `assets/shots/`、`assets/images/`、`assets/frames/`、`assets/audio/`、`output/` 等子目录。

### Step 3: 调度编剧

用 Task 调度 `video-screenwriter`，使用 session_id 保持状态：

```
subagent_name: "video-screenwriter"
session_id: "screenwriter_{project_name}"
prompt: 创意简报内容（见下方）
```

**创意简报必须包含且仅包含：**
- 主题：用户的故事描述
- 风格：视觉风格关键词（英文，用于 style_prefix）
- 时长：如 "1min"
- 画面比例：如 "16:9"
- 语言：如 "中文"
- 项目路径：绝对路径

**禁止在 prompt 中：**
- 指定数据结构、字段名、JSON 格式
- 指定场景数、角色数、幕数
- 指定叙事手法或创作方向
- 复制粘贴 schema 定义

编剧有自己的 schema 和工作流，会自主决定故事结构。

### Step 4: 进入制作阶段

编剧完成后，立即用 ReadFile 加载 `${AGENT_DIR}/workflow-production.md`，按其中的步骤调度导演。不等待用户确认剧本。

## 错误处理

- **用户需求不明确**：回到 Step 1 补充确认。
