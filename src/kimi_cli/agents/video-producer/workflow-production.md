# 制作执行

## 步骤

### Step 1: 调度导演

用 Task 调度 `video-director`，使用 session_id 保持状态：

```
subagent_name: "video-director"
session_id: "director_{project_name}"
prompt: 项目路径和执行指令（见下方）
context_files: ["{project_path}/meta.json", "{project_path}/entities.json", "{project_path}/outline.json", "{project_path}/act-1.json", "{project_path}/act-2.json", ...]
```

> **act 文件必须全部传入。** 调度前先用 `Glob("{project_path}/act-*.json")` 获取实际文件列表，将所有 act 文件加入 context_files。act 文件包含 beat 级对白，是导演提取 dialogues 的唯一数据来源；outline.json 只有场景摘要，不含对白。

**prompt 中必须包含且仅包含：**
- 项目路径（绝对路径）
- 执行完整的导演工作流（事件拆解 → 实体状态规划 → 镜头设计 → 校验）

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

### Step 3: 用户确认制作计划

等待用户确认制作计划。用户可能：
- **确认通过**：进入 Step 4
- **要求修改**：使用同一 session_id 将修改意见转达给导演。修改完成后回到 Step 2 重新汇报。
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
- 重试失败的图（同一 session_id）
- 继续执行（缺失参考图的 shot 会降级为 text_to_video，视觉一致性下降）

### Step 6: 进入执行阶段

参考图完成（或用户选择继续）后，立即用 ReadFile 加载 `${AGENT_DIR}/workflow-execution.md`，按其中的步骤调度摄影、作曲和剪辑。

## 错误处理

- **导演返回校验 FAIL**：向用户展示错误列表，由用户决定是否继续或要求修复。
- **美术返回部分失败**：向用户说明情况，可选择重试或继续。
