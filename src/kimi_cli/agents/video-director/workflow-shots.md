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
   - 查看前一个事件的最后一个 shot（用于衔接设计）

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
   - 具体描写观众看到什么，不要写抽象情绪
   - 按空间顺序描写：先场景，再以一个角色为锚点定位，其他角色相对于锚点描写
   - 包含关键的光影和环境细节
   - 如果有对白，描写角色在说话的动作/表情（具体台词写在 dialogues 字段中）
   - **跨事件衔接**：transition_in 为 dissolve/fade 时，content 须描写从前一场景过渡到当前场景的过程，不能只描写目标画面；transition_in 为 cut 时描写独立画面即可

   **对白（dialogues）：**
   - 将事件的 dialogues 分配到具体 shot 中
   - 每段对白只出现在一个 shot 里，不重复
   - 对白所在 shot 的时长要足够容纳对白的自然语速
   - 对白内容原样保留，不修改台词

   **音效（sfx）：**
   - 只列关键的、影响观感的声音（不需要穷举所有环境音）
   - 与画面动作对应（门关上 → "木门关闭声"，脚踩落叶 → "落叶沙沙声"）
   - 纯环境氛围音也可以列（"远处雷声"、"溪流声"）

   **时长（duration_seconds）：**

   估算流程：
   1. **台词下限**：有对白的 shot，根据对白文本和 meta.json 的 language 估算朗读时间，加上每句间 0.5-1 秒的轮换停顿。这是该 shot 的最短时长，不可压缩。
   2. **自然时长**：在台词下限之上，综合考虑：
      - 动作复杂度：多步动作序列 > 单一动作 > 静止画面
      - 镜头运动：tracking / pan 需要执行时间 > static
      - 景别信息量：wide 建立场景需要观众读画面 > close_up 聚焦单一对象
      - 叙事节奏：紧张段落短切制造紧迫感，情感段落停留让情绪沉淀
      - dissolve 转场比 cut 多消耗 0.5-1 秒重叠时间
   3. **总时长调配**：所有 shot 自然时长求和，与目标总时长对比。超出则压缩弹性 shot（无台词、static、非关键），不足则延长抒情/环境镜头。台词下限不可压缩。
   4. 单个 shot 范围：3-10 秒（AI 视频生成限制）

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
10. **对白完整分配**：events.json 中每个事件的每段对白都被分配到某个 shot 的 dialogues 中，无遗漏、无重复
11. **对白时长匹配**：含对白的 shot 时长不低于台词朗读时间（根据对白文本和 language 估算）
12. **shot_order 完整**：shot_order 包含所有 shot ID，无遗漏、无重复，同 event 内 shot 的相对顺序与 order 字段一致

发现问题直接修复并重新写入 shots.json。

## 输出

在项目路径下生成：
- `shots.json` — 逐事件的镜头列表 + 播放顺序（shot_order）+ 总时长

## 错误处理

- **目标时长与事件数严重不匹配**（如 30 秒要塞 15 个事件）：报告调用方，建议减少事件数或增加目标时长。
- **states.json 缺少 active_during**：无法确定 focus_on，报告调用方。
- **调整后总时长仍无法满足 ±10% 偏差**：以最接近的结果写入，在报告中说明偏差值。
