# Evaluation Guide: Prompt Semantic Validation

本指南用于在生成图片/视频之前，校验 prompt 是否准确表达了原始数据的语义。

---

## 评估流程

调用方会在 prompt 中提供**一条或多条** prompt 的完整信息（entity_id、type、prompt、negative_prompt、source 等），包裹在 `<prompts>` 标签中。

1. 根据涉及的 entity type **按需读取**对应的 prompt guide 作为规范参考（每种类型只读一次）：
   - Character / CharacterAppearance → `${AGENT_DIR}/../image-creator/prompt-guide-character.md`
   - Location / LocationState → `${AGENT_DIR}/../image-creator/prompt-guide-location.md`
   - Prop / PropState → `${AGENT_DIR}/../image-creator/prompt-guide-prop.md`
2. 对**每条** prompt，逐项执行下方 Checklist 中的检查。
3. 输出结构化校验结果（每条一个检查块）。

**注意**：不需要读取 `prompt-review.json`。

---

## 输入字段说明

调用方在 prompt 中提供的字段：

| 字段 | 说明 |
|------|------|
| `entity_id` | 实体/状态 ID |
| `type` | `character / location / prop / character_appearance / location_state / prop_state` |
| `prompt` | 实际要传给 GenerateImage 的英文 prompt |
| `negative_prompt` | 负面提示词 |
| `aspect_ratio` | 画面比例 |
| `reference_image_paths` | 参考图路径列表（Layer 2 必填） |
| `source` | story-graph 中的原始数据（`fixed_traits`、`visual`、`appearance`），是校验语义准确性的唯一依据 |

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

**核心原则：PASS 从简，FAIL 聚焦动作。** 输出会直接返回给调用方 agent，必须精简以节省上下文。

对每条 prompt 输出一行或一块：

**PASS 时**（一行搞定，不解释理由）：
```
- {entity_id} ({type}): PASS
```

**FAIL 时**（只列失败项和修改动作，不解释 PASS 项）：
```
- {entity_id} ({type}): FAIL
  - {失败维度}: {问题} → {修改动作}
  - {失败维度}: {问题} → {修改动作}
```

修改动作必须是可直接执行的指令（如 `删除 "soft shadow"`、`在 X 后添加 Y`、`将 "gentle smile" 改为 "determined gaze"`）。**不要给出修改后的完整 prompt**——调用方自己改。

最后输出汇总行：
```
**汇总: {PASS数}/{总数} PASS, FAIL: [{FAIL的entity_id列表}]**
```

**禁止**：
- PASS 项的逐条论证（"陆地乌龟→land tortoise"这类对应罗列）
- FAIL 项中对 PASS 维度的说明
- 修改后的完整 prompt / negative_prompt 全文
- "前置检查"等额外段落
