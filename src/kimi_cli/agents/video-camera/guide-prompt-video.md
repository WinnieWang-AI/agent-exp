# Prompt 组合规范

> 为每个 shot 组装 GenerateVideoSync 和 GenerateImage 的 prompt 时，参考本文件。

所有 prompt **必须用英文**。将 shots.json 和 states.json 中的结构化数据编织成**流畅的自然语言描述**，不要机械罗列字段。

## 数据来源映射

新数据格式与 prompt 要素的对应关系：

| Prompt 要素 | 数据来源 | 说明 |
|------------|---------|------|
| 风格 | `meta.json` → `production_styles[0].style_prefix` | 放 prompt 开头 |
| 负面提示 | `meta.json` → `production_styles[0].negative_prefix` | 通过 `negative_prompt` 参数传入 |
| 画面比例 | `meta.json` → `video_info.aspect_ratio` | 通过 `aspect_ratio` 参数传入 |
| 对白语言 | `meta.json` → `video_info.language` | 对白文本保持原语言 |
| 镜头语言 | `shots.json` → shot 的 `shot_type` / `angle` / `movement` | 翻译为英文描述 |
| 画面内容 | `shots.json` → shot 的 `content` | 翻译为英文，保留空间关系描述 |
| 场景环境 | `states.json` → focus_on 的 LocationState → `lighting` / `weather` / `atmosphere` | 编织进场景描述 |
| 角色外形 | `states.json` → focus_on 的 CharacterAppearance → `visual` | 从简，抓关键特征 |
| 角色行为 | `states.json` → active_during 同 event 的 CharacterMind → `emotion` / `behavior` | 视频核心 |
| 对白 | `shots.json` → shot 的 `dialogues` | 写入 Sound: 段 |
| 音效 | `shots.json` → shot 的 `sfx` | 写入 Sound: 段 |
| 参考图 | `states.json` → 各状态的 `reference_image` 字段 | 通过 reference_images 参数传入 |

## 视频 Prompt 结构

将以下要素编织成自然语言（不需要固定顺序，但都要覆盖）：

1. **风格**：`style_prefix` 放在 prompt 开头
2. **镜头语言**：景别 + 角度 + 运动（如 "Medium shot, eye level, static camera"）
3. **画面内容与空间关系**：content 的英文翻译，保留角色位置关系
4. **场景环境**：LocationState 的 lighting / weather / atmosphere
5. **角色外形**：从简，用最显著特征标识（如 "red-cloaked girl"），参考图已传入不需重复全部细节
6. **角色表演**：CharacterMind 的 emotion + behavior — 这是视频的核心
7. **道具**：只在画面中有重要作用时提及
8. **参考图关联标记**：`<<<image_N>>>`，放在角色/场景首次出现的描述旁
9. **声音描述**：以 "Sound:" 开头，放在 prompt 末尾

### 声音描述（Sound）

视频模型同时生成画面和声音。在 prompt 末尾用 "Sound:" 描述该镜头的声音：

- **环境音**：从场景推断（森林→鸟鸣风声，室内→壁炉声）
- **动作音效**：从 sfx 字段和角色行为推断（奔跑→急促脚步，开门→门轴吱呀）
- **角色对白**：从 dialogues 字段提取，格式 `the girl says "奶奶我来看你了"`，保持原语言
- **不描述 BGM** — BGM 由作曲 agent 独立生成

### 参考图关联标记

两种场景使用不同标记语法：

| 场景 | 工具 | 标记 | 前缀 |
|------|------|------|------|
| 首帧图 | GenerateImage | `@[role N]` | `"Reference image characters from left to right are: @[role 1], @[role 2]."` 放在 prompt 最前面 |
| 视频 | GenerateVideoSync | `<<<image_N>>>` | 无前缀，直接放在角色描述旁 |

编号按参数中图片列表的顺序（reference_image_paths 或 reference_images）。

**自查**：reference_images 有几张，prompt 中就必须有几个 `<<<image_N>>>` 标记。

## 首帧图 Prompt

首帧图是一张**静态画面**，描述动作发生前一刻的"定格"：
- 有完整场景环境（不是白背景）
- 有具体角色站位和朝向
- 没有动作过程

与视频 prompt 的区别：首帧图只描述一个瞬间，视频 prompt 描述动作的时间推进。

## 跨镜头接续时的 Prompt 写法

使用了前一 shot 尾帧作为参考图时，prompt 中必须交代时序：

- 描述角色从上一个场景如何过渡到当前场景
- 如果尾帧放在 reference_images 中：`"The video starts from <<<image_N>>>, where the girl is at the forest edge. She walks out and approaches the cottage..."`
- 不能只写静态画面描述（"女孩站在小屋前"），要写动态过渡（"女孩从森林走出，来到小屋前"）

## 写作要点

1. **自然语言而非字段罗列**：不要写 "costume: red cloak, hair: curly brown"，而是 "a girl in a red cloak, curly brown hair framing her face"
2. **动作是核心**：behavior 和 content 决定画面中发生什么
3. **角色外形从简**：reference_images 已传入角色参考图，prompt 中用关键特征标识即可
4. **style_prefix 放开头，negative_prefix 放 negative_prompt 参数**：不混放
5. **不要遗漏 `<<<image_N>>>` 标记**：缺标记 = 角色一致性丢失

## 示例

### 示例 1：中景双人互动（reference_to_video）

<example>
shots.json 数据：
```json
{
  "id": "evt_wolf_encounter_shot_1",
  "event_id": "evt_wolf_encounter",
  "shot_type": "medium",
  "angle": "eye_level",
  "movement": "static",
  "content": "林间小路上，小红帽停步，大灰狼从右侧树后探出，两者相距约3米",
  "focus_on": ["appear_red_neat", "appear_wolf_natural", "lstate_forest_bright"],
  "dialogues": [{"speaker": "char_wolf", "text": "你好啊小姑娘，你要去哪里呀？", "tone": "伪装友善"}],
  "sfx": ["树枝折断声"]
}
```

states.json 中查到：
- appear_red_neat → visual: {costume: "红色丝绒斗篷，白色连衣裙"}, reference_image: "assets/images/appear_red_neat.png"
- appear_wolf_natural → visual: {costume: "灰褐色毛皮，蓬松尾巴"}, reference_image: "assets/images/appear_wolf_natural.png"
- lstate_forest_bright → lighting: "丁达尔光束", atmosphere: "童话美好"
- 同 event 的 CharacterMind: char_red → behavior: "停下脚步，侧头倾听"; char_wolf → behavior: "缓缓走出，弓着身体"

视频 prompt：
"hand-drawn illustration, warm color palette, children's storybook style. Medium shot, eye level, static camera. On the left side of the frame, a little girl in a red velvet cloak <<<image_1>>> stops on the forest path, tilting her head with wide curious eyes and a hint of unease. About three meters away on the right, from behind a large oak tree, a tall gray-brown wolf <<<image_2>>> slowly emerges, crouching low to appear smaller. Sunlit forest clearing <<<image_3>>> with god rays and scattered wildflowers. Sound: a twig snapping, gentle breeze, the wolf says in a warm friendly tone '你好啊小姑娘，你要去哪里呀？'"

参数：
- mode: "reference_to_video"（狼中途出场，不适合首帧）
- reference_images: ["assets/images/appear_red_neat.png", "assets/images/appear_wolf_natural.png", "assets/images/lstate_forest_bright.png"]
- negative_prompt: "photorealistic, dark, horror"
- duration_seconds: 5
- aspect_ratio: "16:9"
</example>

### 示例 2：同 event 尾帧接续（image_to_video）

<example>
当前 shot 是 evt_farewell_shot_2，前一 shot evt_farewell_shot_1 已生成。

尾帧提取：
```
ExtractFrame(
  video_path="assets/shots/evt_farewell_shot_1.mp4",
  output_path="assets/frames/evt_farewell_shot_2_tail.png",
  position="last"
)
```

视频 prompt：
"hand-drawn illustration, warm color palette. Close-up, eye level, static camera. The mother <<<image_1>>> leans forward and places a gentle kiss on the girl's forehead, her eyes glistening with worry. Morning sunlight warms the doorway. Sound: soft rustling of fabric, a quiet sigh from the mother."

参数：
- mode: "image_to_video"
- reference_image_path: "assets/frames/evt_farewell_shot_2_tail.png"
- reference_images: ["assets/images/appear_mother_home.png"]
- duration_seconds: 4
</example>

### 示例 3：特写情绪镜头 + 首帧（image_to_video）

<example>
单人特写，角色开头在画面中，push_in 运动幅度小 → 生成首帧 → image_to_video。

首帧 prompt：
"Reference image characters from left to right are: @[role 1]. hand-drawn illustration, warm color palette. Close-up from low angle. An elderly woman in a white nightgown @[role 1], gray hair wisps, frail pale face lit by dim fireplace flicker. She stares forward with wide frozen eyes. Cozy cottage interior with creeping unease."

视频 prompt：
"hand-drawn illustration, warm color palette. Close-up from low angle, camera slowly pushing in. An elderly woman in a white nightgown <<<image_1>>>, her eyes widen in shock, mouth falling open, body shrinking backward as terror washes over her face. The cozy cottage shifts from warmth to oppressive claustrophobia. Sound: crackling fireplace, a sharp gasp, creaking floorboards."

参数：
- mode: "image_to_video"
- reference_image_path: "assets/frames/evt_grandma_door_shot_1_first.png"
- reference_images: ["assets/images/appear_grandma_home.png"]
</example>
