# Generation Strategy Guide

本文件指导你如何为每个 shot 决定生成方式和参考图选择。**开始视频生成前必读。**

---

## 核心原则

1. **每个 shot 是一次独立的 GenerateVideoSync 调用。**
2. **模型能从输入图片里"看到"谁，就能保持谁的一致性。** 首帧图里的角色能保持一致；首帧里没有的角色需要参考图模式。

---

## 决策总览

先看全貌，再走流程。

| 场景 | 生成方式 | 关键参数 |
|---|---|---|
| `is_continuation: true` | `image_to_video` | `reference_image_path` = 前一 part 尾帧 |
| `prev_shot_in_sequence` 存在 + 机位不变 | `image_to_video` | `reference_image_path` = 前一 shot 尾帧 |
| `prev_shot_in_sequence` 存在 + 机位改变 | 走 Step 3 判断 | 前一 shot 尾帧加入 `reference_images` |
| 所有角色首帧可见 + 需要构图控制 | `image_to_video` | `reference_image_path` = 生成的首帧图，可附加 `reference_images` |
| 有角色首帧不可见 / 运动为主 | `reference_to_video` | `reference_images` = 角色参考图列表 |
| 无参考图可用 | `text_to_video` | 仅 prompt |

---

## 决策流程

对每个 shot，按以下顺序推理：

### Step 1: 判断谁出镜

从 `focus_on` 和 `prompt_materials` 确定画面中有哪些角色和环境。

- `focus_on` 中的 appearance state → 角色出镜
- `focus_on` 中的 location state → 环境出镜
- `prompt_materials.minds[].behavior` → 角色在做什么

### Step 2: 尾帧接续（三种情况，互斥，按优先级匹配）

检查当前 shot 是否需要接续前一个 shot 的尾帧。**命中任一条则确定生成方式，跳到 Step 4。**

#### 2a. Duration-split 接续

**条件**：`is_continuation: true`

当前 shot 是同一镜头因时长超限被拆分的后续部分。从 `prev_shot.output_path` 提取尾帧，用 `image_to_video`。

#### 2b. 叙事连续接续

**条件**：`prev_shot_in_sequence` 不为 null

Screenwriter 标注了这两个事件在叙事时间和空间上连续（`continuous: true`）。从 `prev_shot_in_sequence.output_path` 提取尾帧，然后根据机位变化选择策略：

- **机位不变**（当前 shot 的 shot_type 和 angle 与前一 shot 相同）：用尾帧做 `image_to_video` 的 `reference_image_path`。→ 跳到 Step 4。
- **机位改变**（shot_type 或 angle 不同）：把尾帧加入 `reference_images`（参考用，不做主图），继续走 Step 3 判断生成方式。

#### 2c. 尾帧参考（跨场景空间衔接）

**条件**：未命中 2a/2b，且场景有空间连续性（如角色跨场景移动：森林出口 → 小屋门口）。

这不是强制接续，而是**可选的参考图补充**。将前一 shot 的尾帧加入 `reference_images`（不是 `reference_image_path`，不改变生成模式），继续走 Step 3-4。

| 用 | 不用 |
|---|------|
| 角色跨场景移动（森林→小屋） | 无共同角色的跳切 |
| 场景有物理连续性（门内→门外） | 闪回、完全无关的场景切换 |

用时：尾帧占 `reference_images` 一个名额（上限 4 张），优先保角色参考图。当前 shot 必须等前一 shot 完成。

**三种情况都不命中**：跳过，直接进 Step 3。

### Step 3: 判断首帧可行性

**核心问题：首帧能否包含所有出镜角色的视觉身份信息？**

**适合首帧（→ `image_to_video`）**：
- 所有角色在视频开头就在画面中，正面/侧面可辨认
- 无大幅运动（非 tracking、非奔跑/跳跃）

**不适合首帧（→ `reference_to_video`）**：
- 有角色中途出场（如"从树后走出"）
- 角色背对镜头或被遮挡
- 大幅运动（tracking + 蹦跳/奔跑）

### Step 4: 选择参考图

- `focus_on` 中每个 appearance state ID → 从 story-graph.json 的 `character_appearances` 中查找对应节点的 `reference_image`
- 环境参考图 → 从 story-graph.json 的 `location_states` 中按 ID 查找 `reference_image`
- 上限 4 张，超出时优先保角色

---

## 并行规则

- 无依赖的 shot 可并行
- 2a（`is_continuation`）和 2b（`prev_shot_in_sequence`）必须等前一 shot 完成
- 2c 用了尾帧参考时必须等前一 shot 完成；不用时可并行

---

## 示例

### 双人对话（reference_to_video）

```json
{
  "shot_type": "medium", "content": "两人对峙",
  "focus_on": ["appear_red_neat", "appear_wolf_natural"],
  "is_continuation": false,
  "prompt_materials": {
    "minds": [
      {"entity": "char_red", "behavior": "停下脚步"},
      {"entity": "char_wolf", "behavior": "缓缓走出，弓着身体"}
    ]
  }
}
```

推理：狼"缓缓走出"→ 开头不完全可见 → 不适合首帧 → `reference_to_video`，传入两张角色参考图。

### 运动镜头（reference_to_video）

```json
{
  "shot_type": "wide", "movement": "fast_tracking",
  "focus_on": ["appear_wolf_natural"],
  "is_continuation": false,
  "prompt_materials": {
    "minds": [{"entity": "char_wolf", "behavior": "全速奔跑"}]
  }
}
```

推理：fast_tracking + 全速奔跑 → 大幅运动 → `reference_to_video`。

### Duration-split 接续（image_to_video）

```json
{
  "shot_id": "evt_forest_walk_shot_1_part_2",
  "is_continuation": true,
  "prev_shot": {"output_path": "{project_dir}/assets/shots/evt_forest_walk_shot_1_part_1.mp4"}
}
```

推理：`is_continuation: true` → 提取尾帧 → `image_to_video`。

---

## 常见陷阱

1. **跨 shot 尾帧接续只在 `prev_shot_in_sequence` 存在时使用。** 没有该字段的 shot 不做 2b 接续。
2. **已用首帧/尾帧（image_to_video）时，额外传参考图收益有限。** 画面身份已锚定。
3. **运动幅度大的镜头慎用首帧。** 首帧约束起始构图，大幅运动会不自然。
4. **不要因为一次失败就放弃某种策略。** 每个 shot 独立决策。
