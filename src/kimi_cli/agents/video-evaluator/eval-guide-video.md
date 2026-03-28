# Evaluation Guide: Video

本指南用于评估**生成的视频片段（逐 shot）**或**最终成片**。

---

## 评估流程

1. 调用方会提供：视频路径、shot/成片的描述信息（content、角色、场景等）、**要求的 aspect_ratio**、**出镜角色的参考图路径**。如果是对比评估，还会提供原始视频路径。
2. **画面比例检查（确定性）**：用 **AnalyzeVideo** 获取视频元数据（resolution），从返回的 `resolution` 字段（如 `960x960`、`720x1280`）计算实际宽高比，与调用方提供的要求 aspect_ratio 对比。这是确定性检查，不依赖 VLM 判断。
3. **视觉评估**：优先使用 AnalyzeVideo（VLM 整片分析）。如果 VLM 限流（429）或失败，**切换到截图评估方案**（见下文）。
4. 输出结构化报告。

### 截图评估方案（VLM 不可用时的替代方案，或成片多 shot 评估的标准方案）

当 AnalyzeVideo 限流/失败，或评估多 shot 成片时，使用 **ExtractFrame + ReadMediaFile** 逐 shot 提取关键帧进行评估：

**提取策略**：对每个 shot 视频提取**首帧和尾帧**：
```
ExtractFrame(video_path=shot.mp4, output_path=frames/{shot_id}_start.png, position="first")
ExtractFrame(video_path=shot.mp4, output_path=frames/{shot_id}_end.png, position="last")
```

**查看方式**：用 **ReadMediaFile** 查看提取的截图。每次可同时查看多张截图（如一个 shot 的首尾帧 + 参考图）进行对比。

**基于截图可评估的维度**：
| 维度 | 截图可评估 | 评估方法 |
|------|-----------|---------|
| Character Consistency 人物一致性 | ✓ | 对比首尾帧中角色外观与参考图 |
| Content Fidelity 内容匹配 | ✓ | 首帧构图是否符合 content 描述 |
| Composition 构图 | ✓ | 从首帧判断画面布局 |
| Color & Lighting 色彩光影 | ✓ | 从截图判断色调、光照 |
| Shot Continuity 镜头衔接 | ✓ | 对比前一 shot 尾帧与后一 shot 首帧，检查跳切 |
| Props Consistency 道具一致性 | ✓ | 跨 shot 对比同一道具（如终点线）外观是否一致 |

**基于截图无法评估的维度**（标注 N/A 并说明原因）：
| 维度 | 原因 |
|------|------|
| Motion & Dynamics 运动 | 需要看视频才能判断运动流畅度、抖动、穿模 |
| Timing & Rhythm 节奏 | 需要看视频才能判断节奏感 |
| Audio & Sync 音频 | 需要播放视频 |

**成片评估时的额外检查**：
- **跨 shot 一致性**：依次查看所有 shot 的首帧，检查角色外观、场景风格是否跨镜头统一
- **叙事完整性**：按时间顺序查看所有首帧，判断故事是否可理解（如龟兔赛跑：起跑→领先→打盹→超越→冲线）
- **镜头衔接**：对比相邻 shot 的尾帧→首帧，检查是否有突兀跳切

---

## 评估维度

### 确定性检查（工具读取，非 VLM）

| 维度 | 评估方式 |
|------|---------|
| **Aspect Ratio 画面比例** | 从 AnalyzeVideo 返回的 `resolution`（如 720x1280）计算实际比例，与要求的 aspect_ratio（如 9:16）对比。宽高比误差 ≤ 5% 为 PASS，否则 FAIL |

### VLM 评估维度（评分 1-10）

| 维度 | 评估要点 |
|------|---------|
| **Character Consistency 人物一致性** | 视频中的角色与调用方提供的参考图是否一致（面部特征、体型、服装、发型）。用 AnalyzeImage 同时传入视频截帧和参考图进行对比 |
| **Content Fidelity 内容匹配** | 内容是否与描述/content 一致、场景是否正确、动作/事件是否符合剧情 |
| **Motion & Dynamics 运动** | 运动速度、方向、流畅度、角色动作是否自然 |
| **Composition 构图** | 镜头角度、画面构成、空间布局、人物站位 |
| **Color & Lighting 色彩光影** | 色调、对比度、光照方向、氛围是否与描述一致 |
| **Timing & Rhythm 节奏** | 片段时长、转场时机、节奏感 |
| **Audio & Sync 音频（如适用）** | 音乐/旁白/音效是否匹配、节奏是否同步。逐 shot 评估时如尚未合成音频则跳过 |

---

## 判定规则

### 维度分级

| 维度 | 级别 | 说明 |
|------|------|------|
| Aspect Ratio 画面比例 | **关键** | 确定性检查，比例不符直接 FAIL，无法后期修复 |
| Character Consistency 人物一致性 | **关键** | 角色与参考图不一致（换脸、换性别、体型完全不同）直接拉低整体 |
| Content Fidelity 内容匹配 | **关键** | 场景完全不符、动作/事件与剧情矛盾直接拉低整体 |
| Motion & Dynamics 运动 | **关键** | 严重变形、肢体异常直接拉低整体 |
| Composition 构图 | **次要** | 影响观感但不影响故事理解 |
| Color & Lighting 色彩光影 | **次要** | 影响氛围但不影响故事理解 |
| Timing & Rhythm 节奏 | **次要** | 影响观感但不影响故事理解 |
| Audio & Sync 音频 | **次要** | 可后期修复；逐 shot 评估时未合成音频则 N/A |

### 评分约束

- 画面比例不符 → **直接 FAIL**（不参与评分，是前置检查）
- 角色与参考图差异很大（变脸、换性别、体型完全不同）→ Character Consistency **≤ 4**
- 角色与参考图有差异但可辨认（服装细节偏差、发色略不同）→ Character Consistency **≤ 7**
- 出现明显变形、闪烁、肢体异常 → Motion **≤ 4**
- 任意**关键维度 ≤ 4** → Overall **≤ 6**
- Overall **不是简单平均**，以最严重的短板为主

### 从评分到结论的判定

| 情况 | 结论 |
|------|------|
| Overall >= 8 | **APPROVED** |
| Overall < 8 | **NEEDS_REVISION** |

对比评估（复现场景）要求更高：Overall >= 9 才 APPROVED。

### 其他原则

- **不要因为是 AI 生成就降低标准**：评价标准是"这个画面能否让观众理解故事"。
- **给出可操作的修改建议**：NEEDS_REVISION 时不要只说"不够好"，要指出具体维度的具体问题和修改方向（如"角色面部在 0:03 变形，建议缩短视频时长或使用 image_to_video 模式"）。

---

## 输出格式

### 逐 Shot 评估

```
## Shot 视频评估报告

### {shot_id}
- 路径: {path}
- 分辨率: {resolution}（来自 AnalyzeVideo 元数据）
- 时长: {duration}

### 前置检查
- Aspect Ratio 画面比例: PASS / FAIL — 实际 {actual_ratio}，要求 {required_ratio}

### 评分（画面比例 PASS 后才评分）
- Character Consistency 人物一致性: X/10 — {与参考图对比反馈}
- Content Fidelity 内容匹配: X/10 — {具体反馈}
- Motion & Dynamics 运动: X/10 — {具体反馈}
- Composition 构图: X/10 — {具体反馈}
- Color & Lighting 色彩光影: X/10 — {具体反馈}
- Timing & Rhythm 节奏: X/10 — {具体反馈}
- Audio & Sync 音频: X/10 — {具体反馈，或 N/A}
- **Overall: X/10**

### 主要问题
- {问题 1: 描述 + 具体建议}

### Verdict
APPROVED (overall >= 8) / NEEDS_REVISION / FAIL (画面比例不符)
```

### 对比评估（原始视频 vs 生成视频）

```
## 视频对比评估报告

### 基本信息
- 原始视频: {path}
- 生成视频: {path}

### 评分
- Character Consistency 人物一致性: X/10 — {与参考图对比}
- Content Fidelity 内容匹配: X/10 — {与原始的差异}
- Motion & Dynamics 运动: X/10 — {与原始的差异}
- Composition 构图: X/10 — {与原始的差异}
- Color & Lighting 色彩光影: X/10 — {与原始的差异}
- Timing & Rhythm 节奏: X/10 — {与原始的差异}
- Audio & Sync 音频: X/10 — {与原始的差异，或 N/A}
- **Overall: X/10**

### What Improved（与上一轮对比，如适用）
- {改善点}

### What Needs Work
- {具体问题 + 可操作的修改建议}

### Verdict
APPROVED (overall >= 9) / NEEDS_REVISION
```

### 成片评估

评估最终拼接的完整视频时，除上述维度外，额外关注：

| 额外检查项 | 评估要点 |
|-----------|---------|
| **总时长** | 是否符合目标时长 |
| **镜头衔接** | 转场是否自然、镜头顺序是否符合叙事逻辑 |
| **音视频同步** | 对白与口型、BGM 与画面节奏 |
| **整体连贯性** | 角色外观是否跨镜头一致、色调风格是否统一 |

---

## Timecode Standard

- 使用 mm:ss(.fff) 格式，在一个 session 内保持一致。
- 指出问题时必须附带时间码（如"0:03 处角色面部变形"）。
