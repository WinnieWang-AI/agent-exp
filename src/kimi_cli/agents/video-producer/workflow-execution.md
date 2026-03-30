# 执行阶段：摄影 + 作曲 → 剪辑 → 交付

## 输入

项目目录下已有导演产出：
- `meta.json` — 视频规格、风格
- `events.json` — 事件列表
- `states.json` — 状态节点 + 参考图路径
- `shots.json` — 镜头列表 + shot_order + bgm + 对白
- `assets/images/` — 参考图

## 步骤

### Step 1: 并行调度摄影和作曲

同时用 Task 调度两个子 agent：

#### 1a. 调度摄影（video-camera）

```
subagent_name: "video-camera"
session_id: "camera_{project_name}"
prompt: 项目路径和执行指令
context_files: ["{project_path}/meta.json", "{project_path}/shots.json", "{project_path}/states.json"]
```

**prompt 中必须包含且仅包含：**
- 项目路径（绝对路径）
- 按 shot_order 逐 shot 生成视频

**禁止在 prompt 中：**
- 指定 prompt 内容或生成模式
- 指定视频生成参数
- 复制粘贴 shots.json 的内容

#### 1b. 调度作曲（video-composer）

```
subagent_name: "video-composer"
session_id: "composer_{project_name}"
prompt: 项目路径和执行指令
context_files: ["{project_path}/meta.json", "{project_path}/shots.json"]
```

**prompt 中必须包含且仅包含：**
- 项目路径（绝对路径）
- 从 shots.json 的 bgm 字段生成背景音乐

**禁止在 prompt 中：**
- 指定音乐风格、乐器、prompt 内容
- 指定分段方式

### Step 2: 等待并行任务完成

两个任务独立执行。任一任务完成后，检查其结果：

- **摄影完成**：读取 `{project_path}/generation-status.json`，记录成功/失败 shot 数
- **作曲完成**：读取 `{project_path}/music-status.json`，记录成功/失败分段数

两个任务都完成后，汇总结果：
- 视频生成：成功 N / 失败 M / 总 T
- BGM 生成：成功 N / 失败 M / 总 T

如果视频生成成功率 < 70%，上报用户，等待指示（可选重试失败的 shot 或继续组装）。

### Step 3: 调度剪辑（video-editor）

```
subagent_name: "video-editor"
session_id: "editor_{project_name}"
prompt: 项目路径、输出路径和执行指令
context_files: ["{project_path}/meta.json", "{project_path}/shots.json"]
```

**确定输出路径**：调度剪辑前，先用 `Glob("{project_path}/output/attempt_*.mp4")` 查看已有成片数量 N，本次输出路径为 `{project_path}/output/attempt_{N+1}.mp4`。首次为 `attempt_1.mp4`。

**prompt 中必须包含且仅包含：**
- 项目路径（绝对路径）
- 输出路径（上一步确定的绝对路径）
- 按 shot_order 组装成片：拼接、转场、BGM 叠加、字幕

**禁止在 prompt 中：**
- 指定 FFmpeg 参数
- 指定转场时长或字幕格式

### Step 4: 交付

剪辑完成后，向用户汇报：
- 成片路径
- 总时长
- 视频片段使用情况（成功数 / 跳过数）
- BGM 情况（有/无/部分缺失）
- 字幕情况（有/无）

如果有缺失（shot 或 BGM 失败），说明对成片的影响。

提示用户可以查看成片。

### Step 5: 用户反馈

用户可能：
- **满意**：项目完成
- **要求修改**：用 ReadFile 加载 `${AGENT_DIR}/workflow-modify.md`，按其中的步骤处理。
- **要求完整重做**：从 Step 1 重新开始（仍使用同一 session_id，子 agent 知道之前的问题）

## 错误处理

- **摄影全部失败**：不调度剪辑，上报用户。
- **作曲全部失败**：仍调度剪辑（成片无 BGM），告知用户。
- **剪辑失败**：原样转达用户错误信息。
