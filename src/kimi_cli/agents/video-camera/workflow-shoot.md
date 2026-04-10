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
1. `${AGENT_DIR}/guide-tool-capabilities.md` — 工具能力说明（各 provider 的音频/视频能力、TTS 适用范围）
2. `${AGENT_DIR}/guide-shot-strategy.md` — 生成模式决策树
3. `${AGENT_DIR}/guide-prompt-video.md` — prompt 组合规则

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

4. `{project_path}/entities.json` — 建立 **character_id → voice_description** 映射，用于 prompt 中角色对白的音色描述

5. `{project_path}/events.json` — 提取每个事件的 `state_changes`（了解哪些事件包含状态转换）

6. 检查断点：如果 `{project_path}/generation-status.json` 已存在，读取每个 shot 的记录：
   - `status: "done"` 或 `"degraded"` → 跳过（规划和执行都跳过，degraded 由调用方决定是否重试）
   - `status: "planned"` → 跳过规划，直接进入执行
   - `status: "in_progress"` → 跳过规划，从未完成的步骤继续执行（检查 `steps` 中哪些已完成）
   - `status: "failed"` 或无记录 → 需要重新规划

### Step 3: 规划（逐 Shot）

按 `shot_order` 顺序遍历需要规划的 shot（无记录或 `status: "failed"`），为每个 shot 制定生成计划。**本步骤只做决策，不执行任何生成工具。**

#### 3.1 分析需求：这个 shot 需要生成什么？

**视觉需求：**

读取当前 shot 的 `content`、`framing`、`angle`、`movement`、`transition_in`、`focus_on`、`event_id`、`scene_continuous`。
读取前一 shot（shot_order 中的前一个，如有）的 `content`、`framing`、`angle`、`event_id`、`focus_on`。

构建完整场景状态表：从 Step 2 建立的 event→实体状态映射中，查出当前 event 的全部 active 状态（所有 character_appearance、prop_state、location_state），不限于 focus_on。

如果跨 event（两个 shot 的 event_id 不同）：
- 用 event→实体状态映射，对比前后 event 中共同实体的状态
- 记录 `unchanged_entities`（状态相同）和 `changed_entities`（状态变了）

**音频需求：**

从 shot 的 `content` 中提取声音信息（对白、音效已按时间顺序写在 content 中），以及 `narration` 字段（画外旁白）。再从场景推断环境音。

#### 3.2 选择工具：视频 API 能覆盖什么？

**视频模式**：统一使用 `reference_to_video`。按 guide-shot-strategy.md 判断尾帧用法、是否需要构图参考图、参考图选择。

**选择 provider：**

参照 guide-tool-capabilities.md，根据该 shot 的视频模式和音频需求，选择最合适的 provider。例如：
- 需要 reference_to_video → 排除 Kling（不支持）
- 需要音频（有对白/音效）→ 优先选 Vidu
- 纯环境镜头无音频需求 → 任意 provider 均可

**音频策略决策：**

参照 guide-tool-capabilities.md 的"音频策略选择规则"，根据已选定的 provider 的音频能力，确定该 shot 的 `audio_strategy` 和 `need_tts`。

#### 3.3 写入生成计划

将每个 shot 的计划写入 `{project_path}/generation-status.json`，`status: "planned"`：

```json
{
  "shots": {
    "evt_farewell_shot_1": {
      "status": "planned",
      "plan": {
        "provider": "vidu",
        "video_mode": "reference_to_video",
        "reference_images": ["assets/images/appear_red_neat.png", "assets/images/lstate_forest_bright.png"],
        "need_tail_frame": false,
        "need_composition_image": false,
        "audio_strategy": "video_api",
        "need_tts": false
      },
      "reasoning": "ref2v + 音频 → Vidu。transition_in=cut 不用尾帧。单角色无复杂空间关系，不需要构图图"
    },
    "evt_finish_reversal_shot_3": {
      "status": "planned",
      "plan": {
        "provider": "vidu",
        "video_mode": "reference_to_video",
        "reference_images": ["__TAIL_FRAME__", "assets/images/appear_hare_flustered.png", "assets/images/lstate_trail_finish_bright.png", "assets/images/pstate_ribbon_snap.png"],
        "need_tail_frame": true,
        "need_composition_image": true,
        "audio_strategy": "video_api",
        "need_tts": false
      },
      "reasoning": "scene_continuous + 构图从 close_up 变 medium_close + 多角色空间关系 → 需要构图参考图锁定位置"
    }
  }
}
```

所有 shot 规划完成后再进入执行阶段。

### Step 4: 执行

按 `shot_order` 顺序执行每个 `status: "planned"` 或 `status: "in_progress"` 的 shot。每完成一步立即更新 generation-status.json。

**并行规则：**
- `scene_continuous = true` 的连续 shot 必须串行（后者需要前者尾帧）
- `transition_in = dissolve` 的 shot 必须等前一 shot 完成
- 其他情况下 shot 可并行（建议每批 3-5 个）

对每个 shot，按 plan 依次执行：

#### 4.1 尾帧提取（plan.need_tail_frame = true 时）

```
ExtractFrame(
  video_path="{project_path}/assets/shots/{prev_shot_id}.mp4",
  output_path="{project_path}/assets/frames/{shot_id}_tail.png",
  position="last"
)
```

#### 4.2 构图参考图生成（plan.need_composition_image = true 时）

用于 scene_continuous 且构图变化的 shot，或有复杂空间位置关系需要精确控制的 shot。

```
GenerateImage(
  prompt=<构图 prompt：描述各元素的精确位置关系，按 guide-prompt-video.md 的首帧规范组装>,
  reference_image_paths=<尾帧（如有）+ 角色/场景/道具参考图>,
  aspect_ratio=<从 meta.json>,
  negative_prompt=<从 meta.json>,
  output_path="{project_path}/assets/frames/{shot_id}_comp.png"
)
```

构图 prompt 使用 `@[image N]` 标记引用所有输入参考图。重点描述各角色、道具在画面中的位置和相对关系。

完成后将生成的构图图路径**替换** plan.reference_images 中的尾帧位置（构图图已包含尾帧信息），更新 generation-status.json。

#### 4.3 组装 Prompt + 视频生成

确定 reference_images 数组（顺序：构图参考图或尾帧（如有）→ 角色参考图（按 focus_on 顺序）→ 场景参考图 → 道具参考图）。

按 `guide-prompt-video.md` 的分段标注格式组装视频 prompt：
- **Style**: style_prefix
- **Camera**: framing + angle + movement
- **Scene**: LocationState 的 lighting / atmosphere，用 `<<<location_state_id>>>` 标记
- **Action**: content + interactions/mood/state_changes + 对白（附带 voice_description）+ 旁白。每个实体用 `<<<state_id>>>` 标记（如 `<<<appear_hare_default>>>`）
- **Sound**: 环境音 + content 中的音效
- **Note**: "No background music. Smooth natural motion. Physically plausible movements." + 其他约束
- 构图参考图用 `<<<composition>>>`，尾帧用 `<<<tail_frame>>>`
- reference_images 有几张图，prompt 中就必须有几个不同的 `<<<...>>>` 标记

**跨镜头 prompt 写法**（使用了尾帧时）：
- 描述从前一状态到当前状态的转换
- `"The video starts from <<<tail_frame>>>"` 标记尾帧

**Prompt 必须用英文。** 组装完执行 guide-prompt-video.md 的 3 点自检。

```
GenerateVideoSync(
  provider=<plan.provider>,
  prompt=<组装好的 prompt>,
  mode="reference_to_video",
  reference_images=<plan.reference_images>（包含构图参考图（如有）、尾帧（如有）、角色/场景/道具参考图）,
  duration_seconds=<shot.duration_seconds>,
  aspect_ratio=<从 meta.json>,
  negative_prompt=<从 meta.json>,
  download_path="{project_path}/assets/shots/{shot_id}.mp4"
)
```

完成后更新 generation-status.json：写入 `steps.video`，记录 `has_audio`、`output_path`。

#### 4.4 旁白 TTS（plan.need_tts = true 时）

```
GenerateSpeech(
  text=<dialogue.text>,
  output_path="{project_path}/assets/audio/tts_{shot_id}_{index}.mp3",
  voice_id="male-qn-qingse",
  language=<meta.json video_info.language>
)
```

**语音分配**：旁白默认 → "male-qn-qingse"。如需区分可从 meta.json 的 narrator 设定推断。

**跳过条件**（即使 plan 中标了 need_tts = true）：
- GenerateSpeech 工具不可用（TTS provider 未配置）→ 跳过，记录 `steps.tts.paths: []`

**TTS 失败处理**：记录 `steps.tts: {"status": "failed", "paths": []}`，继续下一个 shot。不重试。

完成后更新 generation-status.json：写入 `steps.tts`。

#### 4.5 标记完成

完成后对比实际执行和计划，确定状态：

- 实际 provider、mode、audio_strategy 与 plan 一致 → `status: "done"`
- 实际执行偏离了 plan（换了 provider、升级了 mode、音频策略变了）→ `status: "degraded"`，记录 `degradation`（偏离了什么、为什么、对质量的影响）
- 视频生成失败 → `status: "failed"`，记录 error

```json
{
  "shots": {
    "evt_farewell_shot_1": {
      "status": "done",
      "plan": { "provider": "vidu", "video_mode": "reference_to_video", "audio_strategy": "video_api", "need_tts": false },
      "steps": {
        "video": {"status": "done", "output_path": "assets/shots/evt_farewell_shot_1.mp4", "has_audio": true}
      },
      "prompt": "实际使用的完整 prompt",
      "reasoning": "..."
    },
    "evt_narration_shot_1": {
      "status": "done",
      "plan": { "provider": "vidu", "video_mode": "reference_to_video", "audio_strategy": "video_api", "need_tts": false },
      "steps": {
        "video": {"status": "done", "output_path": "assets/shots/evt_narration_shot_1.mp4", "has_audio": true}
      },
      "prompt": "...",
      "reasoning": "..."
    },
    "evt_farewell_shot_2": {
      "status": "failed",
      "error": "API error: rate limited",
      "retry_count": 2
    }
  },
  "summary": {
    "total": 12,
    "done": 7,
    "degraded": 1,
    "failed": 1,
    "pending": 3
  }
}
```

逐个 shot 更新，不要等全部完成再批量写入。

### Step 5: 错误处理

1. **网络错误 / 超时** → 用相同参数重试 1 次
2. **参数格式错误** → 修正参数后重试
3. **构图参考图生成失败** → 跳过构图图，用尾帧 + 角色参考图直接 ref2v（降级为无空间精确控制）
4. **provider 报能力不支持**（如 model not supported）→ 标记 failed，不降级、不换 provider
5. **累计 2 次失败** → 标记 failed，继续下一个 shot
6. **多个 shot 因同一 provider 报错** → 汇报时汇总说明

### Step 6: 汇报

所有 shot 处理完成后，报告结果：
- done / degraded / failed / 总数
- **degraded 的 shot**：逐个列出 shot ID、偏离内容、原因、对质量的影响
- **failed 的 shot**：逐个列出 shot ID、错误信息
- 总生成时长

等待调用方指示。调用方根据 degraded 信息决定是否接受或重试。

## 输出

在项目路径下生成：
- `assets/shots/{shot_id}.mp4` — 视频片段
- `assets/frames/{shot_id}_tail.png` — 尾帧（接续用）
- `assets/frames/{shot_id}_comp.png` — 构图参考图（如有）
- `generation-status.json` — per-shot 生成状态

## 错误处理

- **shots.json 缺少 shot_order**：按 events.json 的 event_sequence + shot 的 event_id/order 推断顺序，报告 warning。
- **states.json 中 reference_image 路径不存在**：该状态无参考图，仅用其他可用参考图继续 reference_to_video。
- **所有 shot 均失败**：停止并上报调用方，不尝试本地生成。
