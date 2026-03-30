# Events Schema 定义

> 事件拆解前，用 ReadFile 加载本文件，确认字段格式。

导演的事件拆解产出为 `events.json`，存放在项目目录下。

## events.json

```json
{
  "events": [...],
  "event_sequence": [...]
}
```

### Event

<example>
```json
{
  "id": "evt_farewell",
  "title": "告别出发",
  "description": "妈妈将装满食物的篮子递给小红帽，叮嘱路上小心不要和陌生人说话。小红帽接过篮子，蹦蹦跳跳出了家门。",
  "source_scenes": ["scene_001"],
  "location": "loc_home",
  "area": null,
  "time_of_day": "morning",
  "characters": ["char_red", "char_mother"],
  "props": ["prop_basket"],
  "interactions": [
    {
      "between": ["char_mother", "char_red"],
      "style": "妈妈弯腰递篮子，语气温柔叮嘱；小红帽仰头认真听"
    }
  ],
  "state_changes": [
    {
      "entity": "char_red",
      "aspect": "emotion",
      "detail": "从平静到兴奋期待"
    }
  ],
  "dialogues": [
    {
      "speaker": "char_mother",
      "text": "路上不要和陌生人说话",
      "tone": "温柔叮嘱"
    },
    {
      "speaker": "char_red",
      "text": "我知道了，妈妈！",
      "tone": "开心"
    }
  ],
  "mood": "温馨、充满期待"
}
```
</example>

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `evt_{descriptive_name}`，全局唯一，英文小写+下划线 |
| title | string | 是 | 事件标题（简短，中文） |
| description | string | 是 | 事件的完整描述，包含关键动作和视觉细节。应足够具体，让下游不需要回查原始剧本 |
| source_scenes | string[] | 是 | 来源场景 ID 列表。一个事件可能合并多个场景的 beats，也可能只来自一个场景的部分 beats |
| location | string | 是 | 地点 ID，必须在 entities.json 中存在 |
| area | string\|null | 否 | 子区域 ID，须属于该 location 的 areas |
| time_of_day | string\|null | 否 | morning / midday / afternoon / evening / night |
| characters | string[] | 是 | 参与角色 ID 列表，必须在 entities.json 中存在 |
| props | string[] | 是 | 出现的道具 ID 列表，必须在 entities.json 中存在。无道具时为空数组 |
| interactions | array | 否 | 角色间的互动描述。只在有明确互动时填写 |
| state_changes | array | 否 | 该事件引发的实体状态变化。只记录剧本中明确描写的变化 |
| dialogues | array | 否 | 该事件中的对白。从剧本 beats 中提取，不修改台词内容 |
| mood | string | 是 | 事件的情感氛围 |

### Interaction

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| between | string[] | 是 | 互动双方的角色 ID |
| style | string | 是 | 互动方式的视觉描述（肢体语言、空间关系、情感张力） |

### StateChange

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| entity | string | 是 | 发生变化的实体 ID（角色/道具/场景） |
| aspect | string | 是 | 变化维度：emotion / appearance / lighting / condition / held_by |
| detail | string | 是 | 变化描述（从什么到什么） |

### Dialogue

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| speaker | string | 是 | 角色 ID 或 "narrator" |
| text | string | 是 | 对白内容，原样保留编剧的台词 |
| tone | string | 否 | 语气/情绪 |

### EventSequence

事件间的时序关系。

<example>
```json
{
  "from": "evt_farewell",
  "to": "evt_forest_walk",
  "type": "THEN"
}
```
</example>

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| from | string | 是 | 前驱事件 ID |
| to | string | 是 | 后继事件 ID |
| type | string | 是 | 关系类型：THEN（顺序）/ PARALLEL（同时发生） |

**THEN**：from 结束后 to 开始。大多数事件都是 THEN 关系。
**PARALLEL**：from 和 to 在同一时间段内同时发生（如"小红帽摘花"和"大灰狼赶往外婆家"）。

每个事件（除第一个）必须作为至少一条边的 `to` 出现，保证所有事件都连入时序图。
