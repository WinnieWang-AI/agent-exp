# 图片生成 Prompt 写作规范

> 生成参考图前，用 ReadFile 加载本文件，确认 prompt 写作规则。

## 通用规则

所有 prompt 使用**英文**撰写（即使角色/场景名称是中文）。

### Prompt 结构

```
{style_prefix}, {subject description}, {composition}, {background/environment}, {lighting}
```

- **style_prefix**：从 meta.json 提取，放在 prompt 最前面，确保风格一致
- **subject description**：角色/场景/道具的具体视觉描述
- **composition**：构图指示（full body, close-up, wide shot 等）
- **background/environment**：背景描述
- **lighting**：光照描述

### Negative Prompt

从 meta.json 的 negative_prefix 开始，追加通用排除项：

```
{negative_prefix}, blurry, low quality, watermark, text, signature, deformed, extra limbs
```

## 角色 Prompt 要点

<example>
```
hand-drawn illustration, warm color palette, a 7-year-old girl with brown curly hair wearing a red velvet hooded cloak over a white cotton dress and black leather shoes, carrying a woven basket, full body front view, head to toe visible, centered, pure white background, soft even lighting
```
</example>

- **必须包含**：年龄/体型、发型发色、服装材质和颜色、标志性配饰
- **构图固定**：full body front view, head to toe visible, centered
- **背景固定**：pure white background
- 避免动作描述（参考图是静态展示，不是动态场景）
- 避免表情描述（保持中性表情，后续状态图再加表情）

## 场景 Prompt 要点

<example>
```
hand-drawn illustration, warm color palette, a cozy wooden cottage in a forest clearing, flower garden in front, smoke rising from chimney, red checkered curtains in windows, soft morning sunlight filtering through trees, no people, establishing shot
```
</example>

- **必须包含**：空间类型、关键视觉元素、光照/天气/时间
- **构图**：establishing shot 或 wide shot，展示整体环境
- **无角色**：场景图中不出现任何人物
- 光照要具体（"soft morning sunlight filtering through trees" 而非 "good lighting"）

## 道具 Prompt 要点

<example>
```
hand-drawn illustration, warm color palette, a woven rattan basket with red and white checkered cloth cover, slightly bulging with food inside, product shot, centered, pure white background, soft studio lighting
```
</example>

- **构图固定**：product shot, centered, pure white background
- 描述材质和状态细节
- 保持与角色图同样的画风

## 状态图 Prompt 补充

状态图在实体图基础上修改，prompt 需要：
- 保留实体的基础特征描述（不能丢失身份信息）
- 添加状态变化的描述（换装、受伤、光照变化等）
- 使用 reference_image_paths 传入实体图，确保一致性

<example>
角色状态图（受伤状态）：
```
hand-drawn illustration, warm color palette, a 7-year-old girl with brown curly hair wearing a torn red velvet hooded cloak, dirt on face, scratches on arms, white dress stained with mud, full body front view, head to toe visible, centered, pure white background, soft even lighting
```
</example>

<example>
场景状态图（夜晚状态）：
```
hand-drawn illustration, dark cool palette, a cozy wooden cottage in a forest clearing at night, warm light glowing from windows, full moon visible through bare tree branches, no people, establishing shot, moonlight and window light
```
</example>
