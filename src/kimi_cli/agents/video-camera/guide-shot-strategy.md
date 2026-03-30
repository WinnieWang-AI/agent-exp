# 生成模式决策树

> 每个 shot 生成前，用本文件的决策流程确定生成模式和参考图选择。

## 核心原则

1. **每个 shot 是一次独立的 GenerateVideoSync 调用。**
2. **模型能从输入图片里"看到"谁，就能保持谁的一致性。** 首帧/参考图里出现的角色能保持一致，没出现的无法保证。

## 决策总览

| 场景 | 生成方式 | 关键参数 |
|---|---|---|
| 同 event 内非首 shot（尾帧接续） | `image_to_video` | `reference_image_path` = 前一 shot 尾帧 |
| 跨 event 相邻 + 共同角色 | 走 Step 3 判断 | 前一 shot 尾帧可加入 `reference_images` |
| 所有角色开头可见 + 动作小 | `image_to_video` | `reference_image_path` = 生成的首帧图 |
| 有角色中途出场 / 大幅运动 | `reference_to_video` | `reference_images` = 角色参考图 |
| 无参考图 | `text_to_video` | 仅 prompt |

## 决策流程

### Step 1: 判断谁出镜

从 `focus_on` 和 states.json 确定：

- `focus_on` 中的 CharacterAppearance ID → 哪些角色出镜
- `focus_on` 中的 LocationState ID → 场景环境
- `focus_on` 中的 PropState ID → 道具
- 通过 active_during 找同 event 的 CharacterMind → 角色行为

### Step 2: 判断尾帧接续

按优先级检查：

#### 2a. 同 event 内连续 shot

**条件**：当前 shot 与 shot_order 中前一个 shot 属于同一个 event_id，且前一个 shot 已生成。

从前一 shot 的输出提取尾帧，用 `image_to_video`。→ **跳到 Step 4**。

#### 2b. 跨 event 相邻（空间连续性）

**条件**：shot_order 中相邻但不同 event_id，且两个 shot 有共同的出镜角色（focus_on 中有相同 entity 的状态）。

可选将前一 shot 尾帧加入 `reference_images`（不是 `reference_image_path`，不改变生成模式）。尾帧占一个名额（上限 4 张），优先保角色参考图。→ **继续 Step 3**。

| 用尾帧参考 | 不用 |
|---|------|
| 角色跨场景移动（森林→小屋） | 无共同角色的跳切 |
| 场景有物理连续性（门内→门外） | 闪回、完全无关的场景 |

#### 都不命中

直接进 Step 3。

### Step 3: 判断首帧可行性

**核心问题：首帧能否包含所有出镜角色的视觉身份信息？**

**适合首帧（→ `image_to_video`）**：
- 所有角色在视频开头就在画面中，正面/侧面可辨认
- 无大幅运动（非 tracking、非奔跑/跳跃/转身）

**不适合首帧（→ `reference_to_video`）**：
- 有角色中途出场（如"从树后走出"，开头不在画面中）
- 角色背对镜头或被遮挡
- 大幅运动（tracking + 奔跑/蹦跳）

**无参考图（→ `text_to_video`）**：
- 纯环境镜头，无角色参考图可用

### Step 4: 选择参考图

从 states.json 按 focus_on 中的状态 ID 查找 `reference_image` 路径：

- CharacterAppearance → 角色参考图
- LocationState → 场景参考图
- PropState → 道具参考图（通常没有，可忽略）
- 上限 4 张，超出时优先保角色
- Step 2b 的尾帧参考也占一个名额

## 并行规则

- 同 event 内的连续 shot 必须串行（后者可能需要前者尾帧）
- 不同 event 且不使用尾帧参考的 shot 可并行
- 2b 决定使用尾帧参考时，必须等前一 shot 完成

## 常见陷阱

1. **尾帧接续只在同 event 内或有共同角色时使用。** 无关场景跳切不要强行接续。
2. **已用首帧/尾帧时，额外参考图收益有限。** 画面身份已锚定。
3. **运动幅度大的镜头慎用首帧。** 首帧约束起始构图，大幅运动会不自然。
4. **每个 shot 独立决策。** 不要因为一次失败就放弃某种策略。
5. **prompt 中不要遗漏 `<<<image_N>>>` 标记。** 缺标记 = 角色一致性丢失。
