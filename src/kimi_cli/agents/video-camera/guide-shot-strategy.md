# 生成模式决策参考

> 每个 shot 生成前，workflow-shoot.md 中的决策步骤引用本文件的条件定义和参考标准。

## 核心原则

1. **模型能从输入图片里"看到"谁，就能保持谁的一致性。** 首帧/参考图里出现的角色能保持一致，没出现的无法保证。
2. **尾帧用法由导演意图决定，不由"什么变了"机械决定。** content 和 transition_in 已编码了导演的转换意图。
3. **角色一致性由参考图保证，不由尾帧保证。** 参考图是白底全身的身份锚点，尾帧是特定场景中的画面截图。

## 尾帧的三种角色

| 角色 | 触发条件 | 用法 |
|------|---------|------|
| **接续画面** | 同 event 内时长拆分（shot_type+angle 相同） | `reference_image_path`（主输入，image_to_video） |
| **变化起点** | content 描述从前一状态到当前状态的转换过程 | 放入 `reference_images`（辅助参考） |
| **不使用** | transition_in=cut + content 描述独立场景 | 不提取尾帧 |

## 判断导演是否要展示转换

**需要展示转换**的信号：
- content 描述一个**过程**（"从 X 变成 Y"、"角色从 A 走到 B"、"光线从明亮变为昏暗"）
- transition_in 是 `dissolve`（渐变过渡）

**不需要展示转换（硬切）**的信号：
- transition_in 是 `cut`
- content 描述一个**独立画面**（"小屋内，奶奶躺在床上"），不涉及从前一画面的过渡

**同 event 内镜头切换**（shot_type 或 angle 变了）：
- content 描述同一动作的不同视角 → 展示转换
- content 描述独立画面（如插入道具特写） → 不展示

## 生成模式判断条件

| 条件 | 模式 |
|------|------|
| 所有角色在视频开头就在画面中 + 正面/侧面可辨认 + 无大幅运动 | `image_to_video`（先生成首帧） |
| 有角色中途出场（如"从树后走出"） | `reference_to_video` |
| 角色背对镜头或被遮挡 | `reference_to_video` |
| 大幅运动（tracking + 奔跑/蹦跳） | `reference_to_video` |
| 纯环境镜头，无角色参考图 | `text_to_video` |

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

- 同 event 内 shot_type+angle 相同的连续 shot 必须串行（后者需要前者尾帧）
- 决定使用尾帧参考时，必须等前一 shot 完成
- 其他情况下不同 event 的 shot 可并行

## 常见陷阱

1. **不要机械按"什么变了"分 case。** 始终读 content + transition_in 判断导演意图。
2. **尾帧不是万能的一致性工具。** 硬切时使用尾帧反而引入前一场景的干扰。
3. **状态变化是故事的一部分。** 当 active_during 显示角色状态变了，用新状态的参考图。
4. **运动幅度大的镜头慎用首帧。** 首帧约束起始构图，大幅运动会不自然。
5. **每个 shot 独立决策。** 不要因为一次失败就放弃某种策略。
6. **prompt 中不要遗漏 `<<<image_N>>>` 标记。** 缺标记 = 角色一致性丢失。
