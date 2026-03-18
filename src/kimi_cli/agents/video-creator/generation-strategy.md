# Generation Strategy Guide (Phase 3)

Phase 3 开始前请阅读。本文件指导你如何根据每个 shot 的素材清单，决定生成方式和参考图选择。

**核心原则：每个 shot 是一次独立的 GenerateVideoSync 调用。** Shot 之间不做尾帧接续。尾帧接续仅在同一个 shot 因时长超限被拆分成多个 part 时使用（`is_continuation: true`）。

**模型能从输入图片里"看到"谁，就能保持谁的一致性。** 首帧图里出现的角色，后续视频能保持一致；首帧里没有的角色，模型没有视觉锚点，一致性无法保证。参考图模式下，模型全程持有角色参考，无论角色何时出场都能保持一致。

---

## 决策流程

对每个 shot，按以下顺序推理：

### Step 1: 判断谁出镜

从 `focus_on` 和 `prompt_materials` 确定这个镜头里有哪些人物和环境。

- `focus_on` 中的 appearance state → 该角色在画面中出现
- `focus_on` 中的 location state → 该环境在画面中出现
- `prompt_materials.minds[].behavior` → 补充理解角色在做什么

### Step 2: 判断人物在首帧和视频过程中的状态

这一步决定**首帧图生成是否可行**。关键问题：首帧能否包含整个片段所需的全部视觉身份信息？

**适合首帧图生成的情况：**
- 所有出镜角色在视频开头就在画面中
- 角色正面或侧面面对镜头（身份可辨认）
- 视频过程中角色外观变化不大（没有转身、没有剧烈形变）

**不适合首帧图生成的情况：**
- 有角色在视频中途才出场（如"大灰狼从树后走出"——狼在开头不在画面中）
- 角色背对镜头或被遮挡（身份信息不足）
- 视频过程中有新角色进入画面

<example>
适合首帧：
```json
{
  "shot_type": "medium",
  "intent": "两人对峙",
  "focus_on": ["appear_red_neat", "appear_wolf_natural"],
  "prompt_materials": {
    "event_description": "小红帽和大灰狼面对面站在林间小路上",
    "minds": [
      {"entity": "char_red", "behavior": "停下脚步，侧头倾听"},
      {"entity": "char_wolf", "behavior": "弓着身体显得矮小"}
    ]
  }
}
```
→ 两个角色从一开始就在画面中，面对面站着，身份可辨认。生成一张首帧图定义站位和构图，视频展现对话过程。
</example>

<example>
不适合首帧：
```json
{
  "shot_type": "medium",
  "movement": "push_in",
  "intent": "狼从树后走出",
  "focus_on": ["appear_red_neat", "appear_wolf_natural"],
  "prompt_materials": {
    "event_description": "大灰狼从树后现身，假装友善地搭话",
    "minds": [
      {"entity": "char_red", "behavior": "停下脚步"},
      {"entity": "char_wolf", "behavior": "缓缓走出树后"}
    ]
  }
}
```
→ 狼在视频开头在树后面，首帧里看不到狼。必须用参考图模式，让模型全程持有狼的参考。
</example>

<example>
不适合首帧：
```json
{
  "shot_type": "wide",
  "movement": "tracking",
  "intent": "小红帽走在林间小路",
  "focus_on": ["appear_red_neat"],
  "prompt_materials": {
    "minds": [{"entity": "char_red", "behavior": "蹦蹦跳跳，东张西望"}]
  }
}
```
→ tracking + 蹦跳意味着大幅运动和位置变化。首帧会约束起始构图，限制运动自由度。用参考图模式更好。
</example>

### Step 3: 处理 continuation（仅限 `is_continuation: true` 的 shot）

如果当前 shot 的 `is_continuation` 为 `true`，说明它是同一个摄影镜头被拆分后的后续部分。此时：

1. 从 `prev_shot.output_path` 提取尾帧
2. 用尾帧作为当前 shot 的首帧（`image_to_video`）
3. 这是**唯一**需要尾帧接续的场景

如果 `is_continuation` 为 `false`，跳过此步骤。**不同 shot 之间不做尾帧接续。**

### Step 4: 选择参考图

从 `prompt_materials` 中选择传给生成 API 的参考图。

**基本规则：**
- `focus_on` 中的每个角色 → 用其 appearance state 的 `reference_image`（比 entity 级的图更具体，包含当前装扮）
- 如果 appearance state 没有 `reference_image`，退回使用 `entity_reference_image`
- 环境参考图（location state）→ 当场景氛围对画面重要时传入
- 参考图数量上限通常为 4 张 → 超出时优先保角色

**状态图 vs 实体图：**
- 角色有特定装扮变化（如"逃跑后凌乱"）→ 用状态图
- 角色装扮与实体默认一致 → 状态图和实体图效果相同

### Step 5: 确定生成方式

综合前几步的判断，选择 GenerateVideoSync 的参数：

| 判断结果 | 生成方式 | 关键参数 |
|---|---|---|
| `is_continuation: true` | `image_to_video` | `reference_image_path` = 前一 part 尾帧 |
| 所有角色首帧可见 + 需要构图控制 | `image_to_video` | `reference_image_path` = 生成的首帧图 |
| 有角色首帧不可见 / 运动为主 | `text_to_video` + `reference_images` | `reference_images` = 角色参考图列表 |
| 无参考图可用 | `text_to_video` | 仅 prompt |

---

## 决策示例

### 示例 1：双人对话镜头

```json
{
  "shot_id": "evt_wolf_encounter_shot_1",
  "shot_type": "medium",
  "angle": "eye_level",
  "movement": "",
  "intent": "两人对峙",
  "focus_on": ["appear_red_neat", "appear_wolf_natural"],
  "is_continuation": false,
  "prompt_materials": {
    "event_description": "大灰狼假装友善地搭话",
    "appearances": [
      {"id": "appear_red_neat", "reference_image": "assets/images/appear_red_neat.png"},
      {"id": "appear_wolf_natural", "reference_image": "assets/images/appear_wolf_natural.png"}
    ],
    "minds": [
      {"entity": "char_red", "behavior": "停下脚步，侧头倾听"},
      {"entity": "char_wolf", "behavior": "缓缓走出，弓着身体显得矮小"}
    ]
  }
}
```

**推理：**
1. 出镜：小红帽、大灰狼
2. 狼是"缓缓走出"——狼可能在视频开头不完全可见 → 不适合首帧
3. `is_continuation: false` → 无需尾帧接续
4. 参考图：appear_red_neat.png + appear_wolf_natural.png
5. **决策：`text_to_video` + `reference_images`**

### 示例 2：运动镜头

```json
{
  "shot_id": "evt_wolf_runs_shot_1",
  "shot_type": "wide",
  "angle": "eye_level",
  "movement": "fast_tracking",
  "intent": "狼飞奔",
  "focus_on": ["appear_wolf_natural"],
  "is_continuation": false,
  "prompt_materials": {
    "appearances": [
      {"id": "appear_wolf_natural", "reference_image": "assets/images/appear_wolf_natural.png"}
    ],
    "minds": [{"entity": "char_wolf", "behavior": "四肢着地全速奔跑"}]
  }
}
```

**推理：**
1. 出镜：只有狼
2. fast_tracking + 全速奔跑 → 大幅位移，不适合首帧
3. `is_continuation: false` → 无需尾帧接续
4. 参考图：appear_wolf_natural.png
5. **决策：`text_to_video` + `reference_images`**

### 示例 3：duration-split continuation

```json
{
  "shot_id": "evt_forest_walk_shot_1_part_2",
  "is_continuation": true,
  "prev_shot": {
    "shot_id": "evt_forest_walk_shot_1_part_1",
    "output_path": "assets/shots/evt_forest_walk_shot_1_part_1.mp4"
  },
  "duration_seconds": 5.0,
  "prompt_materials": { ... }
}
```

**推理：**
1. `is_continuation: true` → 这是同一镜头的后续部分
2. 从 `prev_shot.output_path` 提取尾帧
3. **决策：`image_to_video`**，`reference_image_path` = 尾帧路径

---

## 常见陷阱

1. **不要在不同 shot 之间做尾帧接续。** 每个 shot 是独立的摄影镜头，有自己的构图和角度。尾帧接续仅用于 `is_continuation: true` 的 duration-split 场景。
2. **不要因为有参考图就一定传入。** 如果已经用了首帧图（image_to_video），首帧里角色身份已经锚定，额外传参考图的收益有限。
3. **运动幅度大的镜头慎用首帧。** 首帧约束了起始构图和姿态，大幅运动（奔跑、跳跃、转身）会显得不自然。
4. **不要因为一次失败就放弃某种策略。** 每个 shot 独立决策。
