# Prompt Guide: 人物参考图

**核心要求：生成用于影视中角色参考图的Prompt。要准确描述人物的特征、身份背景等。图片要求为纯白背景，角色正面全身的参考图。**

## 参数规则

1. prompt 只写构图指令 + 外观描述，风格通过 `style` 参数传入，negative_prefix 通过 `negative_prompt` 参数传入
2. style 参数直接使用 style_prefix，保留其中所有风格词（画风、色调、质感、光影等）
3. 所有 prompt 用英文，≤ 200 词

---

## 第 1 层：Character 实体图

生成白色背景的人物全身参考图。

- **数据来源**：`fixed_traits`
- **比例**：1:1

将 `fixed_traits` 翻译为英文，补充从头到脚的视觉细节。**上半身和下半身都要描述**（面部、发型、上衣、下装、鞋），避免模型注意力偏上半身导致截断。

**参数**：
- prompt: `"Full-body character reference, white background. {人物外观描述，从头到脚}"`
- style: `"{过滤后的 style_prefix}"`
- negative_prompt: `"{negative_prefix}, cropped, half body, shadow, gradient background"`
- aspect_ratio: `"1:1"`

<example>
数据：
```json
{"id": "char_red", "fixed_traits": "7-8岁小女孩，圆脸，大眼睛，棕色卷发，身材娇小"}
```
style_prefix: `"hand-drawn illustration, warm color palette, children's storybook style"`

- prompt: `"Full-body character reference, white background. A 7-8 year old girl, petite build, round face with rosy cheeks, large brown eyes, curly brown shoulder-length hair. Wearing a simple cream-colored dress with short sleeves, bare feet."`
- style: `"hand-drawn illustration, warm color palette, children's storybook style"`
- negative_prompt: `"dark, horror, oversaturated, cropped, half body, shadow, gradient background"`
</example>

<example>
数据：
```json
{"id": "char_houyi", "fixed_traits": "东方男性，二十五至三十岁，身材高大健壮，英气外貌，背负长弓，古代猎人武士气质"}
```
style_prefix: `"cinematic realistic style, Chinese myth-inspired, subtle cool tones, high dynamic range, fine textures, volumetric lighting, subtle film grain"`

- prompt: `"Full-body character reference, white background. Ancient Chinese warrior-hunter, tall and muscular man in his late twenties, handsome face with bold determined expression, wearing traditional ancient Chinese hunter garments, a long recurve bow strapped across his back, standing in neutral pose."`
- style: `"cinematic realistic style, Chinese myth-inspired, subtle cool tones, high dynamic range, fine textures, volumetric lighting, subtle film grain"`
- negative_prompt: `"cartoon, low detail, cropped, half body, shadow, gradient background"`
</example>

---

## 第 2 层：CharacterAppearance 状态图

在实体身份基础上表现装扮变化。**必须传入对应 Character 实体图作为 `reference_image_paths`**。

- **数据来源**：`visual.costume` + `visual.hair` + `visual.physical`
- **参考图**：对应 Character 实体图 + `based_on` 父状态图（如有）
- **比例**：1:1

只描写与实体基础的**差异**（参考图已传入，不需要重复基础特征）。

<example>
```json
{
  "id": "appear_red_neat",
  "entity": "char_red",
  "visual": {"costume": "红色丝绒斗篷，白色连衣裙，棕色小皮靴", "hair": "棕色卷发散落在斗篷里"}
}
```

- prompt: `"Full-body character reference, white background. Same girl now wearing a red velvet hooded cloak over a white dress, brown leather ankle boots. Curly hair tucked inside the hood, carrying a woven basket in her right hand."`
- style: `"hand-drawn illustration, warm color palette, children's storybook style"`
- negative_prompt: `"dark, horror, oversaturated, cropped, half body, shadow, gradient background"`
- reference_image_paths: `["{project_dir}/assets/images/char_red.png"]`
</example>

<example>
基于前一个状态变化（`based_on`）：
```json
{
  "id": "appear_red_disheveled",
  "entity": "char_red",
  "visual": {"costume": "红色斗篷歪斜，连衣裙下摆沾泥", "hair": "卷发散乱，有树叶碎屑", "physical": "脸颊通红，额头有汗"},
  "based_on": "appear_red_neat"
}
```

- prompt: `"Full-body character reference, white background. Same girl, red cloak hanging askew off one shoulder, white dress hem stained with mud. Hair disheveled with leaf fragments tangled in curls, flushed cheeks, forehead glistening with sweat. Muddy boots."`
- style: `"hand-drawn illustration, warm color palette, children's storybook style"`
- negative_prompt: `"dark, horror, oversaturated, cropped, half body, shadow, gradient background"`
- reference_image_paths: `["{project_dir}/assets/images/char_red.png", "{project_dir}/assets/images/appear_red_neat.png"]`
</example>

---

## 常见错误

| 错误 | 后果 | 正确做法 |
|---|---|---|
| prompt 只描述上半身特征 | 模型注意力偏上半身，生成半身图 | 从头到脚都要描述（面部、上衣、下装、鞋） |
| style_prefix 中的构图暗示词 | 部分词可能暗示半身构图 | 确保 prompt 中有明确的全身构图指令（如 Full-body standing figure）来覆盖 |
| 角色穿白衣 + 白背景 | 衣服和背景融为一体 | negative_prompt 加 `low contrast`；prompt 中强调衣服边缘细节或纹理 |
