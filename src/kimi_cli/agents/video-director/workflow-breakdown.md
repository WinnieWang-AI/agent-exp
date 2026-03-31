# 事件拆解

## 输入

调用方通过 prompt 传入项目路径（绝对路径），项目目录下已有编剧产出的文件：
- `meta.json` — 标题、视频规格、风格
- `entities.json` — 角色、场景、道具
- `outline.json` — 故事大纲（幕 → 场景摘要）
- `act-1.json`、`act-2.json`... — 各幕场景详情

## 步骤

### Step 1: 加载格式定义

用 ReadFile 加载 `${AGENT_DIR}/guide-events-schema.md`，确认 events.json 的字段格式。后续写文件必须以此为准。

### Step 2: 建立全局上下文

依次读取以下三个文件（它们体积小，全部读入）：

1. `{project_path}/meta.json` — 获取目标时长、风格
2. `{project_path}/entities.json` — 获取完整的角色/场景/道具清单及 ID
3. `{project_path}/outline.json` — 获取全局故事结构（幕 → 场景摘要）

从这三个文件中提取：
- **目标时长**（如 "1min"），用于估算事件总数
- **所有实体 ID**，用于后续校验引用正确性
- **全局场景列表**，用于理解每个场景在故事中的位置和分量

### Step 3: 估算事件容量

根据目标时长估算合理的事件数量：

| 目标时长 | 事件数 | 说明 |
|----------|--------|------|
| 30s | 2-4 | 极简叙事，每个事件 1-2 个 shot |
| 1min | 4-8 | 标准短片，每个事件 1-3 个 shot |
| 3min | 10-20 | 中等篇幅，允许更细腻的节奏变化 |
| 5min+ | 20+ | 长篇，可有复杂的并行叙事 |

这是软约束——故事节奏优先，但偏差不应超过 50%。如果剧本的场景数远超估算，说明需要合并；如果远少于估算，说明可能需要拆分。

### Step 4: 逐 act 拆解事件

按幕序号依次处理。对每一幕：

1. 用 ReadFile 读取 `{project_path}/act-{N}.json`
2. 遍历该幕的每个场景，将 beats 拆解为事件

**拆分原则：**

一个事件是一个可拍摄的叙事单元，通常对应 1-3 个 shot（5-15 秒）。判断标准：

- **动力变化 = 新事件**：场景内出现新角色进入、冲突升级/缓和、情绪转折、空间转换时，应拆为新事件
- **连续动作 = 同一事件**：同一组角色在同一空间内的连续互动，没有明显的节奏断点，合为一个事件
- **短场景整体合并**：只有 1-2 个 beat 的短场景，通常整个场景就是一个事件
- **跨场景合并**：相邻场景如果空间相同、时间连续、角色相同，且各自很短，可以合并为一个事件（在 source_scenes 中记录多个场景 ID）

**处理每个事件时：**

- `description`：用自己的语言重新描述事件内容，要包含关键的视觉动作和空间关系。不要照抄 beats 原文拼接，要写成一段连贯的场景描写
- `interactions`：提取角色间有明确肢体/空间/对话互动的部分，描述互动的视觉形态
- `state_changes`：只记录剧本中明确描写的变化（character_states 中 appearance 不为 null、emotion 有变化、location_state 不为 null、prop_states 不为 null）。不要推测隐含的变化
- `dialogues`：原样提取剧本中的对白 beats，不修改台词文字
- `mood`：综合场景的 mood 和 beats 的情绪走向
- `narrative_weight`：从 source_scenes 对应场景的 `narrative_weight` 继承。多个 source_scenes 时取最高权重（climax > turning_point > setup > transition）

**处理完一幕后**，该幕的 act 文件内容就不再需要。已提取的事件列表提供后续幕的上下文。

### Step 5: 定义事件时序

所有事件提取完成后，定义 `event_sequence`：

- 大多数事件之间是 **THEN**（顺序）关系
- 当剧本中有明确的平行叙事（如 outline 中的 `narrative_mode: "parallel"`，或故事逻辑要求两个事件同时发生），使用 **PARALLEL**
- 不要过度使用 PARALLEL——只在叙事结构明确要求时使用
- 确保每个事件（除第一个）都作为至少一条边的 `to` 出现

### Step 6: 写入文件

用 WriteFile 将完整的 events.json 写入 `{project_path}/events.json`。

### Step 7: 自检

写完后逐项检查：

1. **ID 唯一性**：所有事件 ID 全局唯一
2. **引用正确**：所有 characters/props/location ID 在 entities.json 中存在
3. **source_scenes 有效**：所有 source_scenes 中的场景 ID 在 outline.json 中存在
4. **时序完整**：每个事件（除第一个）在 event_sequence 中作为 `to` 出现
5. **事件数量合理**：与 Step 3 的估算对比，偏差不超过 50%
6. **无遗漏场景**：outline 中的每个场景都被至少一个事件的 source_scenes 覆盖
7. **对白完整**：剧本中的所有对白 beats 都出现在某个事件的 dialogues 中

发现问题直接修复并重新写入 events.json，不需要报告给调用方。

## 输出

在项目路径下生成：
- `events.json` — 事件列表 + 事件时序关系

## 错误处理

- **项目路径下缺少文件**：报告调用方，说明缺少哪个文件。
- **entities.json 中缺少剧本引用的实体**：在自检中标记，继续处理，将问题报告给调用方。
- **事件数量严重超出估算（> 2 倍）**：暂停，向调用方说明剧本复杂度与目标时长不匹配，建议调整。
