# Evaluation Guide: Prompt Semantic Validation

本指南用于在生成图片/视频之前，校验 prompt 是否准确表达了原始数据的语义。

---

## 评估流程

1. 调用方会提供 `prompt-review.json` 的路径，用 ReadFile 读取。
2. 同时读取 `${AGENT_DIR}/../video-creator/prompt-guide-refimage.md` 作为规范参考。
3. 对每条 prompt，逐项执行下方 Checklist 中的检查。
4. 输出结构化校验报告。

---

## 输入格式

`prompt-review.json` 包含：
```json
{
  "layer": 1,
  "prompts": [
    {
      "entity_id": "char_xxx",
      "type": "character | location | prop | character_appearance | location_state | prop_state",
      "prompt": "实际要传给 GenerateImage 的英文 prompt",
      "negative_prompt": "negative prompt",
      "aspect_ratio": "1:1",
      "reference_image_paths": [],
      "source": {
        "fixed_traits": "原始中文描述（实体图）",
        "visual": { "costume": "...", "hair": "...", "physical": "..." },
        "appearance": { "lighting": "...", "weather": "...", "condition": "...", "atmosphere": "..." }
      }
    }
  ]
}
```

`source` 字段包含 story-graph 中的原始数据，是校验 prompt 语义准确性的唯一依据。

---

## Checklist

### 1. 语义覆盖（最重要）

对比 `source` 中的原始描述和 `prompt` 的英文内容：

| 检查项 | PASS 标准 | FAIL 示例 |
|--------|----------|----------|
| **关键特征无遗漏** | source 中每个关键视觉特征在 prompt 中都有对应的英文描述 | source 写了"肩背常负弓囊"但 prompt 中完全没提 bow/quiver |
| **无臆造特征** | prompt 中的描述都能在 source 中找到依据，或是合理的视觉补充 | source 写了"眉目坚毅"但 prompt 写了 "gentle smile" |
| **状态差异准确**（仅 Layer 2）| 状态 prompt 准确描述了与实体基础外观的差异 | 状态是"斗篷歪斜、连衣裙沾泥"但 prompt 只写了 "same girl standing" |

**判断方法**：将 source 中的每个描述词/短语逐一检查，确认 prompt 中有语义等价的英文表达。允许合理的视觉细化（如"圆脸"→ "round face, rosy cheeks"），但不允许语义矛盾或遗漏。

### 2. 语义准确

| 检查项 | PASS 标准 | FAIL 示例 |
|--------|----------|----------|
| **翻译准确** | 中文描述到英文 prompt 的翻译语义正确 | "清秀端静"翻译为 "sexy and bold" |
| **无语义矛盾** | prompt 各部分之间不矛盾 | 同时写了 "elderly woman" 和 "youthful skin" |
| **类型匹配** | Character 有全身/白背景/居中，Location 无人物，Prop 白底特写 | Character prompt 缺少 "Full-body standing figure on plain white background" |

### 3. 规范合规

| 检查项 | PASS 标准 | FAIL 示例 |
|--------|----------|----------|
| **结构正确** | `{style_prefix}. {构图指令}, {外观描述}` | 构图指令放在末尾 |
| **style_prefix 在开头** | prompt 以 style_prefix 开头 | style_prefix 混在中间或缺失 |
| **光影禁词** | 参考图 prompt 中无 cinematic lighting, dramatic lighting, volumetric light, natural shadows, rim light, studio lighting, soft lighting, photorealistic | prompt 包含 "cinematic lighting" |
| **全英文** | prompt 全部为英文 | prompt 中夹杂中文 |
| **词数 ≤ 200** | style_prefix 计入，总词数不超过 200 | 超过 200 词 |
| **negative_prompt 不在 prompt 正文中** | negative 内容只在 negative_prompt 字段 | prompt 中写了 "no shadow, no dark background" |

### 4. reference_image_paths 正确性（仅 Layer 2）

| 检查项 | PASS 标准 | FAIL 示例 |
|--------|----------|----------|
| **实体图作为参考** | 状态图的 reference_image_paths 包含对应实体的参考图路径 | character_appearance 的 reference_image_paths 为空 |
| **based_on 父状态图** | 如果状态有 based_on，reference_image_paths 也包含父状态图路径 | 有 based_on 但未传父状态图 |

---

## 输出格式

```
## Prompt 语义校验报告

### 总览
- 总数: N
- PASS: X
- FAIL: Y

### 逐条结果

#### char_chang_e (character) — PASS
全部检查项通过。

#### char_hou_yi (character) — FAIL
- **语义覆盖 — 关键特征遗漏**: source 中"肩背常负弓囊（象征性）"在 prompt 中未体现，建议添加 "symbolic bow quiver over shoulder"
- **语义准确 — 翻译不当**: source 是"眉目坚毅"(determined expression)，prompt 写了 "gentle expression"，应改为 "resolute/determined expression"

#### appear_chang_e_plain (character_appearance) — FAIL
- **规范合规 — 光影禁词**: prompt 包含 "cinematic lighting"，参考图中应去掉
- **reference_image_paths**: 缺少实体图 "assets/images/char_chang_e.png"
```

**每个 FAIL 项必须给出具体的问题描述和修改建议。**
