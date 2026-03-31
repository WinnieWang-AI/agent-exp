# 作曲

## 输入

项目目录下已有：
- `meta.json` — style_prefix、language
- `events.json` — 事件列表（描述、mood、时序关系）
- `shots.json` — shot 列表 + shot_order + 每个 shot 的 duration_seconds

## 步骤

### Step 1: 加载参考文件

用 ReadFile 加载 `${AGENT_DIR}/guide-music-prompt.md`。

### Step 2: 读取项目数据

读取以下文件：

1. `{project_path}/meta.json` — 提取：
   - `style.style_prefix` — 视觉风格（用于推断音乐风格方向）
   - `video_info.language` — 语言

2. `{project_path}/events.json` — 提取：
   - 事件列表：每个事件的 description、mood、characters、interactions
   - `event_sequence` — 事件时序关系

3. `{project_path}/shots.json` — 提取：
   - `shot_order` — 播放顺序
   - 每个 shot 的 `event_id` 和 `duration_seconds`（用于计算时间轴）

4. 检查断点：如果 `{project_path}/music-status.json` 已存在，读取已完成的主题曲，后续跳过。

### Step 3: 主题曲设计

BGM 不是"把视频切成段，每段配一首新曲子"，而是**设计几首主题曲，在时间线上反复编排使用**。

#### 3.1 情绪聚类

遍历所有事件的 mood，归纳为 **2-4 个情绪类别**。相近的情绪合为一类：

- 温暖/轻快/欢乐 → 一类
- 紧张/谨慎/悬疑 → 一类
- 悲伤/惆怅 → 一类
- 宏大/史诗 → 一类

每个类别对应一首主题曲。大多数短片（≤5 分钟）只需要 **1-2 首**，较长的视频（>5 分钟）通常 **2-4 首**足够。

#### 3.2 主题曲规划

每首主题曲记录：
- `theme_id`：`theme_{情绪关键词}`（如 `theme_warm`、`theme_tense`）
- `description`：中文描述该主题曲的情绪和风格
- `mood_cluster`：归入此主题曲的情绪列表
- `event_ids`：使用此主题曲的事件 ID 列表

### Step 4: 主题曲生成

对每首主题曲（跳过 music-status.json 中已完成的）：

#### 4.1 编写 Music Prompt

按 `guide-music-prompt.md` 的规范编写英文 music prompt。主题曲的 prompt 应描述**通用氛围**，不绑定具体事件情节，因为同一首曲子会在多个场景复用。

参考 meta.json 的 style_prefix 确保音画风格一致。

#### 4.2 提交生成

```
GenerateMusic(
  prompt=<英文 music prompt>,
  make_instrumental=true
)
```

记录返回的 `job_id` 和 `provider`。

#### 4.3 轮询等待

用 CheckMusicJob 轮询任务状态。Suno 通常需要 30-90 秒：

```
CheckMusicJob(
  job_id=<job_id>,
  provider=<provider>,
  download_dir="{project_path}/assets/audio",
  download_filename="{theme_id}.mp3"
)
```

- `pending` / `processing` → 等待后重试（间隔 15-30 秒）
- `completed` → 下载完成，记录状态
- `failed` → 记录错误，按错误处理策略决定下一步

#### 4.4 并行策略

- 可以同时提交所有主题曲的 GenerateMusic 调用
- 轮询时按提交顺序检查
- Suno 每次生成 2 首候选，只下载第一首（通过 download_filename 控制）

### Step 5: 时间线编排

所有主题曲生成完成后，设计 BGM 在视频时间线上的编排。

#### 5.1 编排规则

- 按事件顺序，为每个事件指定使用哪首主题曲（或标记为 silence）
- **相邻事件使用同一主题曲 → 连续播放**，不切断
- **相邻事件使用不同主题曲 → crossfade 过渡**（默认 2 秒）
- **需要静默的事件 → silence**，与前后段落 fade_out / fade_in 过渡
- 视频开头 fade_in（默认 2 秒），视频结尾 fade_out（默认 3 秒）

#### 5.2 输出编排

将连续使用同一主题曲的事件合并为一个播放区间，生成 arrangement 数组。每个区间记录：
- `theme_id`：主题曲 ID
- `start`：起始秒数（从 shot_order 累加计算）
- `end`：结束秒数
- `fade_in`：淡入秒数（0 表示无淡入）
- `fade_out`：淡出秒数（0 表示无淡出）

### Step 6: 记录状态

更新 `{project_path}/music-status.json`：

```json
{
  "themes": {
    "theme_warm": {
      "status": "done",
      "description": "温暖轻快的民谣风",
      "prompt": "实际使用的 prompt",
      "job_id": "xxx",
      "provider": "suno",
      "output_path": "assets/audio/theme_warm.mp3",
      "generated_duration_seconds": 85
    },
    "theme_tense": {
      "status": "done",
      "description": "轻微紧张、谨慎",
      "prompt": "实际使用的 prompt",
      "output_path": "assets/audio/theme_tense.mp3",
      "generated_duration_seconds": 60
    }
  },
  "arrangement": [
    {"theme_id": "theme_warm",  "start": 0,  "end": 22, "fade_in": 2, "fade_out": 0},
    {"theme_id": "theme_tense", "start": 22, "end": 43, "fade_in": 0, "fade_out": 0},
    {"theme_id": "theme_warm",  "start": 43, "end": 62, "fade_in": 0, "fade_out": 3}
  ],
  "crossfade_seconds": 2,
  "summary": {"total_themes": 2, "done": 2, "failed": 0}
}
```

### Step 7: 汇报

报告：
- 主题曲数量（成功 / 失败）
- 每首主题曲的情绪描述和生成时长
- 时间线编排概览（哪段时间用哪首曲子）
- 静默区间（如有）
- 失败的主题曲及错误信息

等待调用方指示。

## 输出

在项目路径下生成：
- `assets/audio/{theme_id}.mp3` — 主题曲音频文件
- `music-status.json` — 主题曲状态 + 时间线编排

## 错误处理

- **events.json 为空**：无事件，报告调用方"无 BGM 需求"，正常退出。
- **API 超时** → 用相同参数重试 1 次
- **生成质量差**（调用方反馈）→ 修改 prompt 后重新生成该主题曲
- **单首主题曲累计 2 次失败** → 标记为 failed，继续下一首
- **所有主题曲均失败** → 停止并上报调用方
