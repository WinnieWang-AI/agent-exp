# 生成模式决策参考

> 每个 shot 生成前，workflow-shoot.md 中的决策步骤引用本文件的条件定义和参考标准。

## 核心原则

1. **每个 shot 都必须携带参考图。** 角色 shot 携带角色参考图 + 场景参考图，纯环境 shot 携带场景参考图。参考图是视觉一致性的唯一保证。
2. **模型能从输入图片里"看到"谁，就能保持谁的一致性。** 首帧/参考图里出现的角色能保持一致，没出现的无法保证。
3. **尾帧用法由导演标注决定。** `scene_continuous` 和 `transition_in` 已编码了导演的场景连续性意图。
4. **角色一致性由参考图保证，不由尾帧保证。** 参考图是白底全身的身份锚点，尾帧是特定场景中的画面截图。

## 生成模式

**统一使用 `reference_to_video`。** 不使用 `image_to_video` 或 `text_to_video`。

角色一致性和空间控制都通过 reference_images 解决：角色/场景/道具参考图保证一致性，构图参考图（如需要）保证空间关系。

## 尾帧判断

**是否使用尾帧**（由导演通过 `scene_continuous` 字段标注）：

| 条件 | 是否使用尾帧 |
|------|-------------|
| `scene_continuous = true` | 使用，放入 reference_images |
| `scene_continuous = false` + `transition_in = dissolve` | 使用，放入 reference_images |
| `scene_continuous = false` + `transition_in = cut` | 不使用 |

尾帧始终作为 reference_images 中的一张参考图传入，用 `<<<tail_frame>>>` 标记在 prompt 中引用。

## 构图参考图（首帧图）

当 shot 有**关键空间位置关系**需要精确控制时，先用 GenerateImage 生成一张构图参考图，再作为 reference_images 之一传入 ref2v。

**何时需要构图参考图：**

| 条件 | 是否需要 |
|------|---------|
| `scene_continuous = true` 且构图变了（景别/角度/焦点角色不同） | 需要 — 空间关系靠构图图控制 |
| 多角色有精确相对位置要求（如"A 在线前，B 在线后"） | 需要 |
| 单角色、无复杂空间关系 | 不需要 |
| 纯环境镜头 | 不需要 |

构图参考图的 prompt 描述各元素的精确位置关系，输入参考图包括尾帧（如有）+ 角色/场景参考图。生成后放入 reference_images 数组，在视频 prompt 中用 `<<<composition>>>` 标记并提示"画面从此构图开始"。

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
4. **每个 shot 独立决策。** 不要因为一次失败就放弃某种策略。
5. **prompt 中不要遗漏 `<<<state_id>>>` 标记。** 缺标记 = 角色一致性丢失。
6. **空间关系靠构图参考图控制，不靠 prompt 文字。** 精确位置关系用 GenerateImage 生成构图图，比 prompt 描述可靠。
