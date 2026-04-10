# 工具能力说明

> 规划阶段加载本文件，了解各工具的能力边界，选择合适的工具组合。

## GenerateVideoSync（视频生成）

按 provider 区分能力。**provider 参数填 provider 名（如 `seedance`、`vidu`、`kling`），不填模型名。** 模型由系统根据生成模式自动选择。

### Seedance（provider = `seedance`）⭐ 默认首选

| 模式 | 视频 | 音频 | 时长 |
|------|------|------|------|
| text_to_video | 是 | 是 | 4-15s |
| image_to_video（首帧/首尾帧） | 是 | 是 | 4-15s |
| reference_to_video | 是 | 是 | 4-15s |

- **优先使用此 provider**，特别是 reference_to_video 模式
- prompt 中的对白、音效、环境音由模型同步生成
- 支持多参考图（reference_image）

### Vidu（provider = `vidu`）

| 模式 | 视频 | 音频 | 时长 |
|------|------|------|------|
| text_to_video | 是 | 是 | 1-16s |
| image_to_video | 是 | 是 | 1-16s |
| reference_to_video | 是 | 是 | 1-16s |
| start-end2video | 是 | 是 | 1-16s |

- prompt Sound 段中的对白、音效、环境音均由模型同步生成
- 参考图上限：7 张

### Kling（provider = `kling`）

| 模式 | 视频 | 音频 | 时长 |
|------|------|------|------|
| text_to_video | 是 | 是 | 5-10s |
| image_to_video | 是 | 是 | 5-10s |

- 不支持 reference_to_video

## GenerateSpeech（TTS 语音合成）

- 输入文本，输出语音 mp3
- 仅生成人声朗读，无音效、无环境音
- 适用于：**旁白**（narrator 独白配画面）
- 不适用于：人物对话（语音与画面不同步，质量差）

## GenerateImage（图片生成）

- 用于生成首帧图（image_to_video 的起始画面）
- 支持参考图输入（角色/场景一致性）

## ExtractFrame（帧提取）

- 从已生成的视频中提取首帧或尾帧
- 用于镜头间视觉接续

## 音频策略选择规则

1. **优先 GenerateVideoSync**：如果 provider 支持音频（如 Seedance、Vidu），所有声音（对白 + 音效 + 环境音）交给视频 API，通过 prompt Sound 段描述
2. **TTS 补旁白**：仅当视频 API 无音频能力时，为 narrator 旁白调用 GenerateSpeech
3. **人物对话不走 TTS**：角色对白始终通过视频 API 的 Sound 段生成，无音频能力时缺失，交给剪辑 agent 处理
4. **BGM 独立**：由作曲 agent 生成，视频 prompt 中始终加 "No background music."
