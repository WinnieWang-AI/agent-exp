# 镜头设计

## 输入

项目目录下已有：
- `meta.json` — 目标时长、画面比例、视觉风格
- `events.json` — 事件列表（描述、角色、互动、对白、mood）+ 事件时序
- `states.json` — 状态节点 + active_during 映射（知道每个事件中角色/场景/道具的当前状态）

## 步骤

### Step 1: 加载格式定义

用 ReadFile 加载 `${AGENT_DIR}/guide-shots-schema.md`，确认 shots.json 的字段格式和词表。

### Step 2: 读取输入

读取以下文件：

1. `{project_path}/meta.json` — 提取目标时长和画面比例
2. `{project_path}/events.json` — 提取事件列表和时序关系
3. `{project_path}/states.json` — 提取 active_during 映射

将目标时长转换为秒数（如 "1min" → 60s, "30s" → 30s, "3min" → 180s）。

### Step 3: 预算分配

在设计具体镜头之前，基于 **narrative_weight** 分配时长预算。

从 events.json 中每个事件的 `narrative_weight` 字段读取叙事权重。

**分配原则：**

`narrative_weight` 是分配的指导方向，不是固定公式：

- **climax / turning_point** 是故事的核心时刻，值得更多 shot 和时长，让观众充分感受
- **transition** 应尽量紧凑，服务于衔接，不喧宾夺主
- **setup** 按内容复杂度灵活处理

根据目标总时长和事件总数，综合判断每个事件的 shot 数和时长。硬约束只有两条：
- 含对白的事件时长 ≥ 对白朗读时间（不可压缩）
- 单个 shot 范围 3-10 秒

这是初始预算，逐事件设计时会微调。

### Step 4: 逐事件设计镜头

按事件时序（event_sequence）依次处理每个事件。

对每个事件：

1. **确认上下文**：
   - 从 events.json 读取事件描述、characters、interactions、dialogues、mood
   - 从 states.json 的 active_during 查出该事件中每个角色的 CharacterAppearance ID、场景的 LocationState ID、道具的 PropState ID
   - 查看前一个事件的最后一个 shot（用于衔接设计），**记录其中每个角色的最终物理位置**（从 content 的"最终状态"段提取）

2. **决定 shot 数量**：
   - 根据该事件的时长预算和内容复杂度决定
   - 简单事件（单一动作、无对白）：1 shot
   - 中等事件（互动 + 少量对白）：2 shots
   - 复杂事件（多个互动、情绪转折、多段对白）：3 shots
   - 每个 shot 时长 3-10 秒

3. **设计每个 shot**：

   **景别选择：**
   - 事件第一个 shot 通常用 wide 或 medium 建立空间
   - 情绪高点用 close_up 或 extreme_close
   - 对话用 medium_close 或 over_shoulder
   - 关键道具用 detail_insert
   - 同一事件内避免连续使用相同景别

   **角度选择：**
   - 默认 eye_level
   - 角色有权力差异时用 low_angle（强势方）/ high_angle（弱势方）
   - 不安/紧张时用 dutch_angle
   - 不要过度使用非 eye_level 角度

   **运镜选择：**
   - 对话场景多用 static
   - 角色移动时用 tracking
   - 紧张递增用 push_in
   - 揭示新环境用 pull_out 或 crane_up
   - 混乱/紧张用 handheld_shake
   - 每个 shot 只用一种运镜

   **聚焦对象（focus_on）：**
   - 填写状态 ID（不是实体 ID），下游需要知道用哪张参考图
   - 必须包含该 shot 画面中的主要对象
   - LocationState 必须包含（它决定了背景）

   **画面内容（content）：**

   按"起始状态 → 动态变化 → 最终状态"的顺序写，用"→"分隔三段：

   - **起始状态**：镜头开始时，角色在场景中的物理位置（用场景内参照物如"起跑线左端""树根旁"，不用"画面左侧""前景"等构图语言）、角色之间的相对位置和朝向、姿态表情。**空间连续性**：如果某角色在前一事件结束时处于某个位置，本事件中该角色的起始位置必须与之一致，除非事件描述中有明确的移动动作。角色不能凭空换位——睡着的角色醒来时还在原地，走路的角色从上次停下的地方继续
   - **动态变化**：这段时间里发生的动作、互动、状态变化。从当前 event 的 interactions 和 state_changes 推导具体动作。多角色时写角色之间的互动和反应。**对话和音效按时间顺序写在对应动作节拍中**（对话用「」标注说话者和语气，音效直接描述声源和声音）
   - **最终状态**：镜头结束时角色的位置、姿态、表情

   示例：`起跑线左端，狐狸裁判举旗站立，兔子在起跑线中央弓身热身，乌龟在兔子右侧一步外静立低头 → 兔子转向乌龟，拍着自己胸口大笑，用脚尖点地炫耀速度；乌龟抬头看兔子一眼，不回应，低头继续盯着赛道前方 → 兔子双手叉腰面朝乌龟站定，乌龟目视前方不为所动`

   其他要求：
   - 不写抽象情绪，只写可见的具体内容
   - 环境/光影描写最多一句，篇幅留给角色动作
   - **跨事件衔接**：transition_in 为 dissolve/fade 时，起始状态须描写从前一场景过渡到当前场景的过程；transition_in 为 cut 时直接描写当前场景

   **旁白（narration）：**
   - 画外旁白（不在画面中发生的解说词），如"很久很久以前……"
   - 无旁白时为空字符串或省略
   - 角色对话和音效不放这里，写在 content 中

   **时长（duration_seconds）：**

   估算流程：
   1. **台词下限**：content 中有对白的 shot，根据对白文本和 meta.json 的 language 估算朗读时间，加上每句间 0.5-1 秒的轮换停顿。这是该 shot 的最短时长，不可压缩。
   2. **自然时长**：在台词下限之上，综合考虑：
      - 动作复杂度：多步动作序列 > 单一动作 > 静止画面
      - 镜头运动：tracking / pan 需要执行时间 > static
      - 景别信息量：wide 建立场景需要观众读画面 > close_up 聚焦单一对象
      - 叙事节奏：紧张段落短切制造紧迫感，情感段落停留让情绪沉淀
      - dissolve 转场比 cut 多消耗 0.5-1 秒重叠时间
   3. **总时长调配**：所有 shot 自然时长求和，与目标总时长对比。超出则压缩弹性 shot（无台词、static、非关键），不足则延长抒情/环境镜头。台词下限不可压缩。
   4. 单个 shot 范围：3-10 秒（AI 视频生成限制）

   **场景连续性（scene_continuous）：**
   按 shot_order 顺序，标注当前 shot 与前一 shot 是否在同一物理场景中：
   - 同一事件内的 shot：true
   - 相邻事件，active_during 中 LocationState 相同：true
   - 相邻事件，active_during 中 LocationState 不同：false
   - shot_order 中第一个 shot：false

   **转场：**
   - 同一事件内的 shot 之间：cut
   - 相邻事件，active_during 中 location_state 和主要角色外观均无变化：cut
   - 相邻事件，active_during 中 location_state 或角色外观有变化：dissolve（Camera 会提取前一 shot 尾帧 + 新状态参考图，渲染环境/状态转换过程）
   - 全片第一个 shot 的 transition_in：fade_in
   - 全片最后一个 shot 的 transition_out：fade_out
   - 其他情况默认 cut

### Step 5: 确定播放顺序（shot_order）

根据 events.json 的 `event_sequence`，将所有 shot 排列为最终播放顺序：

1. 从 event_sequence 构建事件 DAG
2. 按拓扑顺序遍历事件：
   - `THEN` 关系：前一个 event 的 shot 全部排完，再排后一个
   - `PARALLEL` 关系：两个 event 的 shot 交叉排列。交叉节奏是创作决策——可以按情绪节奏交替（紧张场景快速切换 A1-B1-A2-B2），也可以先完整展示一侧再切另一侧（A1-A2-B1-B2）
3. 同一 event 内的 shot 按 `order` 字段顺序排列
4. 生成 `shot_order: [shot_id, ...]` 数组

这个顺序就是最终成片的播放顺序，下游不再解析 event_sequence。

### Step 6: 校验总时长

所有 shot 设计完成后（包括 shot_order）：

1. 计算 total_duration_seconds = 所有 shot 的 duration_seconds 之和
2. 与目标时长对比，允许 ±10% 偏差
3. 如果超出偏差：
   - 过长：缩减过渡性 shot 的时长，或合并不必要的 shot
   - 过短：为重要事件增加 shot，或适当延长抒情镜头的时长
4. 调整后重新计算，直到满足偏差要求

### Step 7: 写入文件

用 WriteFile 将完整的 shots.json（含 shots、shot_order、total_duration_seconds）写入 `{project_path}/shots.json`。

### Step 8: 自检

1. **ID 唯一性**：所有 shot ID 全局唯一
2. **事件覆盖**：每个事件至少有一个 shot
3. **event_id 有效**：所有 event_id 在 events.json 中存在
4. **focus_on 有效**：所有状态 ID 在 states.json 中存在
5. **focus_on 与 active_during 一致**：shot 引用的状态确实在该事件中生效
6. **时长合规**：每个 shot 的 duration_seconds 在 3-10 秒范围内
7. **总时长匹配**：total_duration_seconds 与目标时长偏差 ≤ 10%
8. **转场连贯**：前一个 shot 的 transition_out 与后一个 shot 的 transition_in 逻辑匹配（不会 fade_out 接 fade_in）
9. **content 具体**：抽查几个 shot 的 content，确认描述具体可执行，不是空泛的情绪词
10. **对白完整分配**：events.json 中每个事件的每段对白都被写入某个 shot 的 content 中，无遗漏、无重复
11. **对白时长匹配**：content 中含对白的 shot 时长不低于台词朗读时间（根据对白文本和 language 估算）
12. **shot_order 完整**：shot_order 包含所有 shot ID，无遗漏、无重复，同 event 内 shot 的相对顺序与 order 字段一致
13. **细碎度检查**：审视整体 shot 时长分布。如果大部分 shot 都集中在最短时长（3-4秒），整片节奏会显得细碎急促，观众来不及消化画面内容。检查 shot 时长是否有高低变化，是否体现了 narrative_weight 的差异——climax / turning_point 的核心 shot 应比 transition 的过渡 shot 有更充分的时长
14. **连贯性检查**：按 shot_order 审视相邻 shot 的衔接。连续多个短 shot 硬切（尤其跨场景时）会破坏视觉连贯性。每次换场景（scene_continuous = false）的第一个 shot 需要足够时长让观众建立新的空间认知，不应是最短时长
15. **跨事件空间连续性**：按 shot_order 检查每个跨事件边界——前一事件最后一个 shot 的"最终状态"中角色的物理位置，与后一事件第一个 shot 的"起始状态"中同一角色的物理位置是否一致。不一致且事件 description 中没有解释角色如何移动的，必须修正 content

发现问题直接修复并重新写入 shots.json。

### Step 9: 生成 content 可读性测试

为下游观众审查生成测试题，用于验证 shot content 是否准确表达了空间关系。

**出题规则（机械生成，不需要构思）：**

遍历每个 shot 的 `focus_on` 字段，提取其中的角色状态 ID（CharacterAppearance），对照 entities.json 得到角色名称和场景名称：

- **每个角色** → 生成一题：`"{角色名}在{场景名}中的什么位置？"`
- **每对角色**（shot 中有 2 个及以上角色时）→ 生成一题：`"{角色A}和{角色B}的相对位置是什么？"`

**标准答案：**
- 基于你的创作意图作答，简洁明确，一句话
- 不回看 content，从 events 的 interactions 和你对空间布局的设计意图推导

**自检：** 生成前先计算预期题目数。对每个 shot，统计 focus_on 中的角色数 N（仅 CharacterAppearance，不含 LocationState/PropState），该 shot 应生成 N + N*(N-1)/2 题。所有 shot 求和即为总题数。生成后核对实际题数是否等于预期，不等则补齐。

用 WriteFile 分别写入两个文件：

`{project_path}/content-quiz.json`（只含问题，供观众盲答）：

```json
{
  "expected_count": 14,
  "questions": [
    {
      "id": "q_001",
      "shot_id": "evt_001_shot_1",
      "question": "小明在客厅中的什么位置？"
    },
    {
      "id": "q_002",
      "shot_id": "evt_001_shot_1",
      "question": "小明和小红的相对位置是什么？"
    }
  ]
}
```

`{project_path}/content-quiz-answers.json`（含标准答案，观众对比时才读取）：

```json
{
  "answers": [
    {
      "id": "q_001",
      "answer": "靠近窗户，面朝门口"
    },
    {
      "id": "q_002",
      "answer": "小明在左侧靠窗，小红在右侧门口处，两人面对面"
    }
  ]
}
```

## 输出

在项目路径下生成：
- `shots.json` — 逐事件的镜头列表 + 播放顺序（shot_order）+ 总时长
- `content-quiz.json` — content 可读性测试题，只含问题（供观众盲答）
- `content-quiz-answers.json` — 测试题标准答案（供观众对比）

## 错误处理

- **目标时长与事件数严重不匹配**（如 30 秒要塞 15 个事件）：报告调用方，建议减少事件数或增加目标时长。
- **states.json 缺少 active_during**：无法确定 focus_on，报告调用方。
- **调整后总时长仍无法满足 ±10% 偏差**：以最接近的结果写入，在报告中说明偏差值。
