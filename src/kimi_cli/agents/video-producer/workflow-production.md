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

### Step 2: 调度观众审查

导演完成后，调度 `video-audience` 从观看者视角审查制作计划：

```
subagent_name: "video-audience"
session_id: "audience_{project_name}"
prompt: 项目路径和执行指令
context_files: ["{project_path}/entities.json", "{project_path}/events.json", "{project_path}/states.json", "{project_path}/shots.json"]
```

**prompt 中必须包含且仅包含：**
- 项目路径（绝对路径）
- 执行审查

观众 agent 产出 `{project_path}/audience-review.json`。

**处理审查结果：**
- **PASS**：继续 Step 3
- **HAS_ISSUES 仅 warning**：继续 Step 3
- **HAS_ISSUES 且有 error**：执行以下修复流程，然后继续 Step 3

**修复流程（最多 1 轮）：**

1. 读取 `{project_path}/audience-review.json`，提取所有 severity=error 的 issue
2. 用同一 session_id 调度导演修复：

```
subagent_name: "video-director"
session_id: "director_{project_name}"
prompt: 见下方
context_files: ["{project_path}/audience-review.json"]
```

**prompt 格式：**

```
观众审查发现以下问题，请逐个修复：

{逐条列出 error，每条包含：}
- 问题类型：{type}
- 位置：{event_id} / {shot_id}
- 问题：{description}
- 细节：{detail}

修复方式：
- missing_visual_coverage → 补 shot 或在现有 shot 的 content 中补充变化过程
- incomplete_event → 补 shot 覆盖缺失的动作
- broken_causality → 补过渡 shot 或调整前后 shot 的 content 建立因果
- state_jump → 补 state_changes 或调整 active_during
- ambiguous_content → 重写 content，按空间顺序描述清楚角色位置关系

修复后重新执行校验（workflow-validate.md）。
```

3. 导演修复并重新校验后，再调度一次观众审查（新 session_id：`audience_{project_name}_r2`）
4. 第二轮无论结果如何，继续 Step 3

### Step 3: 调度美术

调度 art-designer 生成参考图。如果导演校验返回 FAIL，仍然继续（导演已尽力修复，剩余 warning 不阻塞流程）。

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

### Step 4: 进入执行阶段

美术完成后，立即用 ReadFile 加载 `${AGENT_DIR}/workflow-execution.md`，按其中的步骤调度摄影、作曲和剪辑。不等待用户确认参考图。

## 错误处理

- **导演返回校验 FAIL**：不阻塞，继续流程。导演已做过自动修复。
- **美术返回部分失败**：不阻塞，继续执行。缺失参考图的 shot 会自动降级为 text_to_video。
