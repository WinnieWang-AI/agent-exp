# 制作执行

## 输入

项目目录下已有编剧产出：
- `meta.json` — 标题、视频规格、风格
- `entities.json` — 角色、场景、道具
- `outline.json` — 故事大纲
- `act-1.json`、`act-2.json`... — 各幕场景详情

## 步骤

### Step 1: 调度导演

用 Task 调度 `video-director`，使用 session_id 保持状态：

```
subagent_name: "video-director"
session_id: "director_{project_name}"
prompt: 项目路径和执行指令（见下方）
context_files: ["{project_path}/meta.json", "{project_path}/entities.json", "{project_path}/outline.json"]
```

**prompt 中必须包含且仅包含：**
- 项目路径（绝对路径）
- 执行完整的导演工作流（事件拆解 → 实体状态规划 → 美术设计 → 镜头设计 → 校验）

**禁止在 prompt 中：**
- 指定事件数量、镜头数量、时长分配方式
- 指定视觉风格细节、镜头语言
- 复制粘贴编剧的产出内容

导演有自己的工作流和 schema，会自主完成全部制作计划。

### Step 2: 汇报制作计划

导演完成后，向用户简要汇报：
- 事件数 / 镜头数 / 总时长
- 校验结果（PASS / FAIL）
- 如有 FAIL，列出主要错误

提示用户可以在界面上预览制作计划（分镜板视图）。

如果导演报错，原样转达给用户。

### Step 3: 用户确认制作计划

等待用户确认制作计划。用户可能：
- **确认通过**：进入 Step 4
- **要求修改**：使用同一 session_id 将修改意见转达给导演，不传 context_files。修改完成后回到 Step 2 重新汇报。
- **要求重做**：重新调度导演，仍使用同一 session_id。

### Step 4: 调度美术

用户确认制作计划后，调度 art-designer 生成参考图：

```
subagent_name: "art-designer"
session_id: "art_{project_name}"
prompt: 项目路径和执行指令
context_files: ["{project_path}/meta.json", "{project_path}/entities.json", "{project_path}/states.json"]
```

**prompt 中必须包含且仅包含：**
- 项目路径（绝对路径）
- 执行完整的参考图生成（实体基准图 + 状态变化图）

**禁止在 prompt 中：**
- 指定视觉风格细节、构图方式
- 指定生成参数或 prompt 模板

art-designer 有自己的工作流和 prompt 规范，会从 states.json 的视觉描述自主生成。

### Step 5: 汇报参考图结果

美术完成后，向用户简要汇报：
- 实体参考图：成功 / 失败数
- 状态参考图：成功 / 跳过 / 失败数

如果有失败，向用户说明情况，可选择：
- 重试失败的图（同一 session_id，不传 context_files）
- 继续执行（缺失参考图的 shot 会降级为 text_to_video，视觉一致性下降）

### Step 6: 进入执行阶段

参考图完成（或用户选择继续）后，立即用 ReadFile 加载 `${AGENT_DIR}/workflow-execution.md`，按其中的步骤调度摄影、作曲和剪辑。

不要等用户额外指令——直接推进。

## 输出

项目目录下的制作计划和参考图：
- `events.json` — 事件列表 + 时序关系
- `states.json` — 状态节点 + active_during + 参考图路径
- `shots.json` — 镜头列表（画面 + 音频 + 时长）
- `validation-report.json` — 校验报告
- `assets/images/` — 参考图文件

## 错误处理

- **导演返回校验 FAIL**：向用户展示错误列表，由用户决定是否继续或要求修复。
- **美术返回部分失败**：向用户说明情况，可选择重试或继续。
