# 实体状态规划

## 输入

项目目录下已有：
- `entities.json` — 角色、场景、道具的基础定义（fixed_traits、description 等）
- `events.json` — 事件列表（含 state_changes 线索和 active_during 所需的事件-实体关系）

## 步骤

### Step 1: 加载格式定义

用 ReadFile 加载 `${AGENT_DIR}/guide-states-schema.md`，确认 states.json 的字段格式。

### Step 2: 读取输入文件

读取以下两个文件：

1. `{project_path}/entities.json` — 获取所有实体的基础定义
2. `{project_path}/events.json` — 获取事件列表、每个事件涉及的实体、state_changes 线索

从中提取：
- 每个角色的 fixed_traits（基础外观）
- 每个场景的 description（默认环境）
- 每个道具的 description（默认外观）
- 每个事件中出场的角色、道具、场景
- 每个事件的 state_changes（状态变化线索）

### Step 3: 逐实体规划状态

按实体类型分别处理：角色 → 场景 → 道具。

#### 角色状态

对每个角色：

1. 找出该角色参与的所有事件（按时序排列）
2. 扫描这些事件的 state_changes，找出所有 appearance 变化点
3. 根据变化点划分阶段，每个阶段定义一个 CharacterAppearance
4. 没有变化的连续事件共享同一个状态

**状态划分原则：**
- 外观无变化（events.json 中没有 aspect: appearance 的 state_change）→ 整个故事只需一个 CharacterAppearance，visual 基于 fixed_traits 展开
- 外观有变化 → 变化前后各一个 CharacterAppearance。变化前的 visual 基于 fixed_traits，变化后的 visual 根据 state_change 的 detail 修改
- **不发明变化**：只有 events.json 中有明确 state_change 的才创建新状态。不要因为"感觉应该变了"就增加状态
- 角色的情绪和行为已在 events.json 中通过 interactions、state_changes、mood 描述，不需要单独建模

#### 场景状态

对每个场景：

1. 找出发生在该场景的所有事件
2. 扫描这些事件的 state_changes，找出 lighting / condition 等变化
3. 根据变化划分阶段。无变化则基于场景的 description 创建一个默认 LocationState

**注意：** 同一场景在不同时间段（如 morning vs night）可能需要不同的 LocationState，即使没有显式的 state_change。参考事件的 time_of_day 判断。

#### 道具状态

对每个道具：

1. 找出涉及该道具的所有事件
2. 扫描 state_changes，找出 appearance / condition / held_by 等变化
3. 根据变化划分阶段。无变化则基于道具的 description 创建一个默认 PropState

### Step 4: 构建 active_during 映射

对每个状态，列出它生效的事件 ID 列表：

1. 遍历每个事件
2. 对该事件中的每个角色，确定其当前的 CharacterAppearance
3. 对该事件的场景，确定其当前的 LocationState
4. 对该事件中的每个道具，确定其当前的 PropState
5. 将事件 ID 添加到对应状态的 active_during 列表中

### Step 5: 写入文件

用 WriteFile 将完整的 states.json 写入 `{project_path}/states.json`。

### Step 6: 自检

1. **覆盖完整性**：
   - 每个事件中的每个角色都有且仅有一个 character_appearance 覆盖
   - 每个事件的场景都有且仅有一个 location_state 覆盖
   - 每个事件中的每个道具都有且仅有一个 prop_state 覆盖
2. **ID 引用正确**：所有 entity 字段引用的 ID 在 entities.json 中存在
3. **事件引用正确**：active_during 中的事件 ID 在 events.json 中存在
4. **visual 描述具体**：CharacterAppearance 的 visual 描述不能是空泛的（如"穿着衣服"），必须具体到可以生成参考图
5. **状态变化有依据**：每个新状态的产生都能在 events.json 的 state_changes 中找到对应线索（time_of_day 变化除外）

发现问题直接修复并重新写入 states.json。

## 输出

在项目路径下生成：
- `states.json` — 所有实体状态节点 + active_during 映射

## 错误处理

- **events.json 中的 state_changes 描述模糊**：根据 entities.json 的基础定义和事件上下文合理推断，在该状态的 phase 中标注"推断"。
- **角色在某些事件中缺少 state_change 线索但明显应有变化**（如场景 mood 从"欢乐"突变为"恐惧"）：不创建新的 CharacterAppearance。情绪和行为变化已在 events.json 的 interactions 和 state_changes 中体现，无需在 states.json 中重复建模。
