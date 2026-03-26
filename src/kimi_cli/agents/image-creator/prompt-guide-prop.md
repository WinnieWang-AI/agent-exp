# Prompt Guide: 道具参考图

**核心要求：生成用于影视中道具参考图的Prompt。要准确描述道具的特征。图片要求为纯白背景，道具完整居中的参考图。**

## 参数规则

1. prompt 只写道具描述，风格通过 `style` 参数传入，negative_prefix 通过 `negative_prompt` 参数传入
2. style 参数需从 style_prefix 中过滤掉光影词和构图暗示词（同人物参考图规则）
3. 所有 prompt 用英文，≤ 200 词

---

## 第 1 层：Prop 实体图

生成白底道具特写，仅为跨镜头需要一致性的重要道具生成。

- **数据来源**：`fixed_traits`
- **比例**：1:1

**参数**：
- prompt: `"Product closeup on white background. {道具描述}"`
- style: `"{过滤后的 style_prefix}"`
- negative_prompt: `"{negative_prefix}, hands, person, shadow"`
- aspect_ratio: `"1:1"`

<example>
- prompt: `"Product closeup on white background. A round woven rattan basket, beige, single arched handle, detailed weave texture."`
- style: `"hand-drawn illustration, warm color palette, children's storybook style"`
- negative_prompt: `"dark, horror, hands, person, shadow"`
</example>

---

## 第 2 层：PropState 状态图

在实体道具基础上表现外观变化。**必须传入对应 Prop 实体图作为 `reference_image_paths`**。

- **数据来源**：`appearance.visual` + `appearance.condition`
- **参考图**：对应 Prop 实体图
- **比例**：1:1

<example>
- prompt: `"Same woven basket on white background, now covered with a red-white checkered cloth, visibly full and bulging, cloth tucked neatly around edges, perfect condition."`
- style: `"hand-drawn illustration, warm color palette, children's storybook style"`
- negative_prompt: `"dark, horror, hands, person, shadow"`
- reference_image_paths: `["assets/images/prop_basket.png"]`
</example>
