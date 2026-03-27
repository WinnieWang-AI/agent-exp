# Prompt Guide: 环境参考图

**核心要求：生成用于影视中环境参考图的Prompt。要准确描述环境的特征。**

## 参数规则

1. prompt 只写环境描述，风格通过 `style` 参数传入，negative_prefix 通过 `negative_prompt` 参数传入
2. style 参数需从 style_prefix 中过滤掉光影词和构图暗示词（同人物参考图规则）
3. 所有 prompt 用英文，≤ 200 词

---

## 第 1 层：Location 实体图

生成纯环境参考图，无人物。

- **数据来源**：`fixed_traits`
- **比例**：1:1

**参数**：
- prompt: `"{环境描述}, no people, wide establishing view"`
- style: `"{过滤后的 style_prefix}"`
- negative_prompt: `"{negative_prefix}, people, characters, figures"`
- aspect_ratio: `"1:1"`

<example>
- prompt: `"Dense European coniferous forest, tall pine and oak trees, thick canopy, moss-covered ground, wide establishing view, no people"`
- style: `"hand-drawn illustration, warm color palette, children's storybook style"`
- negative_prompt: `"dark, horror, oversaturated, people, characters, figures"`
</example>

---

## 第 2 层：LocationState 状态图

在实体环境基础上表现**特定取景区域**的光照/天气/氛围。**必须传入对应 Location 实体图作为 `reference_image_paths`**。

- **数据来源**：`framing`（取景范围）+ `appearance`（光照/天气/氛围）
- **参考图**：对应 Location 实体图
- **比例**：1:1

**取景约束（关键）**：
- prompt **只描述** `framing.visible_regions` 中列出的区域——这是画面的取景范围
- `framing.excluded_elements` 中的元素必须加入 negative_prompt——这些是不应出现在画面中的内容
- `framing.viewpoint` 提供取景角度/方向的参考

**参数**：
- prompt: `"{visible_regions 中区域的环境描述}, {光照/天气/氛围描述}, no people, {viewpoint 视角描述}"`
- style: `"{过滤后的 style_prefix}"`
- negative_prompt: `"{negative_prefix}, people, characters, figures, {excluded_elements 中的每个元素}"`
- reference_image_paths: `["{project_dir}/assets/images/{location_entity_id}.png"]`
- aspect_ratio: `"1:1"`

<example>
数据：
```json
{
  "id": "lstate_forest_bright",
  "entity": "loc_forest",
  "framing": {
    "visible_regions": ["入口小径"],
    "viewpoint": "小径前方，面朝密林方向",
    "excluded_elements": ["橡树旁空地", "小溪"]
  },
  "appearance": {
    "lighting": "丁达尔光束",
    "weather": "晴，微风",
    "condition": "野花，蝴蝶",
    "atmosphere": "童话美好"
  }
}
```

- prompt: `"Forest entrance trail, narrow dirt path leading into dense woods, god rays filtering through canopy, sunny day, gentle breeze, wildflowers along path, butterflies, fairytale atmosphere, view looking forward into the forest, no people"`
- style: `"hand-drawn illustration, warm color palette, children's storybook style"`
- negative_prompt: `"dark, horror, oversaturated, people, characters, figures, oak tree clearing, creek, stream"`
- reference_image_paths: `["{project_dir}/assets/images/loc_forest.png"]`
</example>

<example>
数据（龟兔赛跑 - 起跑线取景）：
```json
{
  "id": "lstate_start",
  "entity": "loc_racecourse",
  "framing": {
    "visible_regions": ["起跑线"],
    "viewpoint": "正面，面朝赛道方向",
    "excluded_elements": ["终点线", "奖杯台"]
  },
  "appearance": {
    "lighting": "清晨阳光",
    "weather": "晴朗",
    "condition": "起跑线标识，围观动物旗帜",
    "atmosphere": "热闹欢快"
  }
}
```

- prompt: `"Racing start line area, morning sunlight, clear sky, starting line markings on grass, colorful spectator flags, cheerful atmosphere, view facing forward along the racecourse, no people"`
- style: `"hand-drawn illustration, warm color palette, children's storybook style"`
- negative_prompt: `"dark, horror, oversaturated, people, characters, figures, finish line, trophy podium"`
- reference_image_paths: `["{project_dir}/assets/images/loc_racecourse.png"]`
</example>
