# Prompt 组合规范

> 为每个 shot 组装 GenerateVideoSync 和 GenerateImage 的 prompt 时，参考本文件。

所有 prompt **必须用英文**。使用分段标注格式（Style / Camera / Scene / Action / Sound / Note），每段内用自然语言描述，不要机械罗列字段。

## 数据来源映射

新数据格式与 prompt 要素的对应关系：

| Prompt 要素 | 数据来源 | 说明 |
|------------|---------|------|
| 风格 | `meta.json` → `style.style_prefix` | 放 Style 段 |
| 负面提示 | `meta.json` → `style.negative_prefix` | 通过 `negative_prompt` 参数传入 |
| 画面比例 | `meta.json` → `video_info.aspect_ratio` | 通过 `aspect_ratio` 参数传入 |
| 对白语言 | `meta.json` → `video_info.language` | 对白文本保持原语言 |
| 镜头语言 | `shots.json` → shot 的 `framing` / `angle` / `movement` | 翻译为英文描述 |
| 画面内容 | `shots.json` → shot 的 `content` | 放 Action 段，翻译为英文，保留空间关系 |
| 场景环境 | `states.json` → focus_on 的 LocationState → `lighting` / `weather` / `atmosphere` | 放 Scene 段 |
| 角色外形 | `states.json` → focus_on 的 CharacterAppearance → `visual` | 放 Action 段，从简，抓关键特征 |
| 角色行为 | `events.json` → 当前事件的 `interactions` / `mood` / `state_changes` | 放 Action 段，视频核心 |
| 对白 | `shots.json` → shot 的 `content`（对白已按时间顺序写在动作节拍中）+ `entities.json` → 角色的 `voice_description` | 嵌入 Action 段动作流程中，附带音色描述 |
| 旁白 | `shots.json` → shot 的 `narration` | Action 段末尾或 Note 段 |
| 音效 | `shots.json` → shot 的 `content`（音效已写在对应动作节拍中） | 放 Sound 段 |
| 参考图 | `states.json` → 各状态的 `reference_image` 字段 | 通过 reference_images 参数传入 |

## 视频 Prompt 结构

Prompt 使用分段标注格式，每段用标签开头，各段职责清晰：

```
Style: {style_prefix}
Camera: {framing}, {angle}, {movement}
Scene: {场景环境描述，含 <<<state_id>>> 标记}
Action: {画面内容——角色动作、空间关系、表演、道具交互，含 <<<state_id>>> 标记。对白嵌入动作流程中，附带音色描述，保持原语言}
Sound: {环境音 + 动作音效，不含 BGM}
Note: No background music. Smooth natural motion. Physically plausible movements.
```

各段说明：

| 段 | 内容来源 | 要点 |
|----|---------|------|
| **Style** | `meta.json` → `style.style_prefix` | 原样放入 |
| **Camera** | shot 的 `framing` / `angle` / `movement` | 翻译为英文（如 "Medium shot, eye level, static camera"） |
| **Scene** | LocationState 的 `lighting` / `weather` / `atmosphere` | 编织成环境描述，用 `<<<location_state_id>>>` 标记 |
| **Action** | shot 的 `content` + events.json 的 `interactions` / `mood` / `state_changes` | 视频核心。角色外形从简（参考图已传入），用 `<<<state_id>>>` 标记。对白跟着动作写，附带 voice_description 音色描述 |
| **Sound** | 从场景和 content 推断 | 只写环境音（森林→鸟鸣风声）和动作音效（奔跑→急促脚步），**不写 BGM** |
| **Note** | 固定约束 | 始终包含 "No background music." 可追加其他约束（如旁白指示） |

### 对白写法

对白嵌入 Action 段的动作流程中，不要堆在末尾：
- 结合 entities.json 中该角色的 `voice_description` 描述音色
- 格式：`...the hare <<<appear_hare_default>>> turns to the tortoise with a smirk and says in a sharp cocky voice "慢吞吞的"... the tortoise <<<appear_tortoise_default>>> glances back calmly and replies in a slow deep voice "一步一步来"...`
- 保持对白原语言

### 旁白写法

如有 `narration` 字段，在 Action 段末尾或 Note 段中写入旁白文本和音色指示。

### 参考图关联标记

两种场景使用不同标记语法：

| 场景 | 工具 | 标记 | 说明 |
|------|------|------|------|
| 首帧图 | GenerateImage | `@[image N]` | 按 reference_image_paths 顺序编号（1-indexed），前缀声明每张图是什么 |
| 视频 | GenerateVideoSync | `<<<state_id>>>` | 用状态 ID 直接标记，如 `<<<appear_tortoise_default>>>`。工具自动按 reference_images 中的文件名匹配转换 |

**视频标记规则**：
- 实体状态图：用 states.json 中的 state_id，如 `<<<appear_hare_default>>>`、`<<<lstate_country_start_morning>>>`、`<<<pstate_finish_ribbon_broken>>>`
- 构图参考图：用 `<<<composition>>>`
- 尾帧：用 `<<<tail_frame>>>`
- reference_images 数组有几张图，prompt 中就必须有几个不同的 `<<<...>>>` 标记，不多不少

## 首帧图 Prompt

首帧图是一张**静态画面**，描述动作发生前一刻的"定格"：
- 有完整场景环境（不是白背景）
- 有具体角色站位和朝向
- 没有动作过程

与视频 prompt 的区别：首帧图只描述一个瞬间，视频 prompt 描述动作的时间推进。

**首帧参考图引用规则**：reference_image_paths 包含所有选中的参考图（角色 + 场景 + 道具），每张都用 `@[image N]` 标记关联到 prompt 中对应描述的位置。前缀格式：`"Reference images: @[image 1] is the hare, @[image 2] is the tortoise, @[image 3] is the meadow starting area."` — 用简短自然语言说明每张图是什么。

## 尾帧在 Prompt 中的使用

根据 `need_tail_frame`、`need_composition_image` 和场景关系，选择对应写法。核心原则：**构图参考图锁定空间位置，prompt 描述动作和变化，两者配合。**

### 不使用尾帧

直接描述当前场景，无需交代前一画面。正常使用角色/场景参考图。

### 场景延续（scene_continuous = true）

空间位置关系靠**构图参考图**控制，不靠 prompt 文字。

1. 先用 GenerateImage 生成构图参考图：输入包括尾帧 + 角色/场景参考图，prompt 描述各元素的精确位置（如"兔子在丝带断口前一步，乌龟在断口另一侧"）
2. 将构图参考图放入 reference_images 数组
3. 视频 prompt 中用 `<<<composition>>>` 标记构图参考图，提示画面从此构图开始：
  `"Action: The scene starts from the composition <<<composition>>>. The hare <<<appear_hare_default>>> skids to a stop, feet scraping dirt..."`
4. Action 段只描述动作和变化，不需要重复空间布局

### 场景转换（换地点）

尾帧 = 前一空间。描述角色如何从旧空间移动到新空间。

- `"The video starts from <<<tail_frame>>>, where the girl is at the forest edge. She walks out of the tree line and approaches the cottage..."`
- 不能只写终点状态（"女孩站在小屋前"），要写移动过程

### 状态转换（角色外观/情绪变化）

尾帧 = 变化前的样子，新参考图 = 变化后的目标。描述变化过程。

- `"The video starts from <<<tail_frame>>>, where the girl's cloak is still intact. The wolf lunges and tears the red cloak <<<appear_red_torn>>>, leaving it shredded..."`
- 两种参考图各有角色：尾帧 = before，新参考图 = after

## 写作要点

1. **Action 段用自然语言**：不要写 "costume: red cloak, hair: curly brown"，而是 "a girl in a red cloak, curly brown hair framing her face"
2. **Action 是视频核心**：behavior 和 content 决定画面中发生什么，给予最多篇幅
3. **角色外形从简**：reference_images 已传入角色参考图，Action 中用关键特征标识即可
4. **negative_prefix 走参数不进 prompt**：style_prefix 放 Style 段，negative_prefix 放 negative_prompt 参数
5. **不要遗漏 `<<<state_id>>>` 标记**：缺标记 = 角色一致性丢失

## Prompt 生成后自检

### 视频 prompt 自检

每次组装完视频 prompt、确定 reference_images 列表后，执行以下 2 点检查：

1. **数量匹配**：reference_images 有 N 张 → prompt 中必须有 N 个不同的 `<<<...>>>` 标记。少一个都不行。
2. **尾帧/构图图使用**：如果使用了尾帧或构图参考图，检查 prompt 中是否正确使用了 `<<<tail_frame>>>` 或 `<<<composition>>>`，且有转换/延续过程描述。

### 首帧 prompt 自检

每次组装完首帧 prompt、确定 reference_image_paths 列表后，执行以下 2 点检查：

1. **数量匹配**：reference_image_paths 有 N 张 → prompt 前缀中必须有 N 个 `@[image N]`，prompt 正文中也必须有 N 个 `@[image N]` 标记。
2. **实体对应**：每个 `@[image N]` 标记必须紧跟对应实体（角色/场景/道具）的描述。编号严格按 reference_image_paths 列表顺序。

## 示例

### 示例：中景双人互动（reference_to_video）

> 更多示例（尾帧接续、构图参考图）见 `${AGENT_DIR}/examples-prompt-video.md`，workflow 在遇到对应模式时用 ReadFile 加载。

<example>
shots.json 数据：
```json
{
  "id": "evt_wolf_encounter_shot_1",
  "event_id": "evt_wolf_encounter",
  "framing": "medium",
  "angle": "eye_level",
  "movement": "static",
  "content": "林间小路上，小红帽停步；右侧树后传来树枝折断声，大灰狼从树后探出，两者相距约3米 → 大灰狼弓身缓步靠近，伪装友善地说：「你好啊小姑娘，你要去哪里呀？」",
  "focus_on": ["appear_red_neat", "appear_wolf_natural", "lstate_forest_bright"],
  "narration": ""
}
```

states.json 中查到：
- appear_red_neat → visual: {costume: "红色丝绒斗篷，白色连衣裙"}, reference_image: "assets/images/appear_red_neat.png"
- appear_wolf_natural → visual: {costume: "灰褐色毛皮，蓬松尾巴"}, reference_image: "assets/images/appear_wolf_natural.png"
- lstate_forest_bright → lighting: "丁达尔光束", atmosphere: "童话美好"
- 同 event 的 interactions / state_changes: char_red → "停下脚步，侧头倾听"; char_wolf → "缓缓走出，弓着身体"

视频 prompt：
"Style: hand-drawn illustration, warm color palette, children's storybook style.
Camera: Medium shot, eye level, static camera.
Scene: Sunlit forest clearing <<<lstate_forest_bright>>> with god rays filtering through the canopy, scattered wildflowers along the path.
Action: On the left side of the frame, a little girl in a red velvet cloak <<<appear_red_neat>>> stops on the forest path, tilting her head with wide curious eyes and a hint of unease. About three meters away on the right, from behind a large oak tree, a tall gray-brown wolf <<<appear_wolf_natural>>> slowly emerges, crouching low to appear smaller, and says in a deep warm friendly voice '你好啊小姑娘，你要去哪里呀？'.
Sound: a twig snapping, gentle breeze rustling leaves.
Note: No background music. Smooth natural motion. Physically plausible movements."

参数：
- mode: "reference_to_video"（狼中途出场，不适合首帧）
- reference_images: ["assets/images/appear_red_neat.png", "assets/images/appear_wolf_natural.png", "assets/images/lstate_forest_bright.png"]
- negative_prompt: "photorealistic, dark, horror"
- duration_seconds: 5
- aspect_ratio: "16:9"
</example>

