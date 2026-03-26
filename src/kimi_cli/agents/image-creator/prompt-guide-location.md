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

在实体环境基础上表现光照/天气/氛围变化。**必须传入对应 Location 实体图作为 `reference_image_paths`**。

- **数据来源**：`appearance.lighting` + `appearance.weather` + `appearance.condition` + `appearance.atmosphere`
- **参考图**：对应 Location 实体图
- **比例**：1:1

<example>
- prompt: `"Same forest scene, god rays filtering through canopy, sunny day, gentle breeze, wildflowers along dirt path, butterflies, fairytale atmosphere, no people"`
- style: `"hand-drawn illustration, warm color palette, children's storybook style"`
- negative_prompt: `"dark, horror, oversaturated, people, characters"`
- reference_image_paths: `["assets/images/loc_forest.png"]`
</example>
