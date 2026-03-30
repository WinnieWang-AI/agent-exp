# 逐 Shot 生成

## 输入

项目目录下已有导演产出：
- `meta.json` — style_prefix、negative_prefix、aspect_ratio、language
- `states.json` — 状态视觉描述 + active_during 映射 + reference_image 路径
- `shots.json` — shot 列表 + shot_order（全局播放顺序）+ total_duration_seconds
- `assets/images/` — 参考图文件

## 步骤

### Step 1: 加载参考文件

用 ReadFile 加载：
1. `${AGENT_DIR}/guide-shot-strategy.md` — 生成模式决策树
2. `${AGENT_DIR}/guide-prompt-video.md` — prompt 组合规则

### Step 2: 读取项目数据

读取以下文件并建立索引：

1. `{project_path}/meta.json` — 提取：
   - `production_styles[0].style_prefix` — 风格前缀
   - `production_styles[0].negative_prefix` — 负面提示
   - `video_info.aspect_ratio` — 画面比例
   - `video_info.language` — 对白语言

2. `{project_path}/states.json` — 建立两个映射：
   - **state_id → 视觉描述**：从 character_appearances / location_states / prop_states 中提取 visual / lighting / atmosphere 等字段
   - **state_id → reference_image 路径**：提取每个状态的 reference_image 字段（可能为空）

3. `{project_path}/shots.json` — 提取：
   - `shots` 数组（全部 shot 数据）
   - `shot_order` 数组（全局播放顺序）

4. 检查断点：如果 `{project_path}/generation-status.json` 已存在，读取已完成的 shot ID 列表，后续跳过这些 shot。

### Step 3: 逐 Shot 决策与执行

按 `shot_order` 顺序遍历每个 shot。对已完成的 shot（在 generation-status.json 中状态为 "done"），跳过。

对每个 shot，依次完成以下步骤：

#### 3.1 决策：生成模式

按 `guide-shot-strategy.md` 的决策流程推理。核心判断：

1. **判断谁出镜**：从 `focus_on` 查出角色/场景/道具的状态 ID
2. **判断是否需要尾帧接续**：
   - 同一 event 内的非首个 shot（同 event_id，前一个 shot 已生成）→ 提取前一 shot 尾帧 → `image_to_video`
   - 不同 event 但在 shot_order 中相邻，且有共同角色 → 可选将前一 shot 尾帧加入 reference_images
3. **判断首帧可行性**：
   - 所有角色开头可见 + 动作小 → 生成首帧图 → `image_to_video`
   - 有角色中途出场 / 大幅运动 → `reference_to_video`
   - 无参考图 → `text_to_video`

#### 3.2 尾帧提取（如需）

当决策需要前一 shot 的尾帧时：

```
ExtractFrame(
  video_path="{project_path}/assets/shots/{prev_shot_id}.mp4",
  output_path="{project_path}/assets/frames/{shot_id}_tail.png",
  position="last"
)
```

#### 3.3 首帧生成（如需）

当决策选择 image_to_video 且非尾帧接续时，生成首帧图：

```
GenerateImage(
  prompt=<首帧 prompt，按 guide-prompt-video.md 的首帧规范组装>,
  reference_image_paths=<角色参考图列表>,
  aspect_ratio=<从 meta.json>,
  negative_prompt=<从 meta.json>,
  output_path="{project_path}/assets/frames/{shot_id}_first.png"
)
```

首帧 prompt 使用 `@[role N]` 标记（不是 `<<<image_N>>>`）。

#### 3.4 组装 Prompt 并生成

按 `guide-prompt-video.md` 的规范组装视频 prompt，覆盖：
- style_prefix（开头）
- 镜头语言（shot_type + angle + movement）
- 画面内容（content）
- 场景环境（从 focus_on 的 LocationState 查 states.json 的 lighting/atmosphere）
- 角色外形（从 focus_on 的 CharacterAppearance 查 states.json 的 visual，从简）
- 角色行为（从 focus_on 查 CharacterMind 的 emotion + behavior，通过 active_during 找到同 event 的 mind 状态）
- 对白（从 shot 的 dialogues 字段，写入 Sound: 段）
- 音效（从 shot 的 sfx 字段，写入 Sound: 段）
- `<<<image_N>>>` 标记（每张 reference_image 对应一个）

**Prompt 必须用英文。** 将中文描述翻译为英文自然语言。

```
GenerateVideoSync(
  prompt=<组装好的 prompt>,
  mode=<决策确定的模式>,
  reference_images=<参考图路径列表>,
  reference_image_path=<首帧/尾帧路径，仅 image_to_video 模式>,
  duration_seconds=<shot.duration_seconds>,
  aspect_ratio=<从 meta.json>,
  negative_prompt=<从 meta.json>,
  download_path="{project_path}/assets/shots/{shot_id}.mp4"
)
```

#### 3.5 记录状态

每个 shot 生成后（无论成功或失败），立即更新 `{project_path}/generation-status.json`：

```json
{
  "shots": {
    "evt_farewell_shot_1": {
      "status": "done",
      "mode": "reference_to_video",
      "reference_images": ["assets/images/appear_red_neat.png"],
      "prompt": "实际使用的完整 prompt",
      "output_path": "assets/shots/evt_farewell_shot_1.mp4",
      "reasoning": "event 首 shot，角色开头可见但有走动，选择 reference_to_video"
    },
    "evt_farewell_shot_2": {
      "status": "failed",
      "error": "API error: rate limited",
      "retry_count": 2
    }
  },
  "summary": {
    "total": 12,
    "done": 8,
    "failed": 1,
    "pending": 3
  }
}
```

逐个记录，不要等全部完成再批量写入。

### Step 4: 并行执行

- **同 event 内的连续 shot 必须串行**：后一个 shot 可能需要前一个的尾帧
- **不同 event 且无尾帧依赖的 shot 可以并行**：在同一个 response 中调用多个 GenerateVideoSync
- 建议每批并行 3-5 个 shot
- 并行时，每个 shot 的决策（3.1-3.4）在调用前完成，不依赖其他并行 shot 的结果

### Step 5: 错误处理

按以下顺序恢复：
1. **网络错误 / 超时** → 用相同参数重试 1 次
2. **参数错误** → 调整参数后重试（如不支持的 mode → 换 mode）
3. **provider 限流 / 连续失败 2 次** → 从错误返回的 `available_providers` 中选另一个 provider 重试
4. **累计 3 次失败** → 标记该 shot 为 failed，继续下一个 shot
5. `image_to_video` 失败可退回 `reference_to_video`

### Step 6: 汇报

所有 shot 处理完成后，报告结果：
- 成功数 / 失败数 / 总数
- 失败的 shot ID 和错误信息
- 总生成时长

等待调用方指示。

## 输出

在项目路径下生成：
- `assets/shots/{shot_id}.mp4` — 视频片段
- `assets/frames/{shot_id}_tail.png` — 尾帧（接续用）
- `assets/frames/{shot_id}_first.png` — 首帧图（如有）
- `generation-status.json` — per-shot 生成状态

## 错误处理

- **shots.json 缺少 shot_order**：按 events.json 的 event_sequence + shot 的 event_id/order 推断顺序，报告 warning。
- **states.json 中 reference_image 路径不存在**：该状态无参考图，降级为 text_to_video 或仅用其他可用参考图。
- **所有 shot 均失败**：停止并上报调用方，不尝试本地生成。
