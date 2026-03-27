# Prompt Guide: Reference Images (Phase 2)

本文件提供参考图生成的 prompt 写作规范和示例。Phase 2 开始前请阅读。

---

## 核心规则

1. **Prompt 总长度 ≤ 200 词**（style_prefix 计入）。利用充足的词数详细描述外观特征，但避免无意义的堆砌。
2. **结构固定**：`{style_prefix}. {构图指令}, {外观描述}`。构图指令紧跟 style_prefix，不要放到末尾。
3. **style_prefix 放在 prompt 开头**，不要通过 `style` 参数重复传入。
4. **negative_prefix 通过 `negative_prompt` 参数传入**，不要拼进 prompt 正文。
5. **style_prefix 直接使用**，保留其中所有风格词（画风、色调、质感、光影等）。
6. **所有 prompt 用英文**。

---

## 第 1 层：实体参考图

目标：建立身份锚点。**纯展示、无叙事、无动作。**

### Character 实体图

**数据来源**：`fixed_traits`
**比例**：1:1

将 `fixed_traits` 翻译为英文并补充视觉细节（体型、五官、肤色）。

**Prompt 结构**：
```
{style_prefix}. Full-body standing figure on plain white background, centered, {外观描述}, neutral pose
```

<example>
story-graph 数据：
```json
{
  "id": "char_red",
  "fixed_traits": "7-8岁小女孩，圆脸，大眼睛，棕色卷发，身材娇小"
}
```
style_prefix: "hand-drawn illustration, warm color palette, children's storybook style"

prompt:
"hand-drawn illustration, warm color palette, children's storybook style. Full-body standing figure on plain white background, centered, 7-8 year old girl, round face, rosy cheeks, large brown eyes, curly brown shoulder-length hair, petite build, neutral pose"

参数：
- negative_prompt: "dark, horror, oversaturated, shadow, gradient background"
- aspect_ratio: "1:1"
- reference_image_paths: []
</example>

<example>
写实风格：
```json
{
  "id": "char_houyi",
  "fixed_traits": "高大健壮的古代射手，肩背肌肉发达，神情坚毅"
}
```
style_prefix: "realistic, high detail, Chinese myth aesthetic"
（style_prefix 直接使用，保留所有风格词）

prompt:
"realistic, high detail, Chinese myth aesthetic. Full-body standing figure on plain white background, centered, tall muscular ancient Chinese archer, broad shoulders, determined expression, hair in topknot, simple linen tunic with leather arm guards, neutral pose"

参数：
- negative_prompt: "cartoon, low detail, shadow, gradient background"
- aspect_ratio: "1:1"
- reference_image_paths: []
</example>

### Location 实体图

**数据来源**：`fixed_traits`
**要求**：无任何角色或人物
**比例**：1:1

<example>
prompt:
"hand-drawn illustration, warm color palette, children's storybook style. Dense European coniferous forest, tall pine and oak trees, thick canopy, moss-covered ground, no people, wide establishing view"

参数：
- negative_prompt: "dark, horror, oversaturated, people, characters, figures"
- aspect_ratio: "1:1"
- reference_image_paths: []
</example>

### Prop 实体图

**数据来源**：`fixed_traits`
**要求**：白底特写、居中、仅重要道具才生成
**比例**：1:1

<example>
prompt:
"hand-drawn illustration, warm color palette, children's storybook style. Round woven rattan basket, beige, single arched handle, detailed weave texture, centered on plain white background, product closeup"

参数：
- negative_prompt: "dark, horror, hands, person, shadow"
- aspect_ratio: "1:1"
- reference_image_paths: []
</example>

---

## 第 2 层：状态参考图

目标：在实体身份基础上表现装扮/氛围变化。**必须传入对应实体图作为 reference**。

### CharacterAppearance 状态图

**数据来源**：`visual.costume` + `visual.hair` + `visual.physical`
**参考图**：对应 Character 实体图 + `based_on` 父状态图（如有）
**比例**：1:1

只描写与实体基础的**差异**（参考图已传入，不需要重复基础特征）。

<example>
```json
{
  "id": "appear_red_neat",
  "entity": "char_red",
  "phase": "整洁出行装",
  "visual": {
    "costume": "红色丝绒斗篷，白色连衣裙，棕色小皮靴",
    "hair": "棕色卷发散落在斗篷里"
  }
}
```

prompt:
"hand-drawn illustration, warm color palette, children's storybook style. Full-body standing figure on plain white background, centered, same girl now wearing red velvet hooded cloak over white dress, brown leather boots, curly hair tucked inside hood, carrying woven basket"

参数：
- negative_prompt: "dark, horror, oversaturated, shadow, gradient background"
- aspect_ratio: "1:1"
- reference_image_paths: ["{project_dir}/assets/images/char_red.png"]
</example>

<example>
基于前一个状态变化（`based_on`）：
```json
{
  "id": "appear_red_disheveled",
  "entity": "char_red",
  "phase": "逃跑后凌乱",
  "visual": {
    "costume": "红色斗篷歪斜，连衣裙下摆沾泥",
    "hair": "卷发散乱，有树叶碎屑",
    "physical": "脸颊通红，额头有汗"
  },
  "based_on": "appear_red_neat"
}
```

prompt:
"hand-drawn illustration, warm color palette, children's storybook style. Full-body standing figure on plain white background, centered, same girl with red cloak askew, dress hem mud-stained, hair disheveled with leaf fragments, flushed cheeks, sweating"

参数：
- negative_prompt: "dark, horror, oversaturated, shadow, gradient background"
- aspect_ratio: "1:1"
- reference_image_paths: ["{project_dir}/assets/images/char_red.png", "{project_dir}/assets/images/appear_red_neat.png"]
</example>

### LocationState 状态图

**数据来源**：`framing`（取景范围）+ `appearance.lighting` + `appearance.weather` + `appearance.condition` + `appearance.atmosphere`
**参考图**：对应 Location 实体图
**比例**：1:1

**取景约束**：如果 `framing` 存在，prompt 只描述 `framing.visible_regions` 中的区域环境，`framing.excluded_elements` 中的元素加入 negative_prompt。

<example>
prompt:
"hand-drawn illustration, warm color palette, children's storybook style. Forest entrance trail, god rays through canopy, sunny, gentle breeze, wildflowers along dirt path, butterflies, fairytale atmosphere, view looking forward into the forest, no people"

参数：
- negative_prompt: "dark, horror, oversaturated, people, characters, oak tree clearing, creek"
- aspect_ratio: "1:1"
- reference_image_paths: ["{project_dir}/assets/images/loc_forest.png"]
</example>

### PropState 状态图

**数据来源**：`appearance.visual` + `appearance.condition`
**参考图**：对应 Prop 实体图
**比例**：1:1

<example>
prompt:
"hand-drawn illustration, warm color palette, children's storybook style. Same woven basket covered with red-white checkered cloth, visibly full, cloth tucked neatly, perfect condition, plain white background, closeup"

参数：
- negative_prompt: "dark, horror, hands, person, shadow"
- aspect_ratio: "1:1"
- reference_image_paths: ["{project_dir}/assets/images/prop_basket.png"]
</example>

---

## 常见错误

| 错误 | 后果 | 正确做法 |
|---|---|---|
| 构图指令放在末尾 | 模型注意力不足，脚被截断或背景脏 | `Full-body standing figure on plain white background` 紧跟 style_prefix |
| style_prefix 中的构图暗示词 | 部分词可能暗示半身构图 | 确保 prompt 中有明确的全身构图指令来覆盖 |
| 角色穿白衣 + 白背景 | 衣服和背景融为一体 | negative_prompt 加 `low contrast`；prompt 中强调衣服的边缘细节或纹理 |
| 否定描述如 `no saddle`, `no accessories` | 模型可能反而生成这些东西 | 直接不提，或用肯定描述替代 |
