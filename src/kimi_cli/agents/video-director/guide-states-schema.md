# States Schema 定义

> 实体状态规划前，用 ReadFile 加载本文件，确认字段格式。

导演的实体状态规划产出为 `states.json`，存放在项目目录下。

## states.json

```json
{
  "character_appearances": [...],
  "character_minds": [...],
  "prop_states": [...],
  "location_states": [...],
  "active_during": {
    "character_appearance": {...},
    "character_mind": {...},
    "prop_state": {...},
    "location_state": {...}
  }
}
```

### CharacterAppearance

角色的外观状态。同一角色在不同阶段可能有不同外观（换装、受伤、变形等）。

<example>
```json
{
  "id": "appear_red_neat",
  "entity": "char_red",
  "phase": "整洁出行装",
  "visual": {
    "costume": "红色丝绒斗篷，白色连衣裙，黑色小皮鞋",
    "hair": "棕色卷发散落在斗篷里",
    "physical": "健康，红润的脸颊",
    "props": ["prop_basket"]
  }
}
```
</example>

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `appear_{entity_short}_{descriptor}`，全局唯一 |
| entity | string | 是 | 角色 ID，必须在 entities.json 中存在 |
| phase | string | 是 | 状态名称（简短中文，描述这是什么阶段的外观） |
| visual | object | 是 | 视觉描述，key-value 自由定义。常用 key：costume、hair、physical、props、makeup |

**visual 写作要点：**
- 描述必须具体到可以被 AI 图像生成理解（"红色丝绒斗篷" 而非 "穿着外套"）
- 与 entities.json 中 fixed_traits 的关系：fixed_traits 是不变的基础特征，visual 描述在此基础上的当前状态
- props 字段列出该状态下角色随身携带的道具 ID

### CharacterMind

角色的心理/行为状态。影响表演方向和镜头设计。

<example>
```json
{
  "id": "mind_red_innocent",
  "entity": "char_red",
  "phase": "天真无忧",
  "emotion": "开心，对世界充满好奇",
  "behavior": "蹦蹦跳跳，东张西望，主动与人搭话"
}
```
</example>

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `mind_{entity_short}_{descriptor}`，全局唯一 |
| entity | string | 是 | 角色 ID |
| phase | string | 是 | 状态名称 |
| emotion | string | 是 | 情绪描述 |
| behavior | string | 是 | 该情绪下的外在行为表现（用于指导表演和镜头设计） |

### PropState

道具的视觉状态。

<example>
```json
{
  "id": "pstate_basket_full",
  "entity": "prop_basket",
  "phase": "装满完好",
  "visual": "藤篮盖着红白格子布，鼓鼓的，装满了蛋糕和葡萄酒",
  "condition": "完好"
}
```
</example>

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `pstate_{entity_short}_{descriptor}`，全局唯一 |
| entity | string | 是 | 道具 ID，必须在 entities.json 中存在 |
| phase | string | 是 | 状态名称 |
| visual | string | 是 | 视觉描述 |
| condition | string | 否 | 物理状态（完好/损坏/打开/关闭等） |

### LocationState

场景的视觉状态（光照、天气、氛围等）。

<example>
```json
{
  "id": "lstate_forest_bright",
  "entity": "loc_forest",
  "phase": "阳光林间小路",
  "lighting": "丁达尔光束穿过树冠，光斑洒在小路上",
  "weather": "晴，微风",
  "condition": "野花盛开，蝴蝶飞舞",
  "atmosphere": "童话般的美好"
}
```
</example>

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `lstate_{entity_short}_{descriptor}`，全局唯一 |
| entity | string | 是 | 地点 ID，必须在 entities.json 中存在 |
| phase | string | 是 | 状态名称 |
| lighting | string | 是 | 光照条件 |
| weather | string | 否 | 天气 |
| condition | string | 否 | 环境状态细节 |
| atmosphere | string | 是 | 整体氛围 |

### active_during

映射每个状态到它生效的事件列表。key 为状态 ID，value 为事件 ID 数组。

<example>
```json
{
  "character_appearance": {
    "appear_red_neat": ["evt_farewell", "evt_forest_walk", "evt_wolf_encounter"],
    "appear_red_disheveled": ["evt_rescue", "evt_reunion"]
  },
  "character_mind": {
    "mind_red_innocent": ["evt_farewell", "evt_forest_walk"],
    "mind_red_scared": ["evt_wolf_reveal", "evt_rescue"]
  },
  "prop_state": {
    "pstate_basket_full": ["evt_farewell", "evt_forest_walk", "evt_wolf_encounter"]
  },
  "location_state": {
    "lstate_forest_bright": ["evt_forest_walk"],
    "lstate_forest_dark": ["evt_wolf_encounter"]
  }
}
```
</example>

**active_during 规则：**
- 每个事件中出现的每个角色，必须有且仅有一个 character_appearance 覆盖该事件
- 每个事件中出现的每个角色，必须有且仅有一个 character_mind 覆盖该事件
- 每个事件发生的地点，必须有且仅有一个 location_state 覆盖该事件
- 每个事件中出现的每个道具，必须有且仅有一个 prop_state 覆盖该事件
- 一个状态可以覆盖多个连续事件（角色外观没变就不需要新状态）
