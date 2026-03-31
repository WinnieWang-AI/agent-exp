# Screenplay Schema 定义

> 编写或修改故事文件前，用 ReadFile 加载本文件，确认字段格式。

编剧的产出物由 4 类 JSON 文件组成，存放在项目目录下。

## meta.json

全局元信息。

```json
{
  "title": "故事标题",
  "video_info": {
    "aspect_ratio": "16:9",
    "duration": "1min",
    "language": "中文"
  },
  "style": {
    "style_prefix": "hand-drawn illustration, warm color palette",
    "negative_prefix": "photorealistic, dark, horror"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 是 | 故事标题 |
| video_info.aspect_ratio | string | 是 | 画面比例，如 "16:9"、"9:16"、"1:1" |
| video_info.duration | string | 是 | 目标时长，如 "30s"、"1min"、"3min" |
| video_info.language | string | 是 | 对白语言，如 "中文"、"英文" |
| style.style_prefix | string | 是 | **纯视觉风格**正向描述（英文）。只写画风、色调、质感、光影风格，**禁止**混入具体场景/环境/地点描述——那些属于 location 的 description。 |
| style.negative_prefix | string | 是 | 视觉风格排除描述（英文） |

**style_prefix 正误示例：**

| | 示例 | 原因 |
|---|---|---|
| ✅ | `photorealistic, cinematic, realistic lighting, high dynamic range` | 纯画风 + 光影风格 |
| ✅ | `hand-drawn illustration, warm color palette, soft watercolor texture` | 纯画风 + 色调 |
| ❌ | `photorealistic, cinematic, modern city and cosmic vistas` | "modern city and cosmic vistas" 是场景内容，不是风格 |
| ❌ | `anime style, cherry blossom school campus` | "cherry blossom school campus" 是场景内容 |

## entities.json

世界设定：角色、场景、道具。

### Character

```json
{
  "id": "char_red",
  "name": "小红帽",
  "tags": ["主角"],
  "fixed_traits": {
    "age": "7岁",
    "hair": "棕色卷发",
    "signature_look": "红色丝绒斗篷，白色连衣裙"
  },
  "relationships": {
    "char_wolf": [
      {"kind": "陌生人", "until": "scene_002"},
      {"kind": "被欺骗者", "from": "scene_003", "until": "scene_005"},
      {"kind": "恐惧对象", "from": "scene_006"}
    ]
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `char_{name}`，全局唯一 |
| name | string | 是 | 角色名 |
| tags | string[] | 是 | 多维标签（角色类型、阵营、家族、世代等） |
| fixed_traits | object | 是 | 角色的固定视觉特征，key-value 自由定义。必须具体且有区分度 |
| relationships | object | 是 | key 为目标角色 ID，value 为关系数组。每个角色必须声明与其他相关角色的关系 |

**Relationship 条目：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| kind | string | 是 | 关系类型（如"亲人"、"对手"、"伪装者"） |
| from | string | 否 | 关系开始的场景 ID。省略表示从故事开始 |
| until | string | 否 | 关系结束的场景 ID。省略表示持续到故事结束 |

### Location

```json
{
  "id": "loc_grandma_house",
  "name": "外婆的小屋",
  "description": "林中温馨小木屋，壁炉、摇椅、碎花窗帘",
  "areas": [
    {"id": "area_bedroom", "name": "卧室", "description": "碎花窗帘，铁架床，壁炉旁的摇椅"},
    {"id": "area_doorway", "name": "门口", "description": "木门，门廊上挂着干花"}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `loc_{name}`，全局唯一 |
| name | string | 是 | 地点名 |
| description | string | 是 | 地点的默认视觉描述 |
| areas | array | 否 | 子区域列表。只在同一地点有多个会被使用的具体区域时添加 |

**Area 条目：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `area_{name}`，在该 location 内唯一 |
| name | string | 是 | 区域名 |
| description | string | 是 | 区域的视觉描述 |

### Prop

```json
{
  "id": "prop_basket",
  "name": "篮子",
  "description": "藤编篮子，盖着红白格子布，装着蛋糕和葡萄酒",
  "belongs_to": "char_red"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `prop_{name}`，全局唯一 |
| name | string | 是 | 道具名 |
| description | string | 是 | 道具的默认视觉描述 |
| belongs_to | string | 否 | 初始归属角色 ID |

## outline.json

故事大纲。两种层级形式：

### 标准形式（幕 → 场景）

```json
{
  "acts": [
    {
      "id": "act_1",
      "title": "第一幕：出发",
      "summary": "小红帽受妈妈嘱托，带着篮子前往外婆家。",
      "scenes": [...]
    }
  ]
}
```

### 扩展形式（部 → 幕 → 场景，超长故事使用）

```json
{
  "parts": [
    {
      "id": "part_1",
      "title": "第一部：建村",
      "summary": "何塞带领族人建立马孔多。",
      "acts": [...]
    }
  ]
}
```

有 `parts` 时不需要顶层 `acts`。短故事不使用 `parts`。

### Act

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `act_{N}` |
| title | string | 是 | 幕标题 |
| summary | string | 是 | 一句话概括本幕内容 |
| scenes | array | 是 | 场景摘要列表 |

### Scene（大纲中的摘要）

```json
{
  "id": "scene_003",
  "title": "狼的出现",
  "summary": "大灰狼在森林深处拦住小红帽，假装友善套话。",
  "location": "loc_forest_deep",
  "area": "area_bedroom",
  "characters": ["char_red", "char_wolf"],
  "time_of_day": "midday",
  "period": "1920年代初",
  "mood": "表面友善，暗藏危险",
  "narrative_weight": "turning_point",
  "thread": "主线",
  "narrative_mode": "present"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `scene_{NNN}`，全局递增 |
| title | string | 是 | 场景标题 |
| summary | string | 是 | 一句话概括 |
| location | string | 是 | 地点 ID |
| area | string | 否 | 子区域 ID（须属于该 location 的 areas） |
| characters | string[] | 是 | 出场角色 ID 列表 |
| time_of_day | string | 否 | 一天中的时段：morning / midday / afternoon / evening / night |
| period | string | 否 | 年代/时期标记，如 "1920年代初"、"二十年后" |
| mood | string | 否 | 场景整体情感氛围 |
| narrative_weight | string | 是 | 叙事功能权重：`"climax"` / `"turning_point"` / `"setup"` / `"transition"`。climax = 情绪最高点；turning_point = 故事走向发生不可逆变化；setup = 建立信息、铺垫冲突；transition = 连接两个重要时刻的过渡 |
| thread | string | 否 | 所属故事线名称。同名 thread 构成一条叙事线 |
| narrative_mode | string | 否 | 叙事模式：present（默认）/ flashback / flash_forward / parallel |

## act-{N}.json

幕内场景详情。N 从 1 开始。

```json
{
  "act_id": "act_1",
  "scenes": [...]
}
```

### Scene（详情）

在大纲字段基础上，增加：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| description | string | 是 | 场景环境描写（视觉细节、光影、氛围） |
| characters_present | string[] | 是 | 在场角色 ID 列表（同大纲的 characters） |
| character_states | object | 是 | key 为角色 ID，value 见下方 |
| location_state | object\|null | 否 | 地点在该场景的视觉状态。null 表示使用地点默认描述 |
| props_in_scene | string[] | 是 | 出现的道具 ID 列表 |
| prop_states | object\|null | 否 | key 为道具 ID，value 见下方。null 表示所有道具为默认状态 |
| beats | array | 是 | 叙事节拍序列 |

### CharacterState

```json
{
  "emotion": "从好奇到轻信",
  "appearance": "头发花白，身穿破旧的实验服"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| emotion | string | 角色在该场景的情绪 |
| appearance | string\|null | 角色当前外观。null 表示与 fixed_traits 一致 |

### LocationState

```json
{
  "appearance": "房间凌乱，被褥歪斜，地上散落着拖鞋",
  "lighting": "午后阳光从窗户斜照进来"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| appearance | string | 地点在该场景的视觉状态 |
| lighting | string | 光照条件 |

### PropState

```json
{
  "appearance": "篮子打开，蛋糕和葡萄酒摆在桌上",
  "held_by": "char_wolf"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| appearance | string | 道具在该场景的视觉状态 |
| held_by | string | 可选，当前持有者角色 ID（与默认 belongs_to 不同时使用） |

### Beat

两种类型：

**Action beat:**
```json
{
  "type": "action",
  "text": "小红帽弯腰摘了几朵野花，小心翼翼地放进篮子。"
}
```

**Dialogue beat:**
```json
{
  "type": "dialogue",
  "speaker": "char_red",
  "text": "外婆一定会喜欢这些花的！",
  "tone": "自言自语，开心"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | "action" \| "dialogue" | 是 | 节拍类型 |
| text | string | 是 | 动作描述或对白内容 |
| speaker | string | dialogue 时必填 | 角色 ID 或 "narrator" |
| tone | string | 否 | 说话的语气/情绪 |
