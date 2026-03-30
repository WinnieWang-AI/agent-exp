# 时间轴计算与参数参考

> 组装成片时，参考本文件进行时间轴计算和参数选择。

## 时间轴计算

### Shot 时间偏移

按 `shot_order` 顺序累加：

```
shot_offset[0] = 0
shot_offset[i] = shot_offset[i-1] + shot[i-1].duration_seconds
```

注意：转场会缩短实际时长。fade/dissolve 转场时两个 shot 有重叠期，实际总时长 = 理论总时长 - 转场重叠时长之和。

### 转场时长扣减

每个非 cut 转场会引入重叠：

```
overlap = transition_duration  （默认 0.5s）
actual_total = sum(duration_seconds) - count(non_cut_transitions) * transition_duration
```

在计算字幕时间和 BGM 时间时，需要考虑这个扣减。简化处理：先按理论时长计算，最终验证时容差 ±2s。

### 对白时长估算

| 语言 | 语速 | 示例 |
|------|------|------|
| 中文 | 3-4 字/秒 | "路上不要和陌生人说话"（9字）≈ 2.5s |
| 英文 | 2-3 词/秒 | "Don't talk to strangers"（4词）≈ 1.5s |

公式：
```
中文: duration = max(1.5, len(text) / 3.5)
英文: duration = max(1.5, word_count / 2.5)
```

对白在 shot 内的时间位置：居中放置，留 0.3s 头尾余量。

```
subtitle_start = shot_offset + 0.3
subtitle_end = min(subtitle_start + dialogue_duration, shot_offset + shot_duration - 0.3)
```

同一 shot 内多段对白按顺序排列，间隔 0.3s。

## VideoEdit 参数参考

### concat

- 要求所有输入分辨率一致（VideoEdit 内部会自动 scale + pad）
- 至少 2 个输入文件
- 自动处理无音轨的片段（生成静音轨）

### transition

- 只能处理 2 个输入文件
- `transition_type` 映射：
  - `fade_in` / `fade_out` → `"fade"`
  - `dissolve` → `"dissolve"`
  - `wipe` → `"wipeleft"`
- `transition_duration`：默认 0.5s，不超过较短片段时长的 1/3

### add_audio

- `audio_mix=true`：混合模式，保留原生音轨
- `audio_mix=false`：替换模式（不要用于 BGM 叠加）
- `audio_loop=true`：短音频自动循环到视频结束
- `audio_offset`：音频在视频时间轴上的起始偏移（秒）

### mix_audio

- 将多个音频文件预混为一个
- `audio_segments`：每个 segment 指定 path / start / end
- `crossfade_duration`：相邻 segment 之间的交叉淡变时长（默认 2.0s）
- 输出为纯音频文件（.mp3）

### add_subtitles

- 输入 SRT 格式字幕文件
- 字幕烧录到视频画面上（硬字幕）
- 需要 re-encode 视频（较慢）

### trim

- `start_time` / `end_time`：秒数
- 如果只需要截取前 N 秒：`start_time=0, end_time=N`

## 分组拼接策略

为了减少 VideoEdit 调用次数，采用分组策略：

```
示例 shot_order: [A, B, C, D, E, F]
转场: A→B cut, B→C cut, C→D dissolve, D→E cut, E→F fade_out

分组:
  Group 1: concat(A, B, C) → tmp_g1.mp4
  Group 2: concat(D, E) → tmp_g2.mp4
  Final:
    transition(tmp_g1, tmp_g2, type=dissolve) → tmp_t1.mp4
    transition(tmp_t1, F, type=fade) → assembled.mp4
```

这比逐 shot 操作高效得多。
