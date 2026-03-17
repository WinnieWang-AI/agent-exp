# Prompt Guide: Reference Images (Phase 2)

本文件提供参考图生成的 prompt 写作规范和示例。Phase 2 开始前请阅读。

所有 prompt **必须用英文**写（模型对英文 prompt 效果更好）。`style_prefix` 放在 prompt 最前面，`negative_prefix` 通过 `negative_prompt` 参数传入（不要拼进 prompt 正文，避免 provider 重复追加）。

---

## 第 1 层：实体参考图

目标：建立身份锚点。**纯展示、无叙事、无动作。**

### Character 实体图

**数据来源**：`fixed_traits`
**要求**：全身可见、纯白背景、居中站立、面朝镜头或 3/4 侧面
**比例**：3:4

将 `fixed_traits` 扩展为具体的视觉描述，补充合理细节（体型比例、五官特征、肤色）。

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
"hand-drawn illustration, warm color palette, children's storybook style. Full-body character reference sheet of a 7-8 year old little girl, round face with rosy cheeks, large expressive brown eyes, curly brown hair falling to her shoulders, petite build, standing upright facing the viewer, plain white background, centered composition, no accessories, neutral pose"

参数：
- style: ""（已在 prompt 中包含 style_prefix，不要重复传入）
- negative_prompt: "photorealistic, dark, horror, oversaturated"
- aspect_ratio: "3:4"
- reference_image_paths: []
</example>

### Location 实体图

**数据来源**：`fixed_traits`
**要求**：纯环境、无任何角色或人物出现
**比例**：16:9

<example>
story-graph 数据：
```json
{
  "id": "loc_forest",
  "fixed_traits": "茂密的欧洲针叶林，高大的松树和橡树"
}
```

prompt:
"hand-drawn illustration, warm color palette, children's storybook style. A dense European coniferous forest, tall pine and oak trees with thick canopy, dappled sunlight filtering through leaves, moss-covered ground, no people, no characters, empty serene woodland, wide establishing view"

参数：
- negative_prompt: "photorealistic, dark, horror, oversaturated, people, characters, figures"
- aspect_ratio: "16:9"
- reference_image_paths: []
</example>

### Prop 实体图

**数据来源**：`fixed_traits`
**要求**：白底特写、物品居中、仅重要道具才生成
**比例**：1:1

<example>
story-graph 数据：
```json
{
  "id": "prop_basket",
  "fixed_traits": "圆形藤编手提篮，米色，单拱形提手"
}
```

prompt:
"hand-drawn illustration, warm color palette, children's storybook style. A round woven rattan hand basket, beige color, single arched handle, detailed weave texture, centered on plain white background, product-style closeup, no hands, no other objects"

参数：
- negative_prompt: "photorealistic, dark, horror, oversaturated, hands, person"
- aspect_ratio: "1:1"
- reference_image_paths: []
</example>

---

## 第 2 层：状态参考图

目标：在实体身份基础上表现具体装扮/氛围变化。**必须传入对应实体图作为 reference**。

### CharacterAppearance 状态图

**数据来源**：`visual.costume` + `visual.hair` + `visual.physical`
**参考图**：对应 Character 实体图 + `based_on` 父状态图（如有）
**比例**：3:4

重点描写与实体基础的**差异**——穿了什么衣服、发型变化、携带什么道具。不需要重复 `fixed_traits` 中的基础特征（参考图已经传入了）。

<example>
story-graph 数据：
```json
{
  "id": "appear_red_neat",
  "entity": "char_red",
  "phase": "整洁出行装",
  "visual": {
    "costume": "红色丝绒斗篷，白色连衣裙，棕色小皮靴",
    "hair": "棕色卷发散落在斗篷里",
    "physical": "健康，红润",
    "props": ["prop_hood", "prop_basket"]
  }
}
```

prompt:
"hand-drawn illustration, warm color palette, children's storybook style. Full-body view, the same girl wearing a bright red velvet hooded cloak over a white dress, small brown leather boots, curly brown hair tucked loosely inside the cloak hood, healthy rosy complexion, carrying a woven basket in one hand, standing upright, plain white background, centered"

参数：
- negative_prompt: "photorealistic, dark, horror, oversaturated"
- aspect_ratio: "3:4"
- reference_image_paths: ["assets/images/char_red.png"]
</example>

<example>
另一个状态（基于前一个状态变化）：
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
"hand-drawn illustration, warm color palette, children's storybook style. Full-body view, the same girl with her red cloak askew and partially slipping off one shoulder, white dress hem stained with mud, curly brown hair disheveled with small leaf fragments caught in it, flushed red cheeks, beads of sweat on forehead, standing, plain white background, centered"

参数：
- negative_prompt: "photorealistic, dark, horror, oversaturated"
- aspect_ratio: "3:4"
- reference_image_paths: ["assets/images/char_red.png", "assets/images/appear_red_neat.png"]
  （实体图 + 父状态图，让模型看到"之前的样子"再生成"变化后的样子"）
</example>

### LocationState 状态图

**数据来源**：`appearance.lighting` + `appearance.weather` + `appearance.condition` + `appearance.atmosphere`
**参考图**：对应 Location 实体图
**比例**：16:9

将 appearance 的四个子字段融合成一段连贯的环境描写。

<example>
story-graph 数据：
```json
{
  "id": "lstate_forest_bright",
  "entity": "loc_forest",
  "phase": "阳光林间小路",
  "appearance": {
    "lighting": "丁达尔光束",
    "weather": "晴，微风",
    "condition": "野花，蝴蝶",
    "atmosphere": "童话美好"
  }
}
```

prompt:
"hand-drawn illustration, warm color palette, children's storybook style. The same forest with dramatic god rays (Tyndall effect) streaming through the tree canopy, clear sunny sky, gentle breeze rustling leaves, a winding dirt path lined with colorful wildflowers, butterflies fluttering in the warm light, enchanting fairytale atmosphere, no people, no characters"

参数：
- negative_prompt: "photorealistic, dark, horror, oversaturated, people, characters"
- aspect_ratio: "16:9"
- reference_image_paths: ["assets/images/loc_forest.png"]
</example>

### PropState 状态图

**数据来源**：`appearance.visual` + `appearance.condition`
**参考图**：对应 Prop 实体图
**比例**：1:1

<example>
story-graph 数据：
```json
{
  "id": "pstate_basket_full",
  "entity": "prop_basket",
  "phase": "装满完好",
  "appearance": {
    "visual": "藤篮盖着红白格子布，鼓鼓的",
    "condition": "完好"
  }
}
```

prompt:
"hand-drawn illustration, warm color palette, children's storybook style. The same woven rattan basket, now covered with a red-and-white checkered cloth, visibly full and bulging, the cloth neatly tucked around the edges, basket in perfect condition, centered on plain white background, closeup"

参数：
- negative_prompt: "photorealistic, dark, horror, oversaturated, hands, person"
- aspect_ratio: "1:1"
- reference_image_paths: ["assets/images/prop_basket.png"]
</example>

---

## 写作要点

1. **style_prefix 放在 prompt 开头**，不要通过 `style` 参数重复传入（Gemini provider 会再追加一次导致重复）。
2. **negative_prefix 通过 `negative_prompt` 参数传入**，不要拼进 prompt 正文。环境图额外加 "people, characters" 到 negative prompt。
3. **实体图 prompt 要具体**：把中文 `fixed_traits` 翻译为英文后，补充合理的视觉细节（肤色、体型比例、五官形状等），不要只做直译。
4. **状态图重点描写变化**：reference_image_paths 已经传入了实体图，不需要重复基础特征，着重描写与基础状态的差异。
5. **`based_on` 状态的 reference_image_paths**：同时传入实体图和父状态图，让模型理解"从什么状态变化而来"。
6. **保持背景干净**：实体图和状态图都应该是纯白/纯色背景（环境图除外），确保后续作为视频参考时不引入背景干扰。
