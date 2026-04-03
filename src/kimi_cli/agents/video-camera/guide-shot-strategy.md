# 生成模式决策参考

> 每个 shot 生成前，workflow-shoot.md 中的决策步骤引用本文件的条件定义和参考标准。

## 核心原则

1. **每个 shot 都必须携带参考图。** 角色 shot 携带角色参考图 + 场景参考图，纯环境 shot 携带场景参考图。参考图是视觉一致性的唯一保证。
2. **模型能从输入图片里"看到"谁，就能保持谁的一致性。** 首帧/参考图里出现的角色能保持一致，没出现的无法保证。
3. **尾帧用法由导演标注决定。** `scene_continuous` 和 `transition_in` 已编码了导演的场景连续性意图。
4. **角色一致性由参考图保证，不由尾帧保证。** 参考图是白底全身的身份锚点，尾帧是特定场景中的画面截图。

## 尾帧判断

**是否使用尾帧**（由导演通过 `scene_continuous` 字段标注）：

| 条件 | 是否使用尾帧 |
|------|-------------|
| `scene_continuous = true` | 使用 |
| `scene_continuous = false` + `transition_in = dissolve` | 使用 |
| `scene_continuous = false` + `transition_in = cut` | 不使用 |

**尾帧用法**（由 Camera 判断画面能否从尾帧自然延续）：

| 条件 | 用法 |
|------|------|
| 构图没变（景别、角度一致）且无新角色出场 | 从尾帧画面开始（`reference_image_path`，image_to_video） |
| 构图变了，或有新角色出场 | 尾帧做一致性参考（放入 `reference_images`），模式 = `reference_to_video` |

## 生成模式判断条件

| 条件 | 模式 |
|------|------|
| 所有角色在视频开头就在画面中 + 正面/侧面可辨认 + 无大幅运动 | `image_to_video`（先生成首帧） |
| 有角色中途出场（如"从树后走出"） | `reference_to_video` |
| 角色背对镜头或被遮挡 | `reference_to_video` |
| 大幅运动（tracking + 奔跑/蹦跳） | `reference_to_video` |
| 纯环境镜头 | `image_to_video`（用场景参考图生成首帧）或 `reference_to_video`（场景参考图做 reference） |

## 参考图选择规则

- 从 active_during 查当前 event 中各实体的状态，再从 states.json 查对应的 `reference_image` 路径
- 类型：CharacterAppearance → 角色参考图，LocationState → 场景参考图，PropState → 道具参考图
- 尾帧参考（如有）也占一个名额
- 上限按 provider 能力（不写死），超出时按优先级截断：**角色 > 场景 > 道具 > 尾帧参考**

## 跨 event 状态对比

当前后 shot 跨 event 时，对比 active_during 中两个 event 的实体状态映射：
- 状态没变的实体 → 用同一张参考图（保一致性）
- 状态变了的实体 → 用新状态的参考图（这是故事发展的一部分，不是不一致）

## 并行规则

- `scene_continuous = true` 的连续 shot 必须串行（后者需要前者尾帧）
- `transition_in = dissolve` 的 shot 必须等前一 shot 完成
- 其他情况下 shot 可并行

## 常见陷阱

1. **不要自己推断场景连续性。** 读 `scene_continuous` 字段，这是导演的标注。
2. **尾帧不是万能的一致性工具。** 硬切时使用尾帧反而引入前一场景的干扰。
3. **状态变化是故事的一部分。** 当 active_during 显示角色状态变了，用新状态的参考图。
4. **运动幅度大的镜头慎用首帧。** 首帧约束起始构图，大幅运动会不自然。
5. **每个 shot 独立决策。** 不要因为一次失败就放弃某种策略。
6. **prompt 中不要遗漏 `<<<image_N>>>` 标记。** 缺标记 = 角色一致性丢失。
