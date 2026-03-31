# Shots Schema 定义

> 镜头设计前，用 ReadFile 加载本文件，确认字段格式。

导演的镜头设计产出为 `shots.json`，存放在项目目录下。

## shots.json

```json
{
  "shots": [...],
  "total_duration_seconds": 60
}
```

### Shot

<example>
```json
{
  "id": "evt_farewell_shot_1",
  "event_id": "evt_farewell",
  "order": 1,
  "shot_type": "wide",
  "angle": "eye_level",
  "movement": "static",
  "focus_on": ["appear_red_neat", "lstate_home_morning"],
  "content": "小屋门前，妈妈弯腰将篮子递给小红帽，晨光从左侧洒入",
  "duration_seconds": 5,
  "transition_in": "cut",
  "transition_out": "cut",
  "dialogues": [
    {
      "speaker": "char_mother",
      "text": "路上不要和陌生人说话",
      "tone": "温柔叮嘱"
    }
  ],
  "sfx": ["晨鸟鸣叫", "篮子提起的藤编声"]
}
```
</example>

**视觉字段：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 格式 `{event_id}_shot_{N}`，全局唯一 |
| event_id | string | 是 | 所属事件 ID，必须在 events.json 中存在 |
| order | int | 是 | 在该事件内的顺序编号，从 1 开始 |
| shot_type | string | 是 | 景别，见下方词表 |
| angle | string | 是 | 角度，见下方词表 |
| movement | string | 是 | 运镜，见下方词表 |
| focus_on | string[] | 是 | 画面聚焦的状态 ID 列表（CharacterAppearance / LocationState / PropState 的 ID），必须在 states.json 中存在 |
| content | string | 是 | 画面内容描述。具体描写这个镜头里观众看到什么：角色动作、空间关系、光影、关键细节。必须足够具体让下游生成视频，不需要回查其他文件 |
| duration_seconds | number | 是 | 时长（秒）。最小 3 秒，最大 10 秒。超过 10 秒的镜头需要拆分 |
| transition_in | string | 是 | 入场转场方式 |
| transition_out | string | 是 | 出场转场方式 |

**音频字段：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| dialogues | array | 否 | 该 shot 中的对白列表。从 events.json 的 dialogues 中分配过来，不修改台词内容。无对白时省略 |
| sfx | string[] | 否 | 音效提示列表。只列关键的环境音或动作音，不需要穷举所有声音 |

**Dialogue（shot 内对白）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| speaker | string | 是 | 角色 ID 或 "narrator" |
| text | string | 是 | 对白内容，原样保留 |
| tone | string | 否 | 语气/情绪 |

### 词表

**shot_type（景别）：**

| 值 | 说明 | 典型用途 |
|----|------|----------|
| extreme_wide | 大远景 | 建立环境、展示空间规模 |
| wide | 全景 | 交代场景、展示人物与环境的关系 |
| medium | 中景 | 日常叙事、多人互动 |
| medium_close | 中近景 | 对话、表情与肢体并重 |
| close_up | 特写 | 强调表情、情绪、关键道具 |
| extreme_close | 大特写 | 眼神、手部动作、微表情 |
| detail_insert | 细节插入 | 关键道具、文字、符号 |
| over_shoulder | 过肩 | 对话场景、建立角色空间关系 |
| pov | 主观视角 | 代入角色视角 |

**angle（角度）：**

| 值 | 说明 | 典型用途 |
|----|------|----------|
| eye_level | 平视 | 中性、日常 |
| low_angle | 仰角 | 强势、威压、高大 |
| high_angle | 俯角 | 弱势、渺小、俯瞰 |
| bird_eye | 鸟瞰 | 全局展示、地图感 |
| dutch_angle | 荷兰角 | 不安、失衡、紧张 |
| worm_eye | 虫视角 | 极端仰视、震撼 |

**movement（运镜）：**

| 值 | 说明 | 典型用途 |
|----|------|----------|
| static | 固定 | 稳定叙事、对话 |
| pan_left / pan_right | 左/右摇 | 水平扫视环境、跟随 |
| tilt_up / tilt_down | 上/下摇 | 纵向展示、揭示 |
| push_in | 推进 | 聚焦、强调、紧张感递增 |
| pull_out | 拉远 | 揭示全景、释放张力 |
| tracking | 跟拍 | 跟随运动中的角色 |
| handheld_shake | 手持晃动 | 紧张、混乱、纪实感 |
| crane_up / crane_down | 升/降 | 史诗感、情绪升降 |
| slow_360_orbit | 慢速环绕 | 戏剧化、重要时刻 |
| zoom_in / zoom_out | 变焦推/拉 | 突然聚焦或揭示 |

**transition（转场）：**

| 值 | 说明 | 典型用途 |
|----|------|----------|
| cut | 硬切 | 默认，大多数情况 |
| fade_in | 淡入 | 开场、新段落开始 |
| fade_out | 淡出 | 结束、段落收束 |
| dissolve | 溶解 | 时间流逝、回忆、梦境 |
| wipe | 划变 | 场景平行切换 |

### shot_order

顶层字段，`string[]` 类型。定义所有 shot 的最终播放顺序。

```json
{
  "shots": [...],
  "shot_order": ["evt_farewell_shot_1", "evt_farewell_shot_2", "evt_forest_shot_1", ...],
  "total_duration_seconds": 60
}
```

**规则：**
- 包含 `shots` 数组中所有 shot 的 ID，不遗漏、不重复
- 同一 event 内的 shot 按 `order` 字段顺序排列
- 不同 event 之间的排列由 `event_sequence` 决定：
  - `THEN` 关系：前一个 event 的所有 shot 排完后，再排后一个 event
  - `PARALLEL` 关系：两个 event 的 shot 交叉排列（导演决定交叉节奏，如 A1-B1-A2-B2 或 A1-A2-B1-B2）
- 这是最终播放顺序，下游（摄影、剪辑）直接按此顺序执行，不再解析 event_sequence DAG

### total_duration_seconds

所有 shot 的 duration_seconds 之和。必须与 meta.json 中的目标时长匹配（允许 ±10% 偏差）。
