# Shot Guide

本文件指导你如何为每个 shot 做决策、选参考图、写 prompt。**开始视频生成前必读。**

所有 prompt **必须用英文**。将 `prompt_materials` 中的结构化数据编织成**流畅的自然语言描述**，不要机械罗列字段。

---

## 核心原则

1. **每个 shot 是一次独立的 GenerateVideoSync 调用。**
2. **模型能从输入图片里"看到"谁，就能保持谁的一致性。** 首帧/参考图里出现的角色能保持一致，没出现的无法保证。

---

## 决策总览

| 场景 | 生成方式 | 关键参数 |
|---|---|---|
| 同一镜头拆分延续 | `image_to_video` | `reference_image_path` = 前一 part 尾帧 |
| 叙事连续 + 机位不变 | `image_to_video` | `reference_image_path` = 前一 shot 尾帧 |
| 叙事连续 + 机位改变 | 走 Step 3 判断 | 前一 shot 尾帧加入 `reference_images` |
| 所有角色开头可见 + 动作小 | `image_to_video` | `reference_image_path` = 生成的首帧图 |
| 有角色中途出场 / 大幅运动 | `reference_to_video` | `reference_images` = 角色参考图 |
| 无参考图 | `text_to_video` | 仅 prompt |

---

## Step 1: 这一幕有谁、在哪

从 `focus_on` 和 `prompt_materials` 确定：

- **出镜角色**：`focus_on` 中的 appearance state → 对应角色在画面中
- **场景环境**：`focus_on` 中的 location state → 对应环境在画面中
- **角色行为**：`prompt_materials.minds[].behavior` → 角色在做什么
- **道具**：`prompt_materials.prop_states` → 画面中有什么重要道具

---

## Step 2: 和前一幕怎么衔接

检查当前 shot 与前一幕的关系。2a/2b **优先且互斥**（命中后直接跳 Step 4）；2c 是**可选补充**（继续走 Step 3）：

### 2a. 同一镜头拆分（`is_continuation: true`）

当前 shot 是同一镜头因时长超限被拆分的后续部分。从 `prev_shot.output_path` 提取尾帧，用 `image_to_video`。→ **跳到 Step 4**。

### 2b. 叙事连续接续（`prev_shot_in_sequence` 存在）

Screenwriter 标注了这两个事件在叙事时间和空间上连续（`continuous: true`）。从 `prev_shot_in_sequence.output_path` 提取尾帧。然后**根据机位变化选择策略**：

- **机位不变**（shot_type 和 angle 都相同）：用尾帧做 `image_to_video` 的 `reference_image_path`。→ **跳到 Step 4**。
- **机位改变**（shot_type 或 angle 不同）：把尾帧加入 `reference_images`（参考用，不做主图），→ **继续走 Step 3** 判断生成方式。这保证叙事连贯的同时，不会让旧构图锁死新镜头的视角。

### 2c. 跨场景衔接（无 `prev_shot_in_sequence`，但有空间连续性）

未命中 2a/2b 时，查看 shot-plan 中紧邻的前一个 shot。如果场景有空间连续性（如森林出口 → 小屋门口、角色跨场景移动），则将前一 shot 的尾帧加入 `reference_images`（不是 `reference_image_path`，不改变生成模式）。尾帧占一个名额（上限 4 张），优先保角色参考图。

**不用的情况**：无共同角色的跳切、闪回、完全无关的场景切换。

→ **继续走 Step 3**。

### 都不命中

独立 shot，直接进 Step 3。

---

## Step 3: 怎么拍（生成方式）

**核心问题：首帧能否包含所有出镜角色的视觉身份信息？**

**适合首帧（→ `image_to_video`）**：
- 所有角色在视频开头就在画面中，正面/侧面可辨认
- 无大幅运动（非 tracking、非奔跑/跳跃/转身）

**不适合首帧（→ `reference_to_video`）**：
- 有角色中途出场（如"从树后走出"，开头不在画面中）
- 角色背对镜头或被遮挡
- 大幅运动（tracking + 奔跑/蹦跳）

**无参考图（→ `text_to_video`）**：
- 纯环境镜头、无角色参考图可用

---

## Step 4: 选参考图 & 写 Prompt

决策和 prompt 是一体的。确定生成方式后，选择参考图并组装 prompt。

### 参考图选择

参考图路径不在 shot-plan 中，需要从 **story-graph.json** 按 state ID 查找：
- `focus_on` 中每个 appearance state ID → 在 story-graph 的 `character_appearances` 中找到对应节点的 `reference_image`
- 场景参考图 → `prompt_materials.location_state.id` → 在 `location_states` 中找 `reference_image`
- Step 2c 的尾帧参考 → 如果决定使用
- 上限 4 张，超出时优先保角色

### Prompt 结构

将以下要素编织成自然语言（不需要固定顺序，但都要覆盖）：

1. **风格**：`style_prefix` 放在 prompt 开头
2. **镜头语言**：景别（`shot_type`）、角度（`angle`）、运动（`movement`）、焦距（`lens`）、景深（`focus_depth`）
3. **画面内容与空间关系**：`content` — 画面内容和角色在画面中的位置
4. **场景环境**：`location_state.appearance` 的 lighting / weather / atmosphere。如果 `location_state.framing` 存在，只描述 `visible_regions` 中的区域环境，不要描述 `excluded_elements` 中的元素
5. **角色外形**：从简，抓关键特征（如"red-cloaked girl"），参考图已传入不需重复全部细节
6. **角色表演**：`minds[].emotion` + `minds[].behavior` — 视频的核心
8. **角色关系**：融入氛围（"陌生人初次相遇的试探感"），不要直接写关系名称
9. **道具**：按需提及，只在画面中有重要作用时
10. **负面提示**：`negative_prefix` 通过 `negative_prompt` 参数传入

### 参考图关联标记

让模型知道哪张图对应哪个角色，**必须标注**：

- **首帧图 prompt**（GenerateImage）：使用 `@[role N]`。prompt 开头加 `"Reference image characters from left to right are: @[role 1], @[role 2]."` ，角色描述旁加 `@[role N]`。编号按 `reference_image_paths` 顺序。
- **视频 prompt**（GenerateVideoSync）：使用 `<<<image_N>>>`，放在角色描述旁。编号按 `reference_images` 顺序。

**自查**：`reference_images` 有几张，prompt 中就必须有几个 `<<<image_N>>>` 标记。

### 参考图关系与时序发展

当使用了前一幕尾帧或多张参考图时，prompt 中必须说清楚：

- **尾帧作为起点**：如果用了前一幕尾帧（Step 2c），prompt 用 `"The video starts from <<<image_N>>>"` 告诉模型从这张画面开始，然后描述角色从上一个场景如何过渡到下一个场景
- **各参考图的角色**：哪张是角色参考、哪张是场景参考、哪张是前一幕的画面
- **时序发展**：角色从哪里来、到哪里去、场景如何过渡

不能只写"女孩站在小屋里"，要写"视频从上一幕的画面开始，女孩从森林走出，推开小屋的门" — 让模型理解连续的动作过渡。

### 首帧图 vs 视频 Prompt 的区别

| | 首帧图（GenerateImage） | 视频（GenerateVideoSync） |
|--|--|--|
| 内容 | 静态画面，动作发生前一刻的"定格" | 动态镜头，有动作过程和时间推进 |
| 背景 | 有完整场景环境 | 有完整场景环境 |
| 角色 | 有具体站位和朝向，无动作过程 | 有表演、互动、情绪变化 |
| 标记 | `@[role N]` | `<<<image_N>>>` |

---

## 输出：execution 字段

每个 shot 生成后，回写 `execution` 到 `shot-plan.json`：

```json
"execution": {
  "mode": "reference_to_video",
  "reference_images": ["{project_dir}/assets/images/appear_red_neat.png"],
  "reference_image_path": "",
  "first_frame_path": "",
  "first_frame_prompt": "",
  "tail_frame_path": "",
  "prompt": "实际传给 API 的完整 prompt",
  "negative_prompt": "photorealistic, dark",
  "reasoning": "承接 evt_forest_walk_shot_2（小红帽走出森林），时间连续且角色相同，场景从森林过渡到小屋门口，使用前一幕尾帧作为参考图保持角色和场景衔接。狼在视频中途才出场，首帧无法覆盖所有角色，选择 reference_to_video。"
}
```

`reasoning` 必须说明：
- 承接哪个 shot（如果有衔接关系）
- 为什么使用/不使用前一幕尾帧
- 为什么选择这种生成方式

---

## 并行规则

- 无依赖的 shot 可并行
- 2a（`is_continuation`）和 2b（`prev_shot_in_sequence`）必须等前一 shot 完成
- 2c 使用了尾帧参考时必须等前一 shot 完成；不用时可并行

---

## 示例

### 示例 1：双人对话，角色中途出场（reference_to_video）

```json
{
  "shot_type": "medium", "angle": "eye_level", "movement": "static",
  "content": "林间小路上，小红帽停步，大灰狼从右侧树后探出，两者相距约3米",
  "focus_on": ["appear_red_neat", "appear_wolf_natural"],
  "prompt_materials": {
    "style_prefix": "hand-drawn illustration, warm color palette, children's storybook style",
    "minds": [
      {"entity": "char_red", "emotion": "好奇，微微不安", "behavior": "停下脚步，侧头倾听"},
      {"entity": "char_wolf", "emotion": "伪装友善", "behavior": "缓缓走出，弓着身体"}
    ],
    "relationships": [{"pair": ["char_red", "char_wolf"], "current_kind": "陌生人"}]
  }
}
```

推理：狼"缓缓走出" → 开头不在画面中 → 不适合首帧 → `reference_to_video`。

视频 prompt：
"hand-drawn illustration, warm color palette, children's storybook style. Medium shot, eye level, static camera. On the left side of the frame, a little girl in a red velvet cloak <<<image_1>>> stops on the forest path, tilting her head with wide curious eyes and a hint of unease. From behind a large oak tree on the right, a tall gray-brown wolf <<<image_2>>> slowly emerges, crouching low to appear smaller. The wolf approaches with disarming gentleness — two strangers meeting for the first time, an air of cautious tension."

execution:
```json
{
  "mode": "reference_to_video",
  "reference_images": ["{project_dir}/assets/images/appear_red_neat.png", "{project_dir}/assets/images/appear_wolf_natural.png"],
  "reasoning": "狼在视频中途从树后走出，开头不在画面中，首帧无法覆盖狼的身份信息，选择 reference_to_video 让模型全程持有两个角色的参考。"
}
```

### 示例 2：跨场景衔接，使用前一幕尾帧（reference_to_video + 尾帧参考）

前一幕：evt_forest_walk_shot_2（小红帽走出森林边缘）
当前幕：evt_cabin_arrival_shot_1（小红帽来到小屋门口）

推理：时间连续，同一角色，场景从森林过渡到小屋 → 用前一幕尾帧作为参考图之一。小红帽开头可见但在走动 → `reference_to_video`。

视频 prompt：
"hand-drawn illustration, warm color palette, children's storybook style. Wide shot, eye level, slow tracking. The video starts from <<<image_3>>>, where the girl in a red cloak <<<image_1>>> is at the edge of the forest. She walks out of the tree line and approaches a small cottage <<<image_2>>> at the clearing — transitioning from the dark canopy to the bright open meadow. She approaches the wooden door, basket swinging gently, looking up at the cozy cottage with anticipation."

execution:
```json
{
  "mode": "reference_to_video",
  "reference_images": ["{project_dir}/assets/images/appear_red_neat.png", "{project_dir}/assets/images/loc_cabin_exterior.png", "{project_dir}/assets/frames/evt_forest_walk_shot_2_tail.png"],
  "reasoning": "承接 evt_forest_walk_shot_2（小红帽走出森林），时间连续，角色相同，场景从森林过渡到小屋门口。使用前一幕尾帧作为第 3 张参考图，帮助保持角色外观和场景衔接的连续性。角色在走动中，选择 reference_to_video。"
}
```

### 示例 3：特写情绪镜头，首帧可行（image_to_video）

```json
{
  "shot_type": "close_up", "angle": "low_angle", "movement": "push_in",
  "focus_on": ["appear_grandma_home"],
  "prompt_materials": {
    "minds": [{"entity": "char_grandma", "emotion": "震惊转为恐惧", "behavior": "瞪大双眼，身体往后缩"}],
    "location_state": {"appearance": {"lighting": "昏暗壁炉光", "atmosphere": "从温暖骤变为压迫"}}
  }
}
```

推理：单人特写，角色开头就在画面中，push_in 运动幅度小 → 生成首帧定义构图 → `image_to_video`。

首帧 prompt：
"Reference image characters from left to right are: @[role 1]. hand-drawn illustration, warm color palette, children's storybook style. Close-up from low angle. An elderly woman in a white nightgown and lace nightcap @[role 1], wisps of gray hair, frail pale face lit by dim fireplace flicker. She stares forward with wide eyes, a frozen moment just before terror sets in. Cozy cottage interior, warm but with a creeping sense of unease."

视频 prompt：
"hand-drawn illustration, warm color palette, children's storybook style. Close-up from low angle, camera slowly pushing in. An elderly woman in a white nightgown <<<image_1>>>, her eyes widen in shock, mouth falling open, body instinctively shrinking backward as terror washes over her face. The cozy cottage interior shifts from warmth to an oppressive, claustrophobic feeling, firelight flickering across her horrified expression."

execution:
```json
{
  "mode": "image_to_video",
  "reference_image_path": "{project_dir}/assets/frames/evt_grandma_door_shot_1_first.png",
  "reference_images": ["{project_dir}/assets/images/appear_grandma_home.png"],
  "first_frame_path": "{project_dir}/assets/frames/evt_grandma_door_shot_1_first.png",
  "reasoning": "单人特写，外婆开头就在画面中正面面对镜头，push_in 运动幅度小，适合生成首帧图定义构图和表情起点，选择 image_to_video。"
}
```

---

## 常见陷阱

1. **跨 shot 尾帧接续（2b）只在 `prev_shot_in_sequence` 存在时使用。** 没有该字段不做 2b 接续。
2. **已用首帧/尾帧时，额外参考图收益有限。** 画面身份已锚定。
3. **运动幅度大的镜头慎用首帧。** 首帧约束起始构图，大幅运动会不自然。
4. **每个 shot 独立决策。** 不要因为一次失败就放弃某种策略。
5. **prompt 中不要遗漏 `<<<image_N>>>` 标记。** 缺标记 = 角色一致性丢失。
6. **跨场景衔接时 prompt 必须交代时序。** 不写时序，模型不知道角色从哪里来。
