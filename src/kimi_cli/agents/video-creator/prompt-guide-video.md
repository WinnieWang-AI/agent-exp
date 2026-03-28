# Prompt Guide: Video Generation (Phase 3)

本文件提供首帧图和视频 prompt 的写作规范和示例。Phase 3 开始前请阅读。

所有 prompt **必须用英文**写。你需要将 `prompt_materials` 中的结构化数据编织成**一段流畅的自然语言描述**，而不是机械地罗列字段。

---

## 首帧图 Prompt（Technique B）

目标：生成一张**静态画面**作为视频起点。有完整构图、场景、角色站位，但**没有动作过程**——描述的是动作发生前一刻的"定格"。

### 与参考图的区别

| | 参考图（Phase 2） | 首帧图（Technique B） |
|--|--|--|
| 背景 | 纯白/纯色 | 有完整场景环境 |
| 构图 | 居中展示 | 有镜头语言（景别、角度） |
| 角色 | 中立姿势 | 有具体站位和朝向 |
| 用途 | 作为 reference_images 维持一致性 | 作为 reference_image_path 定义视频第一帧 |

### 示例：特写镜头首帧

<example>
shot plan 数据：
```json
{
  "shot_type": "close_up",
  "angle": "eye_level",
  "movement": "push_in",
  "content": "小红帽停步，感觉有什么在看她",
  "focus_on": ["appear_red_neat", "appear_wolf_natural"],
  "prompt_materials": {
    "style_prefix": "hand-drawn illustration, warm color palette, children's storybook style",
    "event_description": "大灰狼从树后现身，假装友善地搭话",
    "appearances": [
      {"entity": "char_red", "visual": {"costume": "红色丝绒斗篷，白色连衣裙", "hair": "棕色卷发散落在斗篷里", "physical": "健康，红润"}},
      {"entity": "char_wolf", "visual": {"costume": "灰褐色毛皮，蓬松的尾巴", "hair": "尖耳竖立", "physical": "体型高大，尖齿"}}
    ],
    "minds": [
      {"entity": "char_red", "emotion": "好奇，微微不安", "behavior": "停下脚步，侧头倾听"},
      {"entity": "char_wolf", "emotion": "伪装友善，暗藏贪婪", "behavior": "缓缓走出，弓着身体显得矮小"}
    ],
    "location_state": {"appearance": {"lighting": "丁达尔光束", "weather": "晴，微风", "condition": "野花，蝴蝶", "atmosphere": "童话美好"}},
  }
}
```

首帧图 prompt（静态画面，描述动作发生前一刻的定格）：
"Reference image characters from left to right are: @[role 1], @[role 2]. hand-drawn illustration, warm color palette, children's storybook style. Close-up shot at eye level. A little girl @[role 1] in a red velvet cloak and white dress stands on a forest path, head slightly tilted, eyes wide with curiosity and a hint of unease, curly brown hair framing her round face. Behind a moss-covered oak tree, a large gray-brown wolf @[role 2] peers out, ears pointed forward, crouching low to appear smaller. Warm god rays filter through the canopy, wildflowers and butterflies dotting the sunlit path. The girl has just noticed something watching her — a frozen moment of first contact."

参数：
- reference_image_paths: ["{project_dir}/assets/images/appear_red_neat.png", "{project_dir}/assets/images/appear_wolf_natural.png"]
  （从 story-graph.json 中按 `focus_on` 涉及的 appearance state ID 查找 `reference_image`，顺序决定 @[role N] 编号）
- aspect_ratio: <从 video_info.aspect_ratio 获取>
- negative_prompt: "photorealistic, dark, horror, oversaturated"
</example>

### 示例：全景首帧

<example>
shot plan 数据：
```json
{
  "shot_type": "wide",
  "angle": "high_angle",
  "movement": "crane_down",
  "content": "小红帽独自走在林间小路上，渺小而天真",
  "focus_on": ["appear_red_neat"],
  "prompt_materials": {
    "style_prefix": "hand-drawn illustration, warm color palette, children's storybook style",
    "event_description": "小红帽蹦蹦跳跳穿过森林小路，采野花",
    "appearances": [
      {"entity": "char_red", "visual": {"costume": "红色丝绒斗篷，白色连衣裙", "hair": "棕色卷发散落在斗篷里", "physical": "健康，红润"}}
    ],
    "minds": [{"entity": "char_red", "emotion": "开心，天真", "behavior": "蹦蹦跳跳，东张西望"}],
    "location_state": {"appearance": {"lighting": "丁达尔光束", "weather": "晴，微风", "condition": "野花，蝴蝶", "atmosphere": "童话美好"}}
  }
}
```

首帧图 prompt：
"Reference image characters from left to right are: @[role 1]. hand-drawn illustration, warm color palette, children's storybook style. Wide shot from a high angle looking down. A tiny figure @[role 1] in a bright red cloak walks along a narrow winding dirt path through a vast dense forest, towering pine and oak trees stretching in all directions, golden god rays slanting through the canopy, patches of colorful wildflowers along the path edges, butterflies in the warm air. The girl appears small against the grand forest, conveying innocence and vulnerability."

参数：
- reference_image_paths: ["{project_dir}/assets/images/appear_red_neat.png"]
- aspect_ratio: <从 video_info.aspect_ratio 获取>
- negative_prompt: "photorealistic, dark, horror, oversaturated"
</example>

---

## 视频 Prompt

目标：描述一段**动态镜头**——角色在做什么、怎么互动、镜头怎么运动。视频 prompt 和首帧图的关键区别是**有动作过程和时间推进**。

### Prompt 结构

将 `prompt_materials` 编织成自然语言，覆盖以下要素（不需要按固定顺序，但都要包含）：

1. **风格**：`style_prefix` 放在开头
2. **镜头语言**：景别（`shot_type`）、角度（`angle`）、运动（`movement`）、镜头焦距（`lens`）、景深（`focus_depth`）
3. **画面内容与空间关系**：`content` — 描述画面内容和人物在画面中的位置关系。这是保证镜头间空间连续性的关键信息，必须体现在 prompt 中
5. **场景环境**：`location_state.appearance` 的 lighting / weather / atmosphere。如果 `location_state.framing` 存在，只描述 `framing.visible_regions` 中的区域环境，不要描述 `framing.excluded_elements` 中的元素
6. **角色外形**：`appearances[].visual` — 不需要详尽描述每个字段，抓关键视觉特征（如"red cloaked girl"而不是重复全部服装细节，因为 reference_images 已经传入了）
7. **角色表演**：`minds[].emotion` + `minds[].behavior` — 这是视频的核心，描述角色的动作和情绪表达
8. **角色关系**：`relationships[]` — 如果关系影响互动氛围（如"陌生人初次相遇"vs"信任的朋友"）
10. **道具**：`prop_states[].appearance` — 如果道具在画面中有重要作用
11. **参考图-角色关联标记**：首帧图和视频 prompt 使用不同的标记语法（因为底层 API 不同），但目的相同——让模型知道哪张参考图对应哪个角色：
   - **首帧图 prompt**（GenerateImage，Seedream/Gemini）：使用 `@[role N]` 标记。在 prompt 最前面加前缀 `"Reference image characters from left to right are: @[role 1], @[role 2]."` 说明参考图顺序，然后在角色首次出现的描述旁放 `@[role N]`。编号按 `reference_image_paths` 参数顺序。
   - **视频 prompt**（GenerateVideoSync，Kling 等）：使用 `<<<image_N>>>` 标记，放在对应角色首次出现的描述旁边。编号按 `reference_images` 参数顺序。
12. **负面提示**：`negative_prefix` 通过 `negative_prompt` 参数传入
13. **声音描述（Sound）**：视频模型会同时生成画面和声音（环境音、对话、音效）。在 prompt 末尾用 "Sound:" 段落描述该镜头应有的声音，帮助模型生成与画面同步的音频。声音描述包含两部分：
    - **环境音与音效**：从 `location_state.appearance`（atmosphere、weather）和角色动作（`minds[].behavior`）推断。如 `Sound: wind rustling through leaves, soft footsteps on dirt path, distant birdsong`
    - **角色对白**：当 shot 的 `audio_ids` 关联了 `audio_dialogue` 类型的 audio_state 时，从 `prompt_materials.audio_states` 中找到对应条目的 `text` 和 `speaker`，将台词写入 prompt。格式：`The girl says "奶奶我来看你了"`。对白语言与 `video_info.language` 一致。无对白的 shot 只写环境音

### 示例：中景 + 双人互动

<example>
shot plan 数据：
```json
{
  "shot_type": "medium",
  "angle": "eye_level",
  "movement": "static",
  "content": "林间小路上，小红帽突然停步，大灰狼从右侧大橡树后探出半身，两者相距约3米",
  "lens": "50mm",
  "focus_depth": "shallow, focus on girl",
  "focus_on": ["appear_red_neat", "appear_wolf_natural"],
  "prompt_materials": {
    "style_prefix": "hand-drawn illustration, warm color palette, children's storybook style",
    "event_description": "大灰狼从树后现身，假装友善地搭话，套出外婆住处",
    "appearances": [
      {"entity": "char_red", "visual": {"costume": "红色丝绒斗篷，白色连衣裙", "hair": "棕色卷发散落在斗篷里"}},
      {"entity": "char_wolf", "visual": {"costume": "灰褐色毛皮，蓬松的尾巴", "hair": "尖耳竖立", "physical": "体型高大，尖齿"}}
    ],
    "minds": [
      {"entity": "char_red", "emotion": "好奇，微微不安", "behavior": "停下脚步，侧头倾听"},
      {"entity": "char_wolf", "emotion": "伪装友善，暗藏贪婪", "behavior": "缓缓走出，弓着身体显得矮小"}
    ],
    "location_state": {"appearance": {"lighting": "丁达尔光束", "condition": "野花", "atmosphere": "童话美好"}},
    "relationships": [{"pair": ["char_red", "char_wolf"], "current_kind": "陌生人"}],
    "prop_states": [{"entity": "prop_basket", "appearance": {"visual": "藤篮盖着红白格子布", "condition": "完好"}}]
  },
}
```

视频 prompt：
"hand-drawn illustration, warm color palette, children's storybook style. Medium shot, eye level, static camera, 50mm lens, shallow depth of field with focus on the girl. On the left foreground of the frame, a little girl in a red velvet cloak <<<image_1>>> stops on the path, facing right, tilting her head with wide curious eyes and a flicker of unease. About three meters away on the right side, from behind a large oak tree, a tall gray-brown wolf <<<image_2>>> slowly emerges, crouching low and hunching his body to appear smaller and less threatening. Sunlit forest clearing with god rays and scattered wildflowers. The wolf approaches with a gentle, disarming manner while the girl clutches her basket — covered with a red-and-white checkered cloth — a little tighter. Two strangers meeting for the first time, an air of deceptive gentleness."

参数：
- negative_prompt: "photorealistic, dark, horror, oversaturated"
- mode: "image_to_video"（因为有 Technique B/C 提供的首帧/尾帧）
- reference_image_path: "{project_dir}/assets/frames/cam_wolf_encounter_shot_0_first.png"（来自 Technique B/C）
- reference_images: ["{project_dir}/assets/images/appear_red_neat.png", "{project_dir}/assets/images/appear_wolf_natural.png"]
- aspect_ratio: <从 video_info.aspect_ratio 获取>
- duration_seconds: 5
</example>

### 示例：全景 + 单人 + 镜头运动

<example>
shot plan 数据：
```json
{
  "shot_type": "wide",
  "angle": "high_angle",
  "movement": "crane_down",
  "content": "小红帽独自走在林间小路上，渺小而天真",
  "focus_on": ["appear_red_neat"],
  "prompt_materials": {
    "style_prefix": "hand-drawn illustration, warm color palette, children's storybook style",
    "event_description": "小红帽蹦蹦跳跳穿过森林小路，采野花",
    "minds": [{"entity": "char_red", "emotion": "开心，天真", "behavior": "蹦蹦跳跳，东张西望"}],
    "location_state": {"appearance": {"lighting": "丁达尔光束", "weather": "晴，微风", "condition": "野花，蝴蝶", "atmosphere": "童话美好"}}
  },
}
```

视频 prompt：
"hand-drawn illustration, warm color palette, children's storybook style. Wide shot from high angle, camera slowly craning down. A vast dense forest with towering pines, golden god rays streaming through the canopy, gentle breeze stirring the leaves. A tiny red-cloaked figure <<<image_1>>> skips merrily along a winding dirt path, hopping and looking around with childlike wonder, pausing to pick a wildflower, butterflies dancing in the warm sunlit air. The girl appears small and innocent against the grand ancient woodland."

参数：
- negative_prompt: "photorealistic, dark, horror, oversaturated"
- mode: "reference_to_video"
- reference_images: ["{project_dir}/assets/images/appear_red_neat.png"]
- aspect_ratio: <从 video_info.aspect_ratio 获取>
- duration_seconds: 5
</example>

### 示例：特写 + 情绪表达

<example>
shot plan 数据：
```json
{
  "shot_type": "close_up",
  "angle": "low_angle",
  "movement": "push_in",
  "content": "外婆发现来的不是小红帽，恐惧涌上脸庞",
  "focus_on": ["appear_grandma_home"],
  "prompt_materials": {
    "style_prefix": "hand-drawn illustration, warm color palette, children's storybook style",
    "event_description": "外婆听到敲门声，开门后发现来者是大灰狼",
    "appearances": [
      {"entity": "char_grandma", "visual": {"costume": "白色睡衣，花边睡帽", "hair": "灰白发丝从帽下露出", "physical": "体弱，脸色苍白"}}
    ],
    "minds": [{"entity": "char_grandma", "emotion": "震惊转为恐惧", "behavior": "瞪大双眼，嘴微张，身体往后缩"}],
    "location_state": {"appearance": {"lighting": "昏暗壁炉光", "condition": "温馨小屋内部", "atmosphere": "从温暖骤变为压迫"}}
  },
}
```

视频 prompt：
"hand-drawn illustration, warm color palette, children's storybook style. Close-up from low angle, camera slowly pushing in. An elderly woman in a white nightgown and lace nightcap <<<image_1>>>, wisps of gray hair peeking out, her frail pale face lit by the dim flicker of a fireplace. Her eyes widen in shock, mouth falling slightly open, body instinctively shrinking backward as terror washes over her expression. The cozy cottage interior shifts from warmth to an oppressive, claustrophobic feeling."

参数：
- negative_prompt: "photorealistic, dark, horror, oversaturated"
- mode: "image_to_video"
- reference_image_path: "{project_dir}/assets/frames/cam_grandma_door_shot_0_first.png"
- reference_images: ["{project_dir}/assets/images/appear_grandma_home.png"]
- aspect_ratio: <从 video_info.aspect_ratio 获取>
- duration_seconds: 5
</example>

---

## 写作要点

1. **自然语言而非字段罗列**：不要写成 "costume: red cloak, hair: curly brown"，而是 "a girl in a red cloak, curly brown hair framing her face"。把结构化数据编织成连贯的画面描述。
2. **动作是视频 prompt 的核心**：`minds[].behavior` 和 `event_description` 决定画面中发生什么。首帧图只描述"即将发生"的瞬间，视频 prompt 要描述动作的完整过程。
3. **镜头语言要明确**：在 prompt 开头标明 shot_type + angle + movement（如 "Medium shot, eye level, static camera"），视频模型会据此控制构图和运镜。
4. **角色外形从简**：因为 reference_images 已经传入了角色参考图，prompt 中不需要重复所有服装细节，用最显著的视觉特征标识角色即可（如 "red-cloaked girl"、"gray-brown wolf"）。
5. **参考图-角色关联**：必须在 prompt 中标注哪张参考图对应哪个角色，否则相似角色会混淆。两种标记语法：
   - **首帧图**（GenerateImage）：使用 `@[role N]`。prompt 最前面加前缀 `"Reference image characters from left to right are: @[role 1], @[role 2]."` ，角色描述旁加 `@[role N]`。编号按 `reference_image_paths` 顺序。
   - **视频**（GenerateVideoSync）：使用 `<<<image_N>>>`，放在角色描述旁（如 "a girl in a red cloak <<<image_1>>>"）。编号按 `reference_images` 顺序。
6. **style_prefix 放 prompt 开头，negative_prefix 放 `negative_prompt` 参数**：不要混放，不要通过 `style` 参数重复传入。
7. **relationships 影响氛围描写**：如果两个角色是"陌生人"，描述中体现初次相遇的试探感；如果是"信任的朋友"，体现亲密随意的互动。不需要直接写出关系名称，而是融入动作和氛围。
8. **prop_states 按需提及**：道具只在画面中有重要作用时提及（如"clutches her basket tighter"），不需要每个 shot 都描述所有道具。
