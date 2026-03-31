# 成片组装

## 输入

项目目录下已有：
- `meta.json` — aspect_ratio、language、style_prefix
- `shots.json` — shot_order、每个 shot 的 duration_seconds / transition_in / transition_out / dialogues
- `music-status.json` — BGM 主题曲 + 时间线编排信息（themes / arrangement）
- `assets/shots/{shot_id}.mp4` — 视频片段
- `assets/audio/{theme_id}.mp3` — BGM 主题曲音频文件
- `generation-status.json` — 视频生成状态（哪些 shot 成功/失败）

调用方会提供：
- 项目路径（绝对路径）
- 输出路径（绝对路径，如 `{project_path}/output/video_1.mp4`）

## 步骤

### Step 1: 加载参考文件

用 ReadFile 加载 `${AGENT_DIR}/guide-timeline.md`。

### Step 2: 读取项目数据

1. `{project_path}/shots.json` — 提取 shot_order、每个 shot 的字段
2. `{project_path}/generation-status.json` — 确认哪些 shot 实际生成成功（`status: "done"`）；从 `steps.video.has_audio` 和 `steps.tts.paths` 提取音频信息，供 Step 4.5 TTS 叠加使用
3. `{project_path}/music-status.json` — 提取 BGM 主题曲和时间线编排（可能不存在，如果没有 BGM 需求）
4. `{project_path}/meta.json` — 提取 aspect_ratio、language

**素材检查**：按 shot_order 遍历，检查每个 shot 的视频文件是否存在（`assets/shots/{shot_id}.mp4`）。记录缺失列表。如果缺失率 > 30%，上报调用方，不继续组装。

### Step 3: 裁剪

对 shot_order 中的每个 shot：

检查实际视频时长（从 VideoEdit 返回的 metadata 中获取）。如果与 shots.json 中的 `duration_seconds` 偏差 > 0.5s，用 trim 裁剪：

```
VideoEdit(
  operation="trim",
  input_files=["{project_path}/assets/shots/{shot_id}.mp4"],
  output_path="{project_path}/assets/shots/{shot_id}_trimmed.mp4",
  end_time=<duration_seconds>
)
```

偏差 ≤ 0.5s 的 shot 不需要裁剪，直接使用原文件。

### Step 4: 转场 + 拼接

按 shot_order 顺序，用转场效果连接 shot。

**策略**：大部分 shot 之间是 `cut`（硬切），只有少数需要转场效果。

1. **分组**：将连续 cut 转场的 shot 分为一组，非 cut 转场（fade / dissolve / wipe）作为分组边界
2. **组内拼接**：每组内用 `concat` 直接拼接
3. **组间转场**：组与组之间用 `transition` 添加转场效果
4. **最终拼接**：将所有组用 `concat` 拼接为一个视频

具体逻辑：

```
遍历 shot_order：
  如果当前 shot 的 transition_in 是 cut，且前一个 shot 的 transition_out 是 cut：
    加入当前 concat 组
  否则：
    关闭当前 concat 组
    用 transition 连接前一组的输出和当前 shot
    开启新 concat 组
```

临时文件输出到 `{project_path}/output/tmp/`，最终组装完成后可清理。

### Step 4.5: TTS 对白音轨叠加

读取 `generation-status.json`，检查是否有 shot 的 `steps.video.has_audio` 为 `false` 且 `steps.tts.paths` 非空。如果没有，跳过此步。

对每个需要 TTS 叠加的 shot：

1. **计算时间偏移**：按 shot_order 累加前序 shot 的 `duration_seconds`，扣除转场重叠（与 Step 6 字幕计算相同的时间轴逻辑），得到该 shot 在拼接视频中的起始秒数。
2. **叠加 TTS 音频**：对该 shot 的每个 TTS 文件：

```
VideoEdit(
  operation="add_audio",
  input_files=[<当前视频>],
  audio_path=<tts_path>,
  audio_mix=true,
  audio_offset=<shot 起始偏移 + 对白在 shot 内的估算位置>,
  output_path="{project_path}/output/tmp/with_tts_{N}.mp4"
)
```

**对白在 shot 内的位置**：居中对齐（与 Step 6 字幕居中逻辑一致）。如果 shot 只有一条对白，偏移 = shot 起始时间。如果有多条对白，按顺序平均分布在 shot 时间范围内。

**多个 shot 需要 TTS 时**：按 shot_order 逐个叠加，每次用上一步的输出作为输入（串行）。

### Step 5: BGM 叠加

读取 `music-status.json`，从 `themes` 中筛选 status 为 "done" 的主题曲，从 `arrangement` 中读取时间线编排。

#### 5a. 单主题曲 + 连续编排

如果 arrangement 只有 1 个区间且覆盖全片，直接叠加（用 audio_loop 循环补足时长）：

```
VideoEdit(
  operation="add_audio",
  input_files=[<Step 4 输出>],
  audio_path="{project_path}/assets/audio/{theme_id}.mp3",
  audio_mix=true,
  audio_loop=true,
  output_path="{project_path}/output/tmp/with_bgm.mp4"
)
```

#### 5b. 多区间编排

按 arrangement 数组构建 `mix_audio` 的 audio_segments。同一首主题曲在不同区间复用同一个音频文件：

```
VideoEdit(
  operation="mix_audio",
  audio_segments=[
    {"path": "assets/audio/theme_warm.mp3",  "start": 0,  "end": 22},
    {"path": "assets/audio/theme_tense.mp3", "start": 22, "end": 43},
    {"path": "assets/audio/theme_warm.mp3",  "start": 43, "end": 62}
  ],
  crossfade_duration=<music-status.json 中的 crossfade_seconds，默认 2.0>,
  output_path="{project_path}/output/tmp/bgm_mixed.mp3"
)
```

arrangement 中各区间的 `fade_in` / `fade_out` 由 mix_audio 的 crossfade 机制自动处理。首段的 `fade_in` 和末段的 `fade_out` 用 FFmpeg 的 afade 滤镜单独实现。

然后叠加到视频：

```
VideoEdit(
  operation="add_audio",
  input_files=[<Step 4 输出>],
  audio_path="{project_path}/output/tmp/bgm_mixed.mp3",
  audio_mix=true,
  output_path="{project_path}/output/tmp/with_bgm.mp4"
)
```

#### 5c. 无 BGM

如果 music-status.json 不存在或无成功主题曲，跳过此步。

### Step 6: 字幕生成与烧录

从 shots.json 按 shot_order 提取所有对白，生成 SRT 字幕文件：

1. **累加时间偏移**：按 shot_order 累加每个 shot 的 duration_seconds，计算每段对白的绝对时间
2. **估算对白时长**：
   - 中文：每秒 3-4 个字
   - 英文：每秒 2-3 个单词
   - 最小 1.5 秒，最大不超过 shot 时长
3. **对白居中对齐**：在 shot 时间范围内居中放置

SRT 格式：

```
1
00:00:02,000 --> 00:00:05,000
路上不要和陌生人说话

2
00:00:12,500 --> 00:00:15,000
你好啊小姑娘，你要去哪里呀？
```

用 WriteFile 写入 `{project_path}/output/subtitles.srt`。

如果没有任何对白，跳过此步。

有对白时，烧录字幕：

```
VideoEdit(
  operation="add_subtitles",
  input_files=[<Step 5 输出或 Step 4 输出>],
  subtitle_path="{project_path}/output/subtitles.srt",
  output_path=<最终输出路径>
)
```

### Step 7: 验证

VideoEdit 每次操作后返回输出文件的 metadata。对最终成片核对：

1. **总时长**：与 shots.json 的 `total_duration_seconds` 比较，容差 ±2s（转场会轻微缩短总时长）
2. **音轨**：必须有音轨（audio=yes）
3. **分辨率**：与 meta.json 的 aspect_ratio 一致

如有问题，定位出错步骤，修复后重新输出。

### Step 8: 汇报

报告：
- 成片路径
- 总时长
- 分辨率
- 使用的 shot 数（含跳过的缺失 shot）
- BGM 主题曲数 + 编排区间数
- 字幕条数
- 任何 warning（如某些 shot 缺失、BGM 缺失等）

## 输出

- `{output_path}` — 最终成片
- `{project_path}/output/subtitles.srt` — 字幕文件（如有对白）

## 错误处理

- **视频片段缺失**：跳过该 shot，在汇报中说明。缺失率 > 30% 时停止并上报。
- **BGM 文件缺失**：跳过 BGM 叠加，汇报中说明成片无 BGM。
- **FFmpeg 操作失败**：检查错误信息，尝试简化参数后重试 1 次。如果 concat 失败可能是分辨率不一致，尝试先统一分辨率。
- **字幕烧录失败**：跳过字幕，交付无字幕版本，汇报中说明。
