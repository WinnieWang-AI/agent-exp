# 逐 Shot 生成

## 输入

项目目录下已有导演产出：
- `meta.json` — style_prefix、negative_prefix、aspect_ratio、language
- `states.json` — 状态视觉描述 + active_during 映射 + reference_image 路径
- `shots.json` — shot 列表 + shot_order（全局播放顺序）+ total_duration_seconds
- `events.json` — 事件列表（event_id、characters、location、state_changes）
- `assets/images/` — 参考图文件

## 步骤

### Step 1: 加载参考文件

用 ReadFile 加载：
1. `${AGENT_DIR}/guide-shot-strategy.md` — 生成模式决策树
2. `${AGENT_DIR}/guide-prompt-video.md` — prompt 组合规则

### Step 2: 读取项目数据

读取以下文件并建立索引：

1. `{project_path}/meta.json` — 提取：
   - `style.style_prefix` — 风格前缀
   - `style.negative_prefix` — 负面提示
   - `video_info.aspect_ratio` — 画面比例
   - `video_info.language` — 对白语言

2. `{project_path}/states.json` — 建立三个映射：
   - **state_id → 视觉描述**：从 character_appearances / location_states / prop_states 中提取 visual / lighting / atmosphere 等字段
   - **state_id → reference_image 路径**：从 character_appearances / location_states / prop_states 中提取 reference_image 字段（可能为空）
   - **event → 实体状态映射**：从 active_during 反向建立 `{event_id: {entity_id: state_id}}` 索引，用于跨 event 状态对比

3. `{project_path}/shots.json` — 提取：
   - `shots` 数组（全部 shot 数据）
   - `shot_order` 数组（全局播放顺序）

4. `{project_path}/events.json` — 提取每个事件的 `state_changes`（了解哪些事件包含状态转换）

5. 检查断点：如果 `{project_path}/generation-status.json` 已存在，读取每个 shot 的记录，用于断点恢复（见 Step 3 开头）。

### Step 3: 逐 Shot 决策与执行

按 `shot_order` 顺序遍历每个 shot。根据 generation-status.json 中的记录决定处理方式：

- `status: "done"` → **跳过**
- `status: "in_progress"` → 检查 `steps` 中已完成的步骤，**从未完成的步骤继续**（如 video 已完成则跳到 TTS）
- `status: "failed"` 或无记录 → **全部重做**

对每个需要处理的 shot，依次完成以下步骤：

#### 3.1 理解上下文

读取当前 shot 的 `content`、`shot_type`、`angle`、`movement`、`transition_in`、`focus_on`、`event_id`。

读取前一 shot（shot_order 中的前一个，如有）的 `content`、`shot_type`、`angle`、`event_id`。

如果跨 event（两个 shot 的 event_id 不同）：
- 用 Step 2 建立的 event→实体状态映射，对比前后 event 中共同实体的状态
- 记录 `unchanged_entities`（状态相同）和 `changed_entities`（状态变了）
- 状态变了的实体用新状态参考图，状态没变的用同一参考图（见 guide-shot-strategy.md 跨 event 状态对比）

#### 3.2 判断尾帧用法与生成模式

按 guide-shot-strategy.md 的条件定义，依次判断：

**A. 是否为时长拆分？**
- 条件：当前 shot 与前一 shot 同 event_id，且 shot_type 和 angle 都相同
- 是 → 提取前一 shot 尾帧，模式 = `image_to_video`，`reference_image_path` = 尾帧路径 → 跳到 3.4（选择参考图并组装 prompt）

**B. 导演是否要展示转换？**（参照 guide-shot-strategy.md "判断导演是否要展示转换"）
- content 描述从前一状态到当前状态的转换过程，或 transition_in = dissolve
  → 提取前一 shot 尾帧，放入 reference_images（辅助参考，占一个名额）
- transition_in = cut，且 content 描述独立场景
  → 不用尾帧

**C. 选择生成模式**（参照 guide-shot-strategy.md "生成模式判断条件"）
- 所有角色开头可见 + 动作小 → `image_to_video`（先生成首帧）
- 有角色中途出场 / 背对镜头 / 大幅运动 → `reference_to_video`
- 无参考图 → `text_to_video`

#### 3.3 尾帧提取（如需）

当 3.2 判断需要前一 shot 的尾帧时（时长拆分或展示转换）：

```
ExtractFrame(
  video_path="{project_path}/assets/shots/{prev_shot_id}.mp4",
  output_path="{project_path}/assets/frames/{shot_id}_tail.png",
  position="last"
)
```

#### 3.4 选择参考图 + 首帧生成（如需）

**选择参考图**（参照 guide-shot-strategy.md "参考图选择规则"）：
- 从 active_during 查当前 event 中 focus_on 各实体的状态 → 取 reference_image 路径
- 如果跨 event 有 changed_entities → 用新状态的参考图
- 3.2B 中的尾帧参考也占一个名额
- 超出 provider 上限时按优先级截断：角色 > 场景 > 道具 > 尾帧参考

**首帧生成**（仅当 3.2C 选择了 image_to_video 且非时长拆分时）：

```
GenerateImage(
  prompt=<首帧 prompt，按 guide-prompt-video.md 的首帧规范组装>,
  reference_image_paths=<角色参考图列表>,
  aspect_ratio=<从 meta.json>,
  negative_prompt=<从 meta.json>,
  output_path="{project_path}/assets/frames/{shot_id}_first.png"
)
```

首帧 prompt 使用 `@[role N]` 标记（不是 `<<<image_N>>>`）。

#### 3.5 组装 Prompt 并生成

按 `guide-prompt-video.md` 的规范组装视频 prompt，覆盖：
- style_prefix（开头）
- 镜头语言（shot_type + angle + movement）
- 画面内容（content）
- 场景环境（从 focus_on 的 LocationState 查 states.json 的 lighting/atmosphere）
- 角色外形（从 focus_on 的 CharacterAppearance 查 states.json 的 visual，从简）
- 角色行为（从 events.json 当前事件的 interactions、mood、state_changes 推断角色的情绪和表演）
- 对白（从 shot 的 dialogues 字段，写入 Sound: 段）
- 音效（从 shot 的 sfx 字段，写入 Sound: 段）
- `<<<image_N>>>` 标记（每张 reference_image 对应一个）

**跨镜头 prompt 写法**（当使用了尾帧作为辅助参考时）：
- 描述角色/场景从前一状态如何过渡到当前状态
- 用 `"The video starts from <<<image_N>>>"` 标记尾帧为起始画面
- 如果有状态变化（active_during 对比发现 changed_entities），prompt 中描述变化过程

**Prompt 必须用英文。** 将中文描述翻译为英文自然语言。

**Prompt 组装完成后，执行 guide-prompt-video.md "Prompt 生成后自检" 的 3 点检查。**

```
GenerateVideoSync(
  prompt=<组装好的 prompt>,
  mode=<决策确定的模式>,
  reference_images=<参考图路径列表>,
  reference_image_path=<首帧/尾帧路径，仅 image_to_video 模式>,
  duration_seconds=<shot.duration_seconds>,
  aspect_ratio=<从 meta.json>,
  negative_prompt=<从 meta.json>,
  download_path="{project_path}/assets/shots/{shot_id}.mp4"
)
```

#### 3.6 对白 TTS 回退

GenerateVideoSync 的返回结果中包含 `has_audio: true` 或 `has_audio: false`。如果 `has_audio: false`，**且**当前 shot 有 `dialogues`（非空），为每条对白生成 TTS 语音：

```
GenerateSpeech(
  text=<dialogue.text>,
  output_path="{project_path}/assets/audio/tts_{shot_id}_{index}.mp3",
  voice_id=<按 speaker 分配的语音，见下方>,
  language=<meta.json video_info.language>
)
```

**语音分配**：维护一个 character_id → voice_id 的映射。角色首次说话时分配语音，后续复用。默认分配规则：从实体名称/描述推断性别，男性 → "male-qn-qingse"，女性 → "female-shaonv"，旁白(narrator) → "male-qn-qingse"。

**跳过条件**：
- GenerateVideoSync 返回 `has_audio: true`（视频已有音频）→ 跳过
- shot 没有 dialogues → 跳过
- GenerateSpeech 工具不可用（TTS provider 未配置）→ 跳过，记录 `steps.tts.paths: []`

**TTS 失败处理**：记录 `steps.tts: {"status": "failed", "paths": []}`，继续下一个 shot。不重试。

#### 3.7 记录状态

**分步写入**，每完成一个关键步骤就立即更新 `{project_path}/generation-status.json`：

1. **视频生成后**：立即写入记录，`status: "in_progress"`，`steps.video` 记录结果
2. **TTS 完成后**（或确认不需要 TTS）：更新 `steps.tts`，将 `status` 改为 `"done"`
3. 如果视频生成就失败了：直接写 `status: "failed"`

`has_audio` 的值直接取 GenerateVideoSync 返回的 `has_audio` 字段。

不需要 TTS 的 shot（`has_audio: true` 或没有 dialogues），视频生成后直接标 `"done"`。

```json
{
  "shots": {
    "evt_farewell_shot_1": {
      "status": "done",
      "steps": {
        "video": {"status": "done", "output_path": "assets/shots/evt_farewell_shot_1.mp4", "has_audio": true}
      },
      "mode": "reference_to_video",
      "reference_images": ["assets/images/appear_red_neat.png"],
      "prompt": "实际使用的完整 prompt",
      "reasoning": "content 描述独立场景，transition_in=cut，不用尾帧。角色开头可见但有走动，选择 reference_to_video"
    },
    "evt_wolf_encounter_shot_1": {
      "status": "done",
      "steps": {
        "video": {"status": "done", "output_path": "assets/shots/evt_wolf_encounter_shot_1.mp4", "has_audio": false},
        "tts": {"status": "done", "paths": ["assets/audio/tts_evt_wolf_encounter_shot_1_0.mp3"]}
      },
      "mode": "reference_to_video",
      "reference_images": ["assets/images/appear_wolf_natural.png"],
      "prompt": "...",
      "reasoning": "Vidu ref2v → no audio. TTS generated for 1 dialogue line."
    },
    "evt_farewell_shot_2": {
      "status": "failed",
      "error": "API error: rate limited",
      "retry_count": 2
    }
  },
  "summary": {
    "total": 12,
    "done": 8,
    "failed": 1,
    "pending": 3
  }
}
```

逐个记录，不要等全部完成再批量写入。

### Step 4: 并行执行

- **同 event 内 shot_type+angle 相同的连续 shot 必须串行**：后一个 shot 需要前一个的尾帧
- **Step 3.2 决定使用尾帧参考时必须等前一 shot 完成**
- **其他情况下不同 event 的 shot 可以并行**：在同一个 response 中调用多个 GenerateVideoSync
- 建议每批并行 3-5 个 shot
- 并行时，每个 shot 的决策（3.1-3.5）在调用前完成，不依赖其他并行 shot 的结果

### Step 5: 错误处理

按以下顺序恢复：
1. **网络错误 / 超时** → 用相同参数重试 1 次
2. **参数错误** → 调整参数后重试（如不支持的 mode → 换 mode）
3. **provider 限流 / 连续失败 2 次** → 从错误返回的 `available_providers` 中选另一个 provider 重试
4. **累计 3 次失败** → 标记该 shot 为 failed，继续下一个 shot
5. `image_to_video` 失败可退回 `reference_to_video`

### Step 6: 汇报

所有 shot 处理完成后，报告结果：
- 成功数 / 失败数 / 总数
- 失败的 shot ID 和错误信息
- 总生成时长

等待调用方指示。

## 输出

在项目路径下生成：
- `assets/shots/{shot_id}.mp4` — 视频片段
- `assets/frames/{shot_id}_tail.png` — 尾帧（接续用）
- `assets/frames/{shot_id}_first.png` — 首帧图（如有）
- `generation-status.json` — per-shot 生成状态

## 错误处理

- **shots.json 缺少 shot_order**：按 events.json 的 event_sequence + shot 的 event_id/order 推断顺序，报告 warning。
- **states.json 中 reference_image 路径不存在**：该状态无参考图，降级为 text_to_video 或仅用其他可用参考图。
- **所有 shot 均失败**：停止并上报调用方，不尝试本地生成。
