# Story Graph 设计文档

## 1. 动机

当前 video-creator agent 使用线性的 `script.json` + `storyboard.json` 描述故事。这种结构存在几个问题：

- **平行叙事丢失**：同时发生的事件（小红帽采花 / 狼奔向外婆家）只能排成先后，无法表达"同时"
- **状态追踪靠上下文**：角色换装、道具损坏、环境变化全靠 LLM 在上下文中记忆，容易前后矛盾
- **连续性决策靠经验**：哪些镜头需要尾帧接续、哪些需要参考图，现在由 LLM 逐镜头判断，没有结构化依据
- **音频与画面脱节**：BGM、环境音、对白作为独立阶段处理，和视觉叙事没有结构化关联

Story Graph 用图结构替代线性列表，以 **Event（事件）** 为中心节点，把角色、物品、环境、镜头、音频的状态全部挂上去。生成每个镜头时只需做一次图查询，就能拿到所有需要的信息。

---

## 2. 节点类型

### 2.1 实体节点（身份，不变）

存储角色/物品/环境的**恒定属性**——无论剧情如何推进都不会变的部分。

#### Character（角色）

```json
{
  "id": "char_red",
  "type": "character",
  "name": "小红帽",
  "fixed_traits": "7-8岁小女孩，圆脸，大眼睛，棕色卷发，身材娇小",
  "relationships": {
    "char_mother": [
      {"kind": "母女", "since": null}
    ],
    "char_wolf": [
      {"kind": "陌生人", "since": null},
      {"kind": "受骗者→欺骗者", "since": "evt_red_arrives"},
      {"kind": "猎物→捕食者", "since": "evt_wolf_eats_red"}
    ]
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识符，`char_` 前缀 |
| `name` | string | 角色名 |
| `fixed_traits` | string | 不随剧情变化的外貌特征（体型、骨架、种族等） |
| `relationships` | map<character_id, list> | 与其他角色的关系，按时间排序 |

**关系字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `kind` | string | 关系性质的自然语言描述 |
| `since` | event_id \| null | 从哪个事件起变为该关系，`null` 表示故事开始前就存在 |

查询方式：给定一个 Event，在时间线上找到它的位置，取关系列表中最后一个 `since <= 当前事件` 的条目。

#### Prop（物品/道具）

```json
{
  "id": "prop_hood",
  "type": "prop",
  "name": "红色斗篷",
  "fixed_traits": "鲜红色丝绒连帽斗篷，到膝盖长度",
  "relationships": {
    "char_grandma": [{"kind": "亲手缝制的礼物", "since": null}],
    "char_red": [{"kind": "最珍爱的衣物，身份象征", "since": null}]
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识符，`prop_` 前缀 |
| `name` | string | 物品名 |
| `fixed_traits` | string | 不变的基本形态 |
| `relationships` | map<character_id, list> | 与角色的关系，按时间排序，格式同 Character.relationships |

物品与角色的关系也支持随时间变化。例如外婆的衣物对狼来说，在 `evt_wolf_disguise` 之前没有关系，之后才变成"伪装工具"：

```json
{
  "id": "prop_grandma_clothes",
  "type": "prop",
  "name": "外婆的衣物",
  "fixed_traits": "白色睡帽，碎花睡衣，老花眼镜",
  "relationships": {
    "char_grandma": [{"kind": "贴身衣物", "since": null}],
    "char_wolf": [{"kind": "伪装工具", "since": "evt_wolf_disguise"}]
  }
}
```

这种关系对视频生成的意义：当镜头聚焦到一个物品时（如 `pstate_hood_wrinkled`），查到它与外婆的关系是"亲手缝制的礼物"，Linearizer 就知道这不只是一个道具损坏的镜头，值得给一个有情感分量的特写。

#### Location（场所）

```json
{
  "id": "loc_forest",
  "type": "location",
  "name": "森林",
  "fixed_traits": "茂密的欧洲针叶林，高大的松树和橡树"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识符，`loc_` 前缀 |
| `name` | string | 场所名 |
| `fixed_traits` | string | 不变的结构特征 |

### 2.2 状态节点（会变）

同一实体在不同剧情阶段的具体表现。

> **重要原则：** 状态只在发生真正变化时才创建新节点。多个事件之间如果没有明显变化（如出门前和走路时），应共享同一个状态节点。`phase` 应描述**状态本身**（如"天真无忧"、"整洁出行装"），而非事件名称（如"出门・走路"）。

角色状态分为**两层**：

#### CharacterAppearance（外形状态）

描述角色的**视觉外形**：服装、发型、身体状态等。只有外形发生重要变化时（换装、受伤、变装等）才创建新节点。**每个节点会生成一张形象参考图**。

```json
{
  "id": "appear_red_neat",
  "type": "character_appearance",
  "entity": "char_red",
  "phase": "整洁出行装",
  "visual": {
    "costume": "红色丝绒斗篷，白色连衣裙，棕色小皮靴",
    "hair": "棕色卷发散落在斗篷里",
    "physical": "健康，红润脸颊",
    "props": ["prop_hood", "prop_basket"]
  },
  "reference_image": "assets/images/red_neat.png"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `entity` | character_id | 所属角色 |
| `phase` | string | 外形状态名称 |
| `visual.costume` | string | 服装描述 |
| `visual.hair` | string | 发型描述 |
| `visual.physical` | string | 身体状态（伤痕、疲劳等） |
| `visual.props` | list<prop_id> | 随身物品引用 |
| `reference_image` | string | 形象参考图路径（由生成流程填充） |

#### CharacterMind（心态状态）

描述角色的**情绪、心理、行为模式**。心态变化频率通常高于外形变化。不需要生成参考图，用于指导表演和对白风格。

```json
{
  "id": "mind_red_innocent",
  "type": "character_mind",
  "entity": "char_red",
  "phase": "天真无忧",
  "emotion": "开心，天真，对世界充满好奇",
  "behavior": "蹦蹦跳跳，东张西望，和陌生人也会友善交谈"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `entity` | character_id | 所属角色 |
| `phase` | string | 心态名称 |
| `emotion` | string | 情绪/心理状态 |
| `behavior` | string | 行为模式、肢体语言 |

> **层级关系**：Character → Appearance → Mind。心态节点通过 `HAS_MIND` 边挂在外形节点上（根据 active_during 事件重叠自动关联），而非直接挂在角色上。
>
> **外形 vs 心态的区别**：小红帽从出门到被吞，外形一直是"整洁出行装"（一个 appearance 节点），但心态从"天真无忧"→"困惑渐恐"变了两次（两个 mind 节点挂在同一个 appearance 下）。镜头生成查外形以获取视觉参考图，查心态以获取表演指导。

#### PropState

> **重要原则：** 道具状态只在**道具本身外观发生变化**时才创建。"挂在腰间"vs"使用中"（斧头没变）、"戴在头上"vs"滑到背后"（斗篷没变）这些是角色的姿态/动作，不是道具状态。只有"完好"→"皱巴巴"、"整洁"→"撕碎"这种道具本身的视觉变化才需要新状态。

```json
{
  "id": "pstate_basket_full",
  "type": "prop_state",
  "entity": "prop_basket",
  "phase": "装满完好",
  "appearance": {
    "visual": "藤篮盖着红白格子布，鼓鼓的，露出面包和酒瓶边缘",
    "condition": "完好"
  },
  "reference_image": "assets/images/basket_full.png"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `entity` | prop_id | 所属物品 |
| `appearance.visual` | string | 外观描述 |
| `appearance.condition` | string | 状态（完好/破损/沾血等） |

#### LocationState

```json
{
  "id": "lstate_forest_bright",
  "type": "location_state",
  "entity": "loc_forest",
  "phase": "明亮的林间小路",
  "appearance": {
    "lighting": "阳光透过树冠的丁达尔光束，光斑洒在小路上",
    "weather": "晴，微风，树叶沙沙",
    "condition": "小路两旁有野花，蝴蝶飞舞",
    "atmosphere": "童话般美好，隐隐暗示深处更暗"
  },
  "reference_image": "assets/images/forest_bright.png"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `entity` | location_id | 所属场所 |
| `appearance.lighting` | string | 光照 |
| `appearance.weather` | string | 天气/室内外环境 |
| `appearance.condition` | string | 场所状态（完好/破损等） |
| `appearance.atmosphere` | string | 氛围 |

> **`based_on` 字段**：当一个状态的视觉基于另一个状态做微调时（如"劫后归暖"基于"整洁温馨"），使用 `based_on` 指向基准状态。生成系统据此用基准状态的参考图作为起点，只应用 delta 修改，保证视觉连续性。适用于所有状态类型（CharacterAppearance、PropState、LocationState）。

### 2.3 Event（事件）

故事的核心节点。所有状态、镜头、音频都通过边挂到 Event 上。

```json
{
  "id": "evt_wolf_encounter",
  "type": "event",
  "description": "大灰狼从树后现身，假装友善地搭话，套出外婆住处",
  "happens_at": "loc_forest",
  "happens_during": "time_midday",
  "interactions": [
    {
      "between": ["char_red", "char_wolf"],
      "style": "狼蹲下平视小红帽，语气温柔；小红帽微微后退但仍回答"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | string | 事件描述 |
| `happens_at` | location_id | 发生地点 |
| `happens_during` | timeline_id | 发生时间 |
| `interactions` | list | 该事件中角色间的互动方式（动作层面） |

`interactions` 和 `relationships` 的区别：
- `relationships`（在 Character 上）：他们**是什么关系** — "母女"、"宿敌"、"猎物与捕食者"
- `interactions`（在 Event 上）：他们在这个事件中**具体怎么互动** — "狼蹲下平视小红帽"

### 2.4 TimeLine（故事时间线）

```json
{
  "id": "time_morning",
  "type": "timeline",
  "label": "清晨"
}
```

表示**故事内部的叙事时间**，用自然语言描述故事中的时间阶段（如"清晨"、"午后"、"三天后"、"深夜"）。多个事件可以共享同一个 TimeLine 节点，表示它们发生在同一个故事时间段内。

**注意：TimeLine 不是制片时间轴。** 不要写成视频的秒数区间（如"0-3秒"、"10-22秒"）。每个镜头的时长由 `production_styles.duration` 和 Linearizer 的分配逻辑决定，与 TimeLine 无关。

### 2.5 CameraDirective（镜头语言）

```json
{
  "id": "cam_wolf_encounter",
  "type": "camera_directive",
  "for_event": "evt_wolf_encounter",
  "shots": [
    {
      "order": 1,
      "shot_type": "medium",
      "angle": "eye_level",
      "movement": "static",
      "focus_on": ["appear_red_neat"],
      "content": "小红帽停下脚步，感觉有什么在看她"
    },
    {
      "order": 2,
      "shot_type": "close_up",
      "angle": "low_angle",
      "movement": "slow_push_in",
      "focus_on": ["appear_wolf_natural"],
      "content": "狼从阴影中走出，仰拍让它看起来更大"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `for_event` | event_id \| list<event_id> | 服务于哪个事件（PARALLEL 事件可共享一个 directive 做交叉剪辑） |
| `shots` | list | 该事件的分镜列表 |
| `shots[].order` | int | 镜头顺序 |
| `shots[].shot_type` | string | 景别 |
| `shots[].angle` | string | 角度 |
| `shots[].movement` | string | 运镜 |
| `shots[].focus_on` | list<state_id> | 镜头聚焦的实体状态 |
| `shots[].content` | string | 该 shot 的画面内容与空间布局 |

**镜头语言词汇表：**

```
shot_type:  extreme_wide | wide | medium | medium_close | close_up
            | extreme_close | detail_insert | over_shoulder | pov

angle:      eye_level | low_angle | high_angle | bird_eye
            | dutch_angle | worm_eye

movement:   static | pan_left | pan_right | tilt_up | tilt_down
            | push_in | pull_out | tracking | handheld_shake
            | crane_up | crane_down | slow_360_orbit
            | whip_pan | zoom_in | zoom_out | fast_tracking
```

### 2.6 ProductionStyle（制作风格 + 画面比例）

全局或分段的视觉风格与画面比例。作为图中的一等节点，通过 `style_active_during` 关联到事件，支持风格中途切换（如闪回用不同风格、梦境用不同比例）。

```json
{
  "id": "style_main",
  "type": "production_style",
  "description": "手绘插画风格，暖色调，儿童绘本质感",
  "style_prefix": "hand-drawn illustration, warm color palette, children's storybook style",
  "negative_prefix": "photorealistic, dark, horror, oversaturated",
  "aspect_ratio": "16:9"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识符，`style_` 前缀 |
| `description` | string | 风格的自然语言描述（给人类和 LLM 看） |
| `style_prefix` | string | 注入视频/图片生成 prompt 前缀的英文风格描述 |
| `negative_prefix` | string | 注入 negative prompt 的英文排除项 |
| `aspect_ratio` | string | 画面比例，如 `"16:9"`、`"9:16"`、`"1:1"` |

**多风格场景示例**（闪回/梦境）：

```json
{
  "production_styles": [
    {
      "id": "style_main",
      "type": "production_style",
      "description": "写实风格，自然光",
      "style_prefix": "photorealistic, natural lighting, cinematic",
      "negative_prefix": "cartoon, anime, oversaturated",
      "aspect_ratio": "16:9"
    },
    {
      "id": "style_flashback",
      "type": "production_style",
      "description": "泛黄复古回忆风格",
      "style_prefix": "sepia tone, soft focus, vintage film grain, nostalgic",
      "negative_prefix": "modern, sharp, vibrant colors",
      "aspect_ratio": "16:9"
    }
  ],
  "style_active_during": {
    "style_main": ["evt_farewell", "evt_forest_walk", "evt_wolf_encounter"],
    "style_flashback": ["evt_memory_scene"]
  },
  "style_transitions": [
    {"from": "style_main", "to": "style_flashback", "trigger": "evt_memory_scene", "method": "crossfade_2s"}
  ]
}
```

> **大多数视频只需要一个 `style_main` 节点**，`style_active_during` 指向所有事件即可。只有风格切换（闪回、梦境、画风突变）才需要多个节点。

> **替代 `style_guide.json`**：之前由 video-creator 在 Phase 1 创建的 `style_guide.json` 现在由 ProductionStyle 节点承担。Linearizer 直接从图中读取每个 shot 的 style，不再需要外部文件。

### 2.7 AudioLayer + AudioState（音频）

音频采用 **Layer（层）+ State chain（状态链）** 结构，和视觉实体同构。

一个场景通常有多个音频层同时存在：BGM、环境音、对白、音效。

#### AudioLayer

```json
{
  "id": "audio_bgm",
  "type": "audio_layer",
  "kind": "bgm",
  "description": "背景音乐"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `kind` | string | 层类型：`bgm` / `ambience` / `dialogue` / `sfx` |

#### AudioState（BGM 类型）

```json
{
  "id": "astate_bgm_tension",
  "type": "audio_state",
  "layer": "audio_bgm",
  "phase": "遇狼・不安渗入",
  "style": "吉他变为不协和拨弦，加入低沉大提琴，竖笛消失",
  "tempo": "slowing",
  "intensity": "medium",
  "instruments": ["木吉他（不协和）", "大提琴", "定音鼓（极远）"],
  "music_prompt": "Acoustic guitar turns dissonant, cello enters with low drone, distant timpani, 80 BPM, fairy tale turning dark"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `layer` | audio_layer_id | 所属音频层 |
| `style` | string | 风格描述 |
| `tempo` | string | 节奏 |
| `intensity` | string | 强度 |
| `instruments` | list<string> | 乐器组成 |
| `music_prompt` | string | 直接用于 GenerateMusic 的 prompt |

#### AudioState（环境音类型）

```json
{
  "id": "astate_amb_forest_quiet",
  "type": "audio_state",
  "layer": "audio_ambience",
  "phase": "森林・鸟鸣停止",
  "style": "鸟鸣突然减少，风声变大，远处有树枝折断声"
}
```

#### AudioState（对白类型）

```json
{
  "id": "astate_dial_wolf_hello",
  "type": "audio_state",
  "layer": "audio_dialogue",
  "speaker": "char_wolf",
  "text": "你好啊，小姑娘。这么好的天气，你要去哪里呀？",
  "tone": "故作温柔，但声音低沉有压迫感",
  "voice_direction": "deep voice pretending to be gentle, slightly too smooth, unsettling undertone"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `speaker` | character_id | 说话者 |
| `text` | string | 台词内容 |
| `tone` | string | 语气描述（给人看） |
| `voice_direction` | string | 语音生成指令（给 GenerateSpeech） |

---

## 3. 边类型

### 3.1 状态边

| 边 | 方向 | 含义 |
|---|---|---|
| `HAS_STATE` | Entity → State | 实体拥有某个状态（Character→Appearance, Prop→PropState, Location→LocationState） |
| `HAS_MIND` | Appearance → Mind | 外形状态下挂载的心态状态（根据 active_during 事件重叠自动关联） |
| `TRANSITIONS_TO` | State → State | 状态演变 |
| `ACTIVE_DURING` | State → Event | 该状态在此事件期间生效 |

`TRANSITIONS_TO` 边携带属性：

```json
{
  "from": "appear_red_neat",
  "to": "appear_red_disheveled",
  "type": "TRANSITIONS_TO",
  "trigger": "evt_rescue",
  "delta": {
    "costume": "斗篷变皱沾灰",
    "hair": "整齐→凌乱"
  }
}
```

| 属性 | 说明 |
|------|------|
| `trigger` | 触发状态变化的事件 |
| `delta` | 变化描述。可用于基于前一状态的参考图做 image-to-image 变换 |

`delta` 格式约定：
- `"field": "旧值→新值"` — 替换
- `"+field": [...]` — 新增
- `"-field": [...]` — 移除

### 3.2 时空边

| 边 | 方向 | 含义 |
|---|---|---|
| `HAPPENS_AT` | Event → Location | 事件发生地 |
| `HAPPENS_DURING` | Event → TimeLine | 事件发生时间 |
| `BASED_ON` | State → State | 视觉基于某个基准状态微调，生成时参考基准状态的参考图 |

这两种边直接作为 Event 的字段（`happens_at`、`happens_during`），不需要单独的边对象。

#### RELATIONSHIP（动态关系边）

| 边 | 方向 | 含义 |
|---|---|---|
| `RELATIONSHIP` | Entity ↔ Entity | 两个实体在某个时间点的关系 |

RELATIONSHIP 边不持久存储在图数据中，而是根据 `Character.relationships` 的时间线数据**动态计算**：给定一个 Event，按 event_sequence 的拓扑排序确定该事件的时间位置，然后取每对实体关系列表中最后一个 `since <= 当前事件` 的条目。

在可视化中，点击一个 Event 节点时，会动态计算并显示该时刻所有生效的关系边（橙色标注线），点击其他地方后消失。

### 3.3 时序边

| 边 | 方向 | 含义 |
|---|---|---|
| `THEN` | Event → Event | 时序/因果（A 发生后 B 发生） |
| `PARALLEL` | Event ↔ Event | 同时发生 |

```json
{
  "event_sequence": [
    {"from": "evt_farewell", "to": "evt_forest_walk", "type": "THEN"},
    {"from": "evt_wolf_encounter", "to": "evt_red_picks_flowers", "type": "THEN"},
    {"from": "evt_wolf_encounter", "to": "evt_wolf_runs_ahead", "type": "THEN"},
    {"from": "evt_red_picks_flowers", "to": "evt_wolf_runs_ahead", "type": "PARALLEL"}
  ]
}
```

`PARALLEL` 边是 Linearizer 做交叉剪辑的依据。

### 3.4 镜头边

| 边 | 方向 | 含义 |
|---|---|---|
| `CAMERA_FOR` | CameraDirective → Event | 镜头指令服务于某事件 |
| `FOCUS_ON` | Shot → State | 某个分镜聚焦于某个实体状态 |

直接作为 CameraDirective 的字段（`for_event`、`shots[].focus_on`）。

### 3.5 风格边

| 边 | 方向 | 含义 |
|---|---|---|
| `STYLE_ACTIVE_DURING` | ProductionStyle → Event | 该风格在此事件期间生效 |
| `STYLE_TRANSITIONS_TO` | ProductionStyle → ProductionStyle | 风格切换（携带 `trigger` 和 `method`） |

风格边使用与其他状态相同的 `*_active_during` / `*_transitions` 模式，存储在 `style_active_during` 和 `style_transitions` 中。

### 3.6 音频边

音频状态使用与视觉状态相同的 `HAS_STATE`、`TRANSITIONS_TO`、`ACTIVE_DURING` 边。

`TRANSITIONS_TO` 音频边额外携带 `method` 属性：

```json
{
  "from": "astate_bgm_pastoral",
  "to": "astate_bgm_uneasy",
  "type": "TRANSITIONS_TO",
  "trigger": "evt_wolf_encounter",
  "method": "crossfade_3s"
}
```

**音频转场方式词汇表：**

```
method:  hard_cut         # 硬切，瞬间切换
         crossfade_{N}s   # 交叉淡入淡出 N 秒
         fade_out_{N}s    # 淡出 N 秒
         fade_in_{N}s     # 淡入 N 秒
         duck             # 压低（对白进入时 BGM 降低）
         swell            # 渐强涌入
         stinger          # 一击音效后切换
```

---

## 4. 图的全貌

```
                            TimeLine
                               ^ HAPPENS_DURING
                               |
  +------- Character -HAS_STATE-> Appearance -HAS_MIND-> Mind      Event <-HAPPENS_AT- Location
  |            |                    |   |                  |         ^ |                  |
  |        relationships      ACTIVE_DURING          ACTIVE_DURING  |  |              HAS_STATE
  |         (带时间线)        TRANSITIONS_TO           (表演指导) THEN/  |                  v
  |                                                                   |           LocationState
  |                                                                   |
  +------- Prop ----HAS_STATE--> PropState ---ACTIVE_DURING-----------+
  |                                                                   |
  |     CameraDirective --CAMERA_FOR----------------------------------+
  |       (shots[]:                                                   |
  |        shot_type,          --FOCUS_ON--> State                    |
  |        angle,                                                     |
  |        movement)                                                  |
  |                                                                   |
  +---- AudioLayer -HAS_STATE-> AudioState -ACTIVE_DURING------------+
  |       (bgm/ambience/          (style, tempo,                     |
  |        dialogue/sfx)           music_prompt)                     |
  |                                                                  |
  +---- ProductionStyle --------STYLE_ACTIVE_DURING-----------------+
          (style_prefix,
           negative_prefix,
           aspect_ratio)
```

**以 Event 为中心的查询：**

```
evt_fight
  |-- WHO:    CharacterAppearance (视觉外形) + CharacterMind (情绪/行为)
  |-- WITH:   PropState (物品当前状态)
  |-- WHERE:  LocationState (环境当前状态)
  |-- WHEN:   TimeLine
  |-- BETWEEN: Character.relationships (查当前生效的关系)
  |-- HOW:    interactions (具体互动方式)
  |-- CAMERA: CameraDirective.shots (镜头语言)
  |-- SOUND:  AudioState per layer (BGM + 环境音 + 对白)
  +-- STYLE:  ProductionStyle (视觉风格 + 画面比例)
```

---

## 5. 状态统一模式

Prop、Location、AudioLayer 三种实体遵循相同的单层状态模式：

```
Entity (身份，不变)
  |
  +--HAS_STATE--> State_1 --TRANSITIONS_TO(trigger, delta)--> State_2 --TRANSITIONS_TO--> ...
                    |                                           |
              ACTIVE_DURING                               ACTIVE_DURING
                    |                                           |
                    v                                           v
                [Event_A, Event_B]                        [Event_C, Event_D]
```

Character 使用**双层状态模式**：

```
Character (身份，不变)
  |
  +--HAS_STATE--> Appearance_1 --TRANSITIONS_TO--> Appearance_2 --...
                    |       |                         |
                 HAS_MIND   ACTIVE_DURING          HAS_MIND
                    |       |                         |
                    v       v                         v
                 Mind_1  [Event_A, ...]            Mind_3
                    |
               TRANSITIONS_TO
                    |
                    v
                 Mind_2
```

Appearance→Mind 的 HAS_MIND 边根据 `appearance_active_during` 和 `mind_active_during` 的事件重叠自动关联：若某个 mind 状态生效的事件集合与某个 appearance 状态有交集，则该 mind 挂在该 appearance 下。

这意味着：
1. **查询当前状态**的方式统一：找到 `*_active_during` 指向当前 Event 的 State
2. **生成参考图**的方式统一：Appearance 和 PropState 等都有 `reference_image` 字段
3. **角色查询**额外获取两层信息：Appearance（视觉参考图）+ Mind（表演指导）

---

## 6. 完整示例：小红帽

### 6.1 实体

```json
{
  "characters": [
    {
      "id": "char_red",
      "name": "小红帽",
      "fixed_traits": "7-8岁小女孩，圆脸，大眼睛，棕色卷发，身材娇小",
      "relationships": {
        "char_mother": [{"kind": "母女", "since": null}],
        "char_grandma": [{"kind": "祖孙", "since": null}],
        "char_wolf": [
          {"kind": "陌生人", "since": null},
          {"kind": "受骗者→欺骗者", "since": "evt_red_arrives"},
          {"kind": "猎物→捕食者", "since": "evt_wolf_eats_red"}
        ],
        "char_hunter": [
          {"kind": "陌生人", "since": null},
          {"kind": "被救者→救命恩人", "since": "evt_rescue"}
        ]
      }
    },
    {
      "id": "char_wolf",
      "name": "大灰狼",
      "fixed_traits": "体型巨大的灰狼，尖耳，长嘴，毛色深灰带黑",
      "relationships": {
        "char_grandma": [{"kind": "捕食者→猎物", "since": "evt_wolf_eats_grandma"}],
        "char_hunter": [{"kind": "猎物→天敌", "since": "evt_hunter_arrives"}]
      }
    },
    {
      "id": "char_grandma",
      "name": "外婆",
      "fixed_traits": "70多岁老妇人，白发，瘦小，面容慈祥"
    },
    {
      "id": "char_mother",
      "name": "妈妈",
      "fixed_traits": "30多岁女性，棕发，围着围裙，温柔但严肃"
    },
    {
      "id": "char_hunter",
      "name": "猎人",
      "fixed_traits": "中年壮汉，络腮胡，宽肩膀，皮肤粗糙"
    }
  ],

  "props": [
    {"id": "prop_basket", "name": "篮子", "fixed_traits": "藤编提篮，带布盖",
     "relationships": {
       "char_mother": [{"kind": "亲手准备的关爱", "since": null}],
       "char_red": [{"kind": "受托之物，责任", "since": "evt_farewell"}]
     }},
    {"id": "prop_hood", "name": "红色斗篷", "fixed_traits": "鲜红色丝绒连帽斗篷，到膝盖长度",
     "relationships": {
       "char_grandma": [{"kind": "亲手缝制的礼物", "since": null}],
       "char_red": [{"kind": "最珍爱的衣物，身份象征", "since": null}]
     }},
    {"id": "prop_axe", "name": "猎斧", "fixed_traits": "木柄铁刃手斧",
     "relationships": {
       "char_hunter": [{"kind": "随身工具，谋生手段", "since": null}]
     }},
    {"id": "prop_grandma_clothes", "name": "外婆的衣物", "fixed_traits": "白色睡帽，碎花睡衣，老花眼镜",
     "relationships": {
       "char_grandma": [{"kind": "贴身衣物", "since": null}],
       "char_wolf": [{"kind": "伪装工具", "since": "evt_wolf_disguise"}]
     }}
  ],

  "locations": [
    {"id": "loc_home", "name": "小红帽的家", "fixed_traits": "村边小木屋，篱笆院子，烟囱冒烟"},
    {"id": "loc_forest", "name": "森林", "fixed_traits": "茂密的欧洲针叶林，高大的松树和橡树"},
    {"id": "loc_grandma_house", "name": "外婆的小屋", "fixed_traits": "森林深处独立小木屋，石头烟囱，木门，窗台有花"}
  ]
}
```

### 6.2 事件 + 时序

```json
{
  "timelines": [
    {"id": "time_morning", "label": "清晨"},
    {"id": "time_midday", "label": "正午前后"},
    {"id": "time_afternoon", "label": "午后"}
  ],

  "events": [
    {"id": "evt_farewell", "description": "妈妈嘱咐小红帽给外婆送吃的，叮嘱不要离开大路",
     "happens_at": "loc_home", "happens_during": "time_morning"},

    {"id": "evt_forest_walk", "description": "小红帽独自走在森林小路上，好奇地东张西望",
     "happens_at": "loc_forest", "happens_during": "time_morning"},

    {"id": "evt_wolf_encounter", "description": "大灰狼从树后现身，假装友善地搭话，套出外婆住处",
     "happens_at": "loc_forest", "happens_during": "time_midday",
     "interactions": [
       {"between": ["char_red", "char_wolf"], "style": "狼蹲下平视小红帽，语气温柔；小红帽微微后退但仍回答"}
     ]},

    {"id": "evt_red_picks_flowers", "description": "小红帽被狼引诱去路边采野花，越走越深",
     "happens_at": "loc_forest", "happens_during": "time_midday"},

    {"id": "evt_wolf_runs_ahead", "description": "大灰狼抄近路飞奔向外婆家",
     "happens_at": "loc_forest", "happens_during": "time_midday"},

    {"id": "evt_wolf_eats_grandma", "description": "大灰狼闯入外婆家，吞掉外婆",
     "happens_at": "loc_grandma_house", "happens_during": "time_midday",
     "interactions": [
       {"between": ["char_wolf", "char_grandma"], "style": "狼破门而入，外婆惊恐后退缩在床角"}
     ]},

    {"id": "evt_wolf_disguise", "description": "大灰狼穿上外婆的衣物，戴上睡帽和眼镜，钻进被窝",
     "happens_at": "loc_grandma_house", "happens_during": "time_midday"},

    {"id": "evt_red_arrives", "description": "小红帽抱着花来到外婆家门前，敲门进入",
     "happens_at": "loc_grandma_house", "happens_during": "time_afternoon"},

    {"id": "evt_dialogue", "description": "经典对话：外婆你的眼睛/耳朵/嘴巴怎么这么大",
     "happens_at": "loc_grandma_house", "happens_during": "time_afternoon",
     "interactions": [
       {"between": ["char_red", "char_wolf"], "style": "小红帽站在床边观察，身体前倾；伪装的狼缩在被子里只露头"}
     ]},

    {"id": "evt_wolf_eats_red", "description": "大灰狼扑向小红帽，将她吞下",
     "happens_at": "loc_grandma_house", "happens_during": "time_afternoon",
     "interactions": [
       {"between": ["char_wolf", "char_red"], "style": "狼从床上弹起扑来，小红帽尖叫后退"}
     ]},

    {"id": "evt_hunter_arrives", "description": "猎人路过听到屋内异响，破门而入",
     "happens_at": "loc_grandma_house", "happens_during": "time_afternoon"},

    {"id": "evt_rescue", "description": "猎人用斧头剖开大灰狼的肚子，救出外婆和小红帽",
     "happens_at": "loc_grandma_house", "happens_during": "time_afternoon",
     "interactions": [
       {"between": ["char_hunter", "char_wolf"], "style": "猎人一斧制服，狼因吃太饱行动迟缓"},
       {"between": ["char_hunter", "char_red"], "style": "小红帽被拉出后抱住猎人哭泣"}
     ]},

    {"id": "evt_reunion", "description": "外婆和小红帽安然无恙，三人一起享用篮子里的食物",
     "happens_at": "loc_grandma_house", "happens_during": "time_afternoon"}
  ],

  "event_sequence": [
    {"from": "evt_farewell", "to": "evt_forest_walk", "type": "THEN"},
    {"from": "evt_forest_walk", "to": "evt_wolf_encounter", "type": "THEN"},
    {"from": "evt_wolf_encounter", "to": "evt_red_picks_flowers", "type": "THEN"},
    {"from": "evt_wolf_encounter", "to": "evt_wolf_runs_ahead", "type": "THEN"},
    {"from": "evt_red_picks_flowers", "to": "evt_wolf_runs_ahead", "type": "PARALLEL"},
    {"from": "evt_wolf_runs_ahead", "to": "evt_wolf_eats_grandma", "type": "THEN"},
    {"from": "evt_wolf_eats_grandma", "to": "evt_wolf_disguise", "type": "THEN"},
    {"from": "evt_red_picks_flowers", "to": "evt_red_arrives", "type": "THEN"},
    {"from": "evt_wolf_disguise", "to": "evt_red_arrives", "type": "THEN"},
    {"from": "evt_red_arrives", "to": "evt_dialogue", "type": "THEN"},
    {"from": "evt_dialogue", "to": "evt_wolf_eats_red", "type": "THEN"},
    {"from": "evt_wolf_eats_red", "to": "evt_hunter_arrives", "type": "THEN"},
    {"from": "evt_hunter_arrives", "to": "evt_rescue", "type": "THEN"},
    {"from": "evt_rescue", "to": "evt_reunion", "type": "THEN"}
  ]
}
```

**时序图：**

```
evt_farewell -> evt_forest_walk -> evt_wolf_encounter -+-> evt_red_picks_flowers ----+
                                                       |          (PARALLEL)         |
                                                       +-> evt_wolf_runs_ahead       |
                                                                   |                 |
                                                           evt_wolf_eats_grandma     |
                                                                   |                 |
                                                           evt_wolf_disguise         |
                                                                   |                 |
                                                                   +--------+--------+
                                                                            |
                                                                     evt_red_arrives
                                                                            |
                                                                      evt_dialogue
                                                                            |
                                                                    evt_wolf_eats_red
                                                                            |
                                                                    evt_hunter_arrives
                                                                            |
                                                                       evt_rescue
                                                                            |
                                                                      evt_reunion
```

### 6.3 角色状态

角色状态分为**外形（Appearance）**和**心态（Mind）**两层。

#### 外形状态

```json
{
  "character_appearances": [
    {"id": "appear_red_neat", "entity": "char_red", "phase": "整洁出行装",
     "visual": {"costume": "红色丝绒斗篷，白色连衣裙，棕色小皮靴", "hair": "棕色卷发散落在斗篷里", "physical": "健康，红润", "props": ["prop_hood", "prop_basket"]},
     "reference_image": null},
    {"id": "appear_red_disheveled", "entity": "char_red", "phase": "劫后狼狈",
     "based_on": "appear_red_neat",
     "visual": {"costume": "斗篷皱巴巴，裙子沾灰", "hair": "凌乱", "physical": "脸色苍白", "props": ["prop_hood"]},
     "reference_image": null},

    {"id": "appear_wolf_natural", "entity": "char_wolf", "phase": "灰狼原形",
     "visual": {"body": "深灰带黑毛色，尖耳长嘴", "physical": "毛发竖立，肌肉紧绷", "props": []},
     "reference_image": null},
    {"id": "appear_wolf_disguised", "entity": "char_wolf", "phase": "穿戴外婆衣物",
     "based_on": "appear_wolf_natural",
     "visual": {"body": "同上，但被衣物遮挡", "costume": "白色睡帽勉强套头，碎花睡衣撑裂，老花镜歪斜", "props": ["prop_grandma_clothes"]},
     "reference_image": null},
    {"id": "appear_wolf_exposed", "entity": "char_wolf", "phase": "衣物撕裂现原形",
     "based_on": "appear_wolf_natural",
     "visual": {"body": "灰狼原形完全暴露", "physical": "獠牙毕露，肚子被剖开（童话风格）", "props": []},
     "reference_image": null},

    {"id": "appear_grandma_normal", "entity": "char_grandma", "phase": "居家睡衣",
     "visual": {"costume": "碎花睡衣，白色睡帽，老花眼镜", "hair": "白发整齐", "physical": "瘦小", "props": ["prop_grandma_clothes"]},
     "reference_image": null},
    {"id": "appear_grandma_disheveled", "entity": "char_grandma", "phase": "被救后狼狈",
     "based_on": "appear_grandma_normal",
     "visual": {"costume": "睡衣皱巴巴", "hair": "白发散乱", "physical": "瘦小，虚弱"},
     "reference_image": null},

    {"id": "appear_mother_home", "entity": "char_mother", "phase": "居家装扮",
     "visual": {"costume": "蓝色连衣裙，白围裙", "hair": "棕发挽起"},
     "reference_image": null},

    {"id": "appear_hunter_gear", "entity": "char_hunter", "phase": "猎装",
     "visual": {"costume": "深绿色猎装，皮靴，皮带挂斧", "physical": "中年壮汉，络腮胡", "props": ["prop_axe"]},
     "reference_image": null}
  ],

  "appearance_active_during": {
    "appear_red_neat": ["evt_farewell", "evt_forest_walk", "evt_wolf_encounter", "evt_red_picks_flowers", "evt_red_arrives", "evt_dialogue", "evt_wolf_eats_red"],
    "appear_red_disheveled": ["evt_rescue", "evt_reunion"],
    "appear_wolf_natural": ["evt_wolf_encounter", "evt_wolf_runs_ahead", "evt_wolf_eats_grandma"],
    "appear_wolf_disguised": ["evt_wolf_disguise", "evt_red_arrives", "evt_dialogue"],
    "appear_wolf_exposed": ["evt_wolf_eats_red", "evt_rescue"],
    "appear_grandma_normal": ["evt_wolf_eats_grandma"],
    "appear_grandma_disheveled": ["evt_rescue", "evt_reunion"],
    "appear_mother_home": ["evt_farewell"],
    "appear_hunter_gear": ["evt_hunter_arrives", "evt_rescue", "evt_reunion"]
  },

  "appearance_transitions": [
    {"from": "appear_red_neat", "to": "appear_red_disheveled", "trigger": "evt_rescue",
     "delta": {"costume": "斗篷变皱沾灰", "hair": "整齐→凌乱"}},
    {"from": "appear_wolf_natural", "to": "appear_wolf_disguised", "trigger": "evt_wolf_disguise",
     "delta": {"+costume": "外婆衣物", "reason": "穿上睡帽睡衣眼镜"}},
    {"from": "appear_wolf_disguised", "to": "appear_wolf_exposed", "trigger": "evt_wolf_eats_red",
     "delta": {"-costume": "外婆衣物撕裂脱落"}},
    {"from": "appear_grandma_normal", "to": "appear_grandma_disheveled", "trigger": "evt_rescue",
     "delta": {"costume": "睡衣皱巴巴", "hair": "散乱"}}
  ]
}
```

注意小红帽从出门到被吞，外形一直是"整洁出行装"（同一个 `appear_red_neat` 节点）——多个事件没有外形变化时共享同一状态。

#### 心态状态

```json
{
  "character_minds": [
    {"id": "mind_red_innocent", "entity": "char_red", "phase": "天真无忧",
     "emotion": "开心，天真，对世界充满好奇", "behavior": "蹦蹦跳跳，东张西望，和陌生人也会友善交谈"},
    {"id": "mind_red_uneasy", "entity": "char_red", "phase": "困惑渐恐",
     "emotion": "隐约不安→困惑→恐惧，逐渐加深", "behavior": "皱眉观察，身体后退，声音变小"},
    {"id": "mind_red_relieved", "entity": "char_red", "phase": "劫后余生",
     "emotion": "惊魂未定但感到安全，含泪笑", "behavior": "抱住救命恩人，紧靠外婆"},

    {"id": "mind_wolf_cunning", "entity": "char_wolf", "phase": "狡猾隐忍",
     "emotion": "贪婪但克制，计划中", "behavior": "假装温和，套话，隐藏真实意图"},
    {"id": "mind_wolf_ferocious", "entity": "char_wolf", "phase": "凶残暴露",
     "emotion": "贪婪爆发，嗜血", "behavior": "奔跑扑咬，不再伪装"},

    {"id": "mind_grandma_frail", "entity": "char_grandma", "phase": "虚弱慈祥",
     "emotion": "身体虚弱但内心温暖", "behavior": "卧床，说话轻柔"},
    {"id": "mind_grandma_relieved", "entity": "char_grandma", "phase": "惊魂未定",
     "emotion": "后怕但感恩", "behavior": "紧握小红帽的手，微笑"},

    {"id": "mind_mother_caring", "entity": "char_mother", "phase": "慈爱叮嘱",
     "emotion": "慈爱，略带担忧", "behavior": "反复叮嘱，整理女儿衣领"},

    {"id": "mind_hunter_resolute", "entity": "char_hunter", "phase": "果敢正义",
     "emotion": "警觉，正义感驱动", "behavior": "果断行动，之后温和安抚"}
  ],

  "mind_active_during": {
    "mind_red_innocent": ["evt_farewell", "evt_forest_walk", "evt_wolf_encounter", "evt_red_picks_flowers"],
    "mind_red_uneasy": ["evt_red_arrives", "evt_dialogue", "evt_wolf_eats_red"],
    "mind_red_relieved": ["evt_rescue", "evt_reunion"],
    "mind_wolf_cunning": ["evt_wolf_encounter", "evt_wolf_disguise", "evt_red_arrives", "evt_dialogue"],
    "mind_wolf_ferocious": ["evt_wolf_runs_ahead", "evt_wolf_eats_grandma", "evt_wolf_eats_red", "evt_rescue"],
    "mind_grandma_frail": ["evt_wolf_eats_grandma"],
    "mind_grandma_relieved": ["evt_rescue", "evt_reunion"],
    "mind_mother_caring": ["evt_farewell"],
    "mind_hunter_resolute": ["evt_hunter_arrives", "evt_rescue", "evt_reunion"]
  },

  "mind_transitions": [
    {"from": "mind_red_innocent", "to": "mind_red_uneasy", "trigger": "evt_red_arrives",
     "delta": {"emotion": "天真→不安", "reason": "到外婆家发现气氛异常"}},
    {"from": "mind_red_uneasy", "to": "mind_red_relieved", "trigger": "evt_rescue",
     "delta": {"emotion": "恐惧→含泪释然"}},
    {"from": "mind_wolf_cunning", "to": "mind_wolf_ferocious", "trigger": "evt_wolf_runs_ahead",
     "delta": {"emotion": "隐忍→爆发", "reason": "套到信息后不再伪装"}},
    {"from": "mind_grandma_frail", "to": "mind_grandma_relieved", "trigger": "evt_rescue",
     "delta": {"emotion": "虚弱→感恩"}}
  ]
}
```

心态变化比外形更频繁。例如狼在外形从"灰狼原形"变为"穿戴外婆衣物"的过程中，心态则从"狡猾隐忍"在中途就切换到了"凶残暴露"（在奔跑吃外婆时）。两层状态独立演变，通过 `HAS_MIND` 边关联。

### 6.4 物品状态

只有物品本身外观变化才创建新状态。注意：猎斧没有状态节点（全程外观不变），"挂在腰间"vs"使用中"属于角色动作而非道具变化。斗篷也只有"完好"和"皱巴脏污"两个状态，"帽子戴在头上"vs"滑到背后"属于角色姿态。

```json
{
  "prop_states": [
    {"id": "pstate_basket_full", "entity": "prop_basket", "phase": "装满完好",
     "appearance": {"visual": "藤篮盖着红白格子布，鼓鼓的", "condition": "完好"}},
    {"id": "pstate_basket_spilled", "entity": "prop_basket", "phase": "倒翻散落",
     "based_on": "pstate_basket_full",
     "appearance": {"visual": "篮子倒在地板上，食物散落一地", "condition": "倒翻"}},
    {"id": "pstate_basket_open", "entity": "prop_basket", "phase": "打开摆盘",
     "based_on": "pstate_basket_full",
     "appearance": {"visual": "篮子放在桌上，食物整齐摆出", "condition": "打开"}},

    {"id": "pstate_hood_intact", "entity": "prop_hood", "phase": "完好整洁",
     "appearance": {"visual": "鲜红色丝绒斗篷，面料光滑", "condition": "完好"}},
    {"id": "pstate_hood_wrinkled", "entity": "prop_hood", "phase": "皱巴脏污",
     "based_on": "pstate_hood_intact",
     "appearance": {"visual": "斗篷皱巴巴，沾灰微脏", "condition": "皱褶"}},

    {"id": "pstate_gclothes_neat", "entity": "prop_grandma_clothes", "phase": "整洁",
     "appearance": {"visual": "白色睡帽+碎花睡衣+老花镜，干净整齐", "condition": "整洁"}},
    {"id": "pstate_gclothes_stretched", "entity": "prop_grandma_clothes", "phase": "撑变形",
     "based_on": "pstate_gclothes_neat",
     "appearance": {"visual": "睡帽勉强套在大头上，睡衣被撑得变形，眼镜歪斜", "condition": "不合身变形"}},
    {"id": "pstate_gclothes_torn", "entity": "prop_grandma_clothes", "phase": "撕碎",
     "based_on": "pstate_gclothes_stretched",
     "appearance": {"visual": "睡帽飞出，睡衣碎片散落", "condition": "破碎"}}
  ],

  "prop_active_during": {
    "pstate_basket_full": ["evt_farewell", "evt_forest_walk", "evt_wolf_encounter", "evt_red_picks_flowers", "evt_red_arrives", "evt_dialogue"],
    "pstate_basket_spilled": ["evt_wolf_eats_red", "evt_hunter_arrives", "evt_rescue"],
    "pstate_basket_open": ["evt_reunion"],
    "pstate_hood_intact": ["evt_farewell", "evt_forest_walk", "evt_wolf_encounter", "evt_red_picks_flowers", "evt_red_arrives", "evt_dialogue", "evt_wolf_eats_red"],
    "pstate_hood_wrinkled": ["evt_rescue", "evt_reunion"],
    "pstate_gclothes_neat": ["evt_wolf_eats_grandma"],
    "pstate_gclothes_stretched": ["evt_wolf_disguise", "evt_red_arrives", "evt_dialogue"],
    "pstate_gclothes_torn": ["evt_wolf_eats_red"]
  }
}
```

`based_on` 字段构成视觉衍生链。例如外婆衣物的链条：`gclothes_neat` → `gclothes_stretched` → `gclothes_torn`，生成系统可以用前一个状态的参考图作为起点做 image-to-image 变换。

### 6.5 环境状态

环境状态描述的是**物理环境本身的状态**（光照、陈设、破坏程度），而非叙事事件名（如"遇狼处"、"团圆"）。`phase` 用物理状态命名。

```json
{
  "location_states": [
    {"id": "lstate_home_morning", "entity": "loc_home", "phase": "晨光暖屋",
     "appearance": {"lighting": "清晨柔和阳光，金色侧逆光", "weather": "晴朗，薄雾", "condition": "整洁温馨，门前花园", "atmosphere": "温暖，安全"}},

    {"id": "lstate_forest_bright", "entity": "loc_forest", "phase": "阳光林间小路",
     "appearance": {"lighting": "丁达尔光束，光斑洒在小路上", "weather": "晴，微风", "condition": "野花，蝴蝶", "atmosphere": "童话美好"}},
    {"id": "lstate_forest_deep", "entity": "loc_forest", "phase": "幽深密林",
     "appearance": {"lighting": "树冠更密，斑驳光影，大片阴影", "weather": "云遮太阳，静，无风", "condition": "小路分岔，杂草+花丛", "atmosphere": "美丽与危险并存"}},

    {"id": "lstate_ghouse_tidy", "entity": "loc_grandma_house", "phase": "整洁温馨",
     "appearance": {"lighting": "午后柔和光线，壁炉微弱火光", "condition": "整洁，床铺整齐，桌上茶壶", "atmosphere": "温馨，安静"}},
    {"id": "lstate_ghouse_eerie", "entity": "loc_grandma_house", "phase": "昏暗异样",
     "appearance": {"lighting": "窗帘拉上，室内昏暗", "condition": "门虚掩，地上泥脚印，椅子碰歪", "atmosphere": "不对劲，过分安静"}},
    {"id": "lstate_ghouse_chaos", "entity": "loc_grandma_house", "phase": "凌乱破碎",
     "appearance": {"lighting": "窗帘被扯下，光线涌入", "condition": "被子掀翻，枕头破裂羽毛飞散", "atmosphere": "暴力爆发后的混乱"}},
    {"id": "lstate_ghouse_restored", "entity": "loc_grandma_house", "phase": "劫后归暖",
     "based_on": "lstate_ghouse_tidy",
     "appearance": {"lighting": "午后阳光完全照入，壁炉重新点燃", "condition": "简单收拾，仍有修补痕迹，桌上摆食物", "atmosphere": "劫后余生的安宁"}}
  ],

  "location_active_during": {
    "lstate_home_morning": ["evt_farewell"],
    "lstate_forest_bright": ["evt_forest_walk"],
    "lstate_forest_deep": ["evt_wolf_encounter", "evt_red_picks_flowers", "evt_wolf_runs_ahead"],
    "lstate_ghouse_tidy": ["evt_wolf_eats_grandma"],
    "lstate_ghouse_eerie": ["evt_wolf_disguise", "evt_red_arrives", "evt_dialogue"],
    "lstate_ghouse_chaos": ["evt_wolf_eats_red", "evt_hunter_arrives", "evt_rescue"],
    "lstate_ghouse_restored": ["evt_reunion"]
  }
}
```

注意：森林从 3 个状态合并为 2 个（"遇狼处"的视觉环境与"深处采花"几乎一致，合并为"幽深密林"）。外婆小屋的"劫后归暖"使用 `based_on: lstate_ghouse_tidy`，视觉上基于"整洁温馨"但增加了修补痕迹——不是创建一个全新状态，而是基于原始状态做微调。

### 6.6 镜头语言

`focus_on` 引用的是 Appearance / PropState / LocationState 的 ID（不是角色实体 ID），确保镜头生成时能直接查到对应的视觉参考图。

```json
{
  "camera_directives": [
    {"id": "cam_farewell", "for_event": "evt_farewell", "shots": [
      {"order": 1, "shot_type": "wide", "angle": "eye_level", "movement": "static",
       "focus_on": ["lstate_home_morning"], "content": "建立画面：晨光中的小木屋"},
      {"order": 2, "shot_type": "medium", "angle": "eye_level", "movement": "static",
       "focus_on": ["appear_mother_home", "appear_red_neat"], "content": "母女告别，妈妈递篮子"},
      {"order": 3, "shot_type": "medium", "angle": "low_angle", "movement": "slow_pull_out",
       "focus_on": ["appear_red_neat"], "content": "小红帽转身出发，渐渐变成风景中的小红点"}
    ]},

    {"id": "cam_forest_walk", "for_event": "evt_forest_walk", "shots": [
      {"order": 1, "shot_type": "extreme_wide", "angle": "high_angle", "movement": "crane_down",
       "focus_on": ["lstate_forest_bright", "appear_red_neat"], "content": "俯瞰：森林中的小路，一个红色小点"},
      {"order": 2, "shot_type": "medium", "angle": "eye_level", "movement": "tracking",
       "focus_on": ["appear_red_neat"], "content": "跟拍小红帽，阳光斑驳，蝴蝶飞过"}
    ]},

    {"id": "cam_wolf_encounter", "for_event": "evt_wolf_encounter", "shots": [
      {"order": 1, "shot_type": "medium", "angle": "eye_level", "movement": "static",
       "focus_on": ["appear_red_neat"], "content": "小红帽停步，感觉有什么在看她"},
      {"order": 2, "shot_type": "close_up", "angle": "low_angle", "movement": "slow_push_in",
       "focus_on": ["appear_wolf_natural"], "content": "狼从阴影现身，仰拍显得更大"},
      {"order": 3, "shot_type": "over_shoulder", "angle": "eye_level", "movement": "static",
       "focus_on": ["appear_red_neat", "appear_wolf_natural"], "content": "从小红帽身后看狼"},
      {"order": 4, "shot_type": "detail_insert", "angle": "close_up", "movement": "static",
       "focus_on": ["appear_wolf_natural"], "content": "特写：狼的爪子微微抓紧"}
    ]},

    {"id": "cam_parallel", "for_event": ["evt_red_picks_flowers", "evt_wolf_runs_ahead"], "shots": [
      {"order": 1, "shot_type": "medium", "angle": "eye_level", "movement": "static",
       "focus_on": ["appear_red_neat", "lstate_forest_deep"], "content": "小红帽蹲下采花"},
      {"order": 2, "shot_type": "wide", "angle": "low_angle", "movement": "fast_tracking",
       "focus_on": ["appear_wolf_natural"], "content": "[切] 狼飞奔穿过黑暗林间"},
      {"order": 3, "shot_type": "close_up", "angle": "eye_level", "movement": "static",
       "focus_on": ["appear_red_neat"], "content": "[切回] 小红帽闻花微笑"},
      {"order": 4, "shot_type": "medium", "angle": "eye_level", "movement": "push_in",
       "focus_on": ["appear_wolf_natural", "loc_grandma_house"], "content": "[切] 狼到达外婆家门前"}
    ]},

    {"id": "cam_dialogue", "for_event": "evt_dialogue", "shots": [
      {"order": 1, "shot_type": "medium", "angle": "eye_level", "movement": "slow_push_in",
       "focus_on": ["appear_red_neat", "appear_wolf_disguised"], "content": "对话全景，每问一句推近一点"},
      {"order": 2, "shot_type": "extreme_close", "angle": "eye_level", "movement": "static",
       "focus_on": ["appear_wolf_disguised"], "content": "极近特写：大眼睛"},
      {"order": 3, "shot_type": "extreme_close", "angle": "eye_level", "movement": "static",
       "focus_on": ["appear_wolf_disguised"], "content": "极近特写：大耳朵"},
      {"order": 4, "shot_type": "extreme_close", "angle": "low_angle", "movement": "slow_push_in",
       "focus_on": ["appear_wolf_disguised"], "content": "极近特写：大嘴巴"},
      {"order": 5, "shot_type": "close_up", "angle": "high_angle", "movement": "static",
       "focus_on": ["appear_red_neat"], "content": "小红帽的脸：困惑变为恐惧"}
    ]},

    {"id": "cam_wolf_attack", "for_event": "evt_wolf_eats_red", "shots": [
      {"order": 1, "shot_type": "wide", "angle": "dutch_angle", "movement": "handheld_shake",
       "focus_on": ["appear_wolf_exposed", "appear_red_neat"], "content": "狼弹起，倾斜构图"},
      {"order": 2, "shot_type": "detail_insert", "angle": "eye_level", "movement": "static",
       "focus_on": ["pstate_basket_spilled", "pstate_gclothes_torn"], "content": "篮子掉地、衣物碎片"}
    ]},

    {"id": "cam_rescue", "for_event": ["evt_hunter_arrives", "evt_rescue"], "shots": [
      {"order": 1, "shot_type": "medium", "angle": "low_angle", "movement": "push_in",
       "focus_on": ["appear_hunter_gear"], "content": "仰拍猎人踹门"},
      {"order": 2, "shot_type": "detail_insert", "angle": "close_up", "movement": "static",
       "focus_on": ["prop_axe"], "content": "斧头举起特写"},
      {"order": 3, "shot_type": "medium", "angle": "eye_level", "movement": "static",
       "focus_on": ["appear_red_disheveled", "appear_grandma_disheveled"], "content": "祖孙被救出，相拥"}
    ]},

    {"id": "cam_reunion", "for_event": "evt_reunion", "shots": [
      {"order": 1, "shot_type": "medium", "angle": "eye_level", "movement": "slow_360_orbit",
       "focus_on": ["appear_red_disheveled", "appear_grandma_disheveled", "appear_hunter_gear", "pstate_basket_open", "lstate_ghouse_restored"],
       "content": "环绕三人围坐吃东西"},
      {"order": 2, "shot_type": "extreme_wide", "angle": "high_angle", "movement": "slow_pull_out",
       "focus_on": ["loc_grandma_house"], "content": "最终镜头：缓缓拉远，炊烟升起"}
    ]}
  ]
}
```

### 6.7 音频

```json
{
  "audio_layers": [
    {"id": "audio_bgm", "kind": "bgm"},
    {"id": "audio_ambience", "kind": "ambience"},
    {"id": "audio_dialogue", "kind": "dialogue"}
  ],

  "audio_states": [
    {"id": "astate_bgm_pastoral", "layer": "audio_bgm", "phase": "田园・出发",
     "style": "轻快木吉他指弹+竖笛，欧洲民谣风", "tempo": "moderate", "intensity": "light",
     "instruments": ["木吉他", "竖笛", "手铃"],
     "music_prompt": "Light acoustic guitar fingerpicking, recorder melody, European folk, warm and innocent, 100 BPM"},

    {"id": "astate_bgm_uneasy", "layer": "audio_bgm", "phase": "遇狼・不安",
     "style": "吉他不协和拨弦，加入低沉大提琴", "tempo": "slowing", "intensity": "medium",
     "instruments": ["木吉他（不协和）", "大提琴", "定音鼓（极远）"],
     "music_prompt": "Acoustic guitar dissonant, cello low drone, distant timpani, tension building, 80 BPM"},

    {"id": "astate_bgm_split", "layer": "audio_bgm", "phase": "交叉剪辑・双线",
     "style": "两主题交替：竖笛（变调）+ 急促弦乐", "tempo": "alternating", "intensity": "building",
     "instruments": ["竖笛（变调）", "急促弦乐", "心跳低鼓"],
     "music_prompt": "Alternating innocent recorder (off-key) and urgent staccato strings, heartbeat bass drum, 120 BPM accelerating"},

    {"id": "astate_bgm_suspense", "layer": "audio_bgm", "phase": "外婆家・悬疑",
     "style": "无旋律，持续低音+尖锐高音滑奏", "tempo": "very_slow", "intensity": "high_tension",
     "instruments": ["持续低音", "小提琴泛音", "玻璃琴"],
     "music_prompt": "Sustained bass drone, violin harmonics, glass armonica, pure suspense, 60 BPM"},

    {"id": "astate_bgm_explosion", "layer": "audio_bgm", "phase": "袭击・爆发",
     "style": "全奏冲击后迅速消失", "tempo": "burst", "intensity": "maximum",
     "instruments": ["铜管齐奏", "定音鼓", "弦乐下行"],
     "music_prompt": "Sudden full orchestra hit, brass blast, timpani crash, then abrupt silence"},

    {"id": "astate_bgm_hero", "layer": "audio_bgm", "phase": "猎人・救援",
     "style": "铜管英雄主题", "tempo": "march", "intensity": "strong",
     "instruments": ["圆号", "小军鼓", "弦乐"],
     "music_prompt": "Heroic French horn theme, snare drum march, brave and decisive, 110 BPM"},

    {"id": "astate_bgm_reunion", "layer": "audio_bgm", "phase": "团圆・回归",
     "style": "开头主题回归，更丰满，加弦乐", "tempo": "moderate", "intensity": "warm",
     "instruments": ["木吉他", "竖笛", "弦乐", "手铃"],
     "music_prompt": "Return of opening folk theme, now with warm string quartet, fuller and grateful, 100 BPM"},

    {"id": "astate_amb_village", "layer": "audio_ambience", "phase": "村庄清晨",
     "style": "远处公鸡，鸟鸣，微风"},
    {"id": "astate_amb_forest_alive", "layer": "audio_ambience", "phase": "森林生机",
     "style": "密集鸟鸣，树叶沙沙，小溪，脚步踩落叶"},
    {"id": "astate_amb_forest_quiet", "layer": "audio_ambience", "phase": "鸟鸣停止",
     "style": "鸟鸣减少，风声变大，远处树枝折断"},
    {"id": "astate_amb_running", "layer": "audio_ambience", "phase": "狼奔跑",
     "style": "急促爪子踏地，树枝撞断，喘息"},
    {"id": "astate_amb_house_creak", "layer": "audio_ambience", "phase": "诡异安静",
     "style": "木地板嘎吱，钟摆滴答，窗外乌鸦"},
    {"id": "astate_amb_aftermath", "layer": "audio_ambience", "phase": "团圆",
     "style": "壁炉噼啪，茶杯碰碟，窗外鸟鸣恢复"},

    {"id": "astate_dial_mother_warn", "layer": "audio_dialogue", "speaker": "char_mother",
     "text": "乖女儿，把这些点心和酒给外婆送去。记住，走大路，不要跑到森林里去。",
     "tone": "温柔但认真", "voice_direction": "warm, gentle but firm, motherly"},
    {"id": "astate_dial_red_ok", "layer": "audio_dialogue", "speaker": "char_red",
     "text": "好的妈妈，我会乖乖的！",
     "tone": "天真欢快", "voice_direction": "child voice, cheerful, innocent"},
    {"id": "astate_dial_wolf_hello", "layer": "audio_dialogue", "speaker": "char_wolf",
     "text": "你好啊，小姑娘。这么好的天气，你要去哪里呀？",
     "tone": "故作温柔，低沉压迫", "voice_direction": "deep voice pretending gentle, unsettling"},
    {"id": "astate_dial_red_naive", "layer": "audio_dialogue", "speaker": "char_red",
     "text": "我去看外婆，她生病了。她住在森林那头的小房子里。",
     "tone": "毫无防备", "voice_direction": "child voice, trusting, naive"},
    {"id": "astate_dial_eyes", "layer": "audio_dialogue", "speaker": "char_red",
     "text": "外婆，你的眼睛怎么这么大呀？",
     "tone": "困惑微不安", "voice_direction": "child, puzzled, slightly nervous"},
    {"id": "astate_dial_wolf_eyes", "layer": "audio_dialogue", "speaker": "char_wolf",
     "text": "为了更好地看清你呀，亲爱的。",
     "tone": "压嗓装老太太", "voice_direction": "strained grandma voice, greedy undertone"},
    {"id": "astate_dial_ears", "layer": "audio_dialogue", "speaker": "char_red",
     "text": "外婆，你的耳朵怎么这么大呀？",
     "tone": "不安加深", "voice_direction": "child, more nervous"},
    {"id": "astate_dial_wolf_ears", "layer": "audio_dialogue", "speaker": "char_wolf",
     "text": "为了更好地听到你呀，亲爱的。",
     "tone": "越来越难掩饰", "voice_direction": "barely maintaining grandma voice"},
    {"id": "astate_dial_mouth", "layer": "audio_dialogue", "speaker": "char_red",
     "text": "外婆……你的嘴巴……怎么这么大呀……？",
     "tone": "恐惧，声音发抖", "voice_direction": "trembling, terrified, whisper-like"},
    {"id": "astate_dial_wolf_mouth", "layer": "audio_dialogue", "speaker": "char_wolf",
     "text": "为了——一口把你吃掉！！",
     "tone": "撕下伪装，咆哮", "voice_direction": "drops pretense, roaring, explosive, animalistic snarl"}
  ],

  "audio_active_during": {
    "astate_bgm_pastoral": ["evt_farewell", "evt_forest_walk"],
    "astate_bgm_uneasy": ["evt_wolf_encounter"],
    "astate_bgm_split": ["evt_red_picks_flowers", "evt_wolf_runs_ahead", "evt_wolf_eats_grandma"],
    "astate_bgm_suspense": ["evt_wolf_disguise", "evt_red_arrives", "evt_dialogue"],
    "astate_bgm_explosion": ["evt_wolf_eats_red"],
    "astate_bgm_hero": ["evt_hunter_arrives", "evt_rescue"],
    "astate_bgm_reunion": ["evt_reunion"],
    "astate_amb_village": ["evt_farewell"],
    "astate_amb_forest_alive": ["evt_forest_walk"],
    "astate_amb_forest_quiet": ["evt_wolf_encounter"],
    "astate_amb_running": ["evt_wolf_runs_ahead"],
    "astate_amb_house_creak": ["evt_red_arrives", "evt_dialogue"],
    "astate_amb_aftermath": ["evt_reunion"],
    "astate_dial_mother_warn": ["evt_farewell"],
    "astate_dial_red_ok": ["evt_farewell"],
    "astate_dial_wolf_hello": ["evt_wolf_encounter"],
    "astate_dial_red_naive": ["evt_wolf_encounter"],
    "astate_dial_eyes": ["evt_dialogue"],
    "astate_dial_wolf_eyes": ["evt_dialogue"],
    "astate_dial_ears": ["evt_dialogue"],
    "astate_dial_wolf_ears": ["evt_dialogue"],
    "astate_dial_mouth": ["evt_dialogue"],
    "astate_dial_wolf_mouth": ["evt_dialogue"]
  },

  "audio_transitions": [
    {"from": "astate_bgm_pastoral", "to": "astate_bgm_uneasy", "trigger": "evt_wolf_encounter", "method": "crossfade_3s"},
    {"from": "astate_bgm_uneasy", "to": "astate_bgm_split", "trigger": "evt_red_picks_flowers", "method": "crossfade_2s"},
    {"from": "astate_bgm_split", "to": "astate_bgm_suspense", "trigger": "evt_red_arrives", "method": "fade_out_3s"},
    {"from": "astate_bgm_suspense", "to": "astate_bgm_explosion", "trigger": "evt_wolf_eats_red", "method": "hard_cut"},
    {"from": "astate_bgm_explosion", "to": "astate_bgm_hero", "trigger": "evt_hunter_arrives", "method": "stinger"},
    {"from": "astate_bgm_hero", "to": "astate_bgm_reunion", "trigger": "evt_reunion", "method": "crossfade_4s"}
  ]
}
```

**BGM 情绪弧线：**

```
Intensity
  ^
  |          /\ cross-cut         ## explosion
  |  pastoral /  \ alternating  suspense ##
  | ~~~     /    \ /\ /\      ........  ##
  |    ~~~ /      X  X  \   ..      .. ##   hero      pastoral return
  | ~~~~~~/      / \/ \  \ .         .##  ^^^^^^^^   ~~~~~~~~~~~~~~~
  +--------------------------------------------------------------------> Time
  farewell forest wolf   flowers/ grandma-house    attack hunter reunion
                  meet   wolf-runs    dialogue
```

---

## 7. 查询接口

Linearizer 或 Agent 在生成某个 Event 的镜头时，需要执行以下查询：

### 7.1 获取事件的完整上下文

```
query_event_context(event_id) -> {
    event:        Event,
    characters:   [{character, appearance, mind, relationship_to_others}],
    props:        [{prop, state}],
    location:     {location, state},
    timeline:     TimeLine,
    interactions: [{between, style}],
    camera:       CameraDirective,
    audio:        {bgm: AudioState, ambience: AudioState, dialogue: [AudioState]},
    prev_events:  [Event],       // THEN 边的前驱
    next_events:  [Event],       // THEN 边的后继
    parallel:     [Event]        // PARALLEL 边
}
```

### 7.2 获取角色当前关系

```
query_relationship(char_a, char_b, current_event) -> {
    kind: string   // 在 event_sequence 中，最后一个 since <= current_event 的关系
}
```

### 7.3 获取连续性信息（用于决定 Technique A/B/C）

```
query_continuity(current_event, prev_event) -> {
    same_location:       bool,    // 是否同一 Location
    shared_characters:   [char],  // 两个事件共有的角色
    shared_props:        [prop],  // 两个事件共有的道具
    location_changed:    bool,    // LocationState 是否变了
    recommend_technique: {A: bool, B: bool, C: bool}
}
```

自动推导规则（与现有 video-creator 的 Consistency Toolkit 对齐）：

| 条件 | 推荐 |
|------|------|
| 有角色 | A（传角色参考图） |
| 与上一事件同 Location 且 THEN 连接 | C（尾帧接续） |
| 角色特写 / 多角色同框 / `shot_type` 为 close_up | B（首帧图生视频） |
| 有重复出现的环境 | A（传环境参考图） |

---

## 8. 数据规模参考

以《小红帽》为例：

| 类型 | 数量 |
|------|------|
| Character | 5 |
| CharacterAppearance | 9 |
| CharacterMind | 9 |
| Prop | 4 |
| PropState | 8 |
| Location | 3 |
| LocationState | 7 |
| Event | 13 |
| TimeLine | 3 |
| CameraDirective | 8（含 23 个 shot） |
| AudioState | 7 bgm |
| Event edges (THEN/PARALLEL) | 14 |
| **总节点** | **约 76** |
| **总边** | **约 140** |

---

## 9. 待设计

- [ ] **Linearizer**：graph -> shot sequence 的转换逻辑，核心问题包括 PARALLEL 边的交叉剪辑策略、shot 排序、时长分配
- [ ] **Graph 构建流程**：LLM 如何从用户描述逐步构建 story graph（一次性 vs 分阶段）
- [ ] **增量编辑**：用户修改故事后如何局部更新 graph（而非重建）
- [ ] **与现有 video-creator 的集成**：graph 如何替代 script.json + storyboard.json
