# 作曲

## 输入

项目目录下已有：
- `meta.json` — style_prefix、language
- `shots.json` — shot 列表 + shot_order + bgm 字段

## 步骤

### Step 1: 加载参考文件

用 ReadFile 加载 `${AGENT_DIR}/guide-music-prompt.md`。

### Step 2: 读取项目数据

读取以下文件：

1. `{project_path}/meta.json` — 提取：
   - `style.style_prefix` — 视觉风格（用于推断音乐风格方向）
   - `video_info.language` — 语言

2. `{project_path}/shots.json` — 提取：
   - `shot_order` — 播放顺序
   - 每个 shot 的 `bgm` 和 `duration_seconds` 字段

3. 检查断点：如果 `{project_path}/music-status.json` 已存在，读取已完成的分段，后续跳过。

### Step 3: BGM 分段聚合

按 `shot_order` 顺序遍历 shot，将连续相同 bgm 描述的 shot 合并为一个音乐分段：

规则：
- `bgm` 字段为空或省略的 shot，继承前一个 shot 的 bgm（延续配乐）
- `bgm` 字段为 `"silence"` 的 shot，表示无配乐，终止当前分段
- `bgm` 字段内容变化时，开启新分段

每个分段记录：
- `segment_id`：`bgm_segment_{N}`（从 1 开始）
- `description`：bgm 描述文本
- `shot_ids`：包含的 shot ID 列表
- `duration_seconds`：包含的 shot 时长之和
- `start_offset`：在最终视频中的起始秒数（累加前面所有 shot 的时长）

示例：

```json
[
  {
    "segment_id": "bgm_segment_1",
    "description": "轻柔的木吉他指弹，温馨家庭氛围",
    "shot_ids": ["evt_farewell_shot_1", "evt_farewell_shot_2"],
    "duration_seconds": 10,
    "start_offset": 0
  },
  {
    "segment_id": "bgm_segment_2",
    "description": "明快的管弦乐，冒险出发的欢快感",
    "shot_ids": ["evt_forest_shot_1", "evt_forest_shot_2", "evt_forest_shot_3"],
    "duration_seconds": 18,
    "start_offset": 10
  }
]
```

### Step 4: 逐段生成

对每个分段（跳过 music-status.json 中已完成的）：

#### 4.1 编写 Music Prompt

按 `guide-music-prompt.md` 的规范，将中文 bgm 描述转化为英文 music prompt，参考 meta.json 的 style_prefix 确保音画风格一致。

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
  download_filename="{segment_id}.mp3"
)
```

- `pending` / `processing` → 等待后重试（间隔 15-30 秒）
- `completed` → 下载完成，记录状态
- `failed` → 记录错误，按错误处理策略决定下一步

#### 4.4 记录状态

每个分段完成后，立即更新 `{project_path}/music-status.json`：

```json
{
  "segments": {
    "bgm_segment_1": {
      "status": "done",
      "prompt": "实际使用的 prompt",
      "job_id": "xxx",
      "provider": "suno",
      "output_path": "assets/audio/bgm_segment_1.mp3",
      "duration_seconds": 10,
      "start_offset": 0
    },
    "bgm_segment_2": {
      "status": "failed",
      "error": "API timeout",
      "retry_count": 1
    }
  },
  "summary": {
    "total": 4,
    "done": 3,
    "failed": 1
  }
}
```

#### 4.5 并行策略

- 可以同时提交多个 GenerateMusic 调用（每批 2-3 个）
- 轮询时按提交顺序检查
- Suno 每次生成 2 首候选，只下载第一首（通过 download_filename 控制）

### Step 5: 汇报

所有分段处理完成后，报告：
- 成功数 / 失败数 / 总分段数
- 每个分段的时长和时间范围
- 失败分段的错误信息
- 总 BGM 覆盖时长 vs 视频总时长

等待调用方指示。

## 输出

在项目路径下生成：
- `assets/audio/{segment_id}.mp3` — 每段 BGM 音频文件
- `music-status.json` — per-segment 生成状态

## 错误处理

- **shots.json 无 bgm 字段**：全部 shot 无配乐需求，报告调用方"无 BGM 需求"，正常退出。
- **API 超时** → 用相同参数重试 1 次
- **生成质量差**（调用方反馈）→ 修改 prompt 后重新生成
- **单个分段累计 2 次失败** → 标记该分段为 failed，继续下一个
- **所有分段均失败** → 停止并上报调用方，不尝试用其他方式生成音乐
