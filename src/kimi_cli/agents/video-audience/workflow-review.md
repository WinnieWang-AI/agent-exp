# 观众审查

## 输入

项目目录下已有导演产出：
- `entities.json` — 角色、场景、道具
- `events.json` — 事件列表、state_changes、interactions
- `states.json` — 实体状态、active_during 映射
- `shots.json` — 镜头列表、shot_order
- `content-quiz.json` — content 可读性测试题，只含问题（如存在）

## 步骤

### Step 1: 加载项目数据

读取以下文件：
- `{project_path}/entities.json` — 角色、场景、道具
- `{project_path}/events.json` — 事件列表、state_changes、interactions
- `{project_path}/states.json` — 实体状态、active_during 映射
- `{project_path}/shots.json` — 镜头列表、shot_order
- `{project_path}/content-quiz.json` — content 可读性测试题，只含问题（如存在）

**注意：`content-quiz-answers.json` 在此阶段不读取。仅在 Step 2E 第二步对比时用 ReadFile 读取。**

建立 event→实体状态映射（从 active_during 反向索引）。

### Step 2: 逐事件审查

按 event_sequence 顺序，对每个 event 审查以下各项：

#### A. 状态变化的视觉覆盖

遍历当前 event 的 `state_changes`，对每个变化：

1. 判断变化的性质：是在镜头内发生（角色当场动手做了某事），还是离场发生（"去做 X"，下一场带着结果回来）
2. 镜头内发生的变化 → 检查是否有 shot 表现了变化**过程**，不能只展示变化后的结果
3. 离场发生的变化 → 检查前后 shot 的 content 是否让观众能推断出发生了什么

**问自己：如果我是第一次看这个视频，看到状态变了，我能理解为什么变了吗？**

#### B. 事件覆盖完整性

检查当前 event 的 shots 是否完整表达了事件意图：

- event 的核心 interactions 是否都有对应 shot
- 关键 state_changes 是否有镜头支撑
- 是否有重要动作被跳过（如"赛跑"事件没有跑步画面，"战斗"事件没有交手画面）

**问自己：如果我只看这些 shot 的描述，我能理解这个事件讲了什么吗？**

#### C. 跨事件因果衔接

检查当前 event 与前一 event 之间：

- 如果 event B 的前提是 event A 的结果，shots 中是否建立了因果（观众看到了 A 的结果，才能理解 B 为什么发生）
- 实体状态是否有无理由的跳变（对比 active_during 中前后 event 的状态，如果变了但没有对应的 state_changes，标记）
- 镜头间是否有逻辑断层（前一个 shot 的画面和下一个 shot 的画面之间，观众是否能自然衔接）

**问自己：从上一个事件到这个事件，过渡自然吗？有没有让我困惑的跳跃？**

#### D. 文本语义正确性

逐 shot 阅读所有文本字段（content、dialogue、voiceover、narration 等），检查：

- 是否存在语病、错别字、语序颠倒、用词不当等语义错误
- 对话是否符合角色身份和语境（一只动物不会说出人类专属的表达，古代角色不会用现代网络用语——除非是刻意设计）
- 引用的成语、谚语、俗语是否正确（字对、义对、用法对）

**问自己：如果我听到角色说出这句话，我能立刻理解意思吗？有没有哪句话让我需要停下来重新想一遍才能懂？**

issue type: `semantic_error`

#### E. 画面描述清晰度（答题测试）

答题测试使用两个文件：
- `{project_path}/content-quiz.json` — 只含问题（question + shot_id），**不含答案**
- `{project_path}/content-quiz-answers.json` — 含标准答案，**仅在第二步对比时读取**

分两步执行：

**第一步：仅凭 content 答题**

读取 `{project_path}/content-quiz.json`，对每道题：
1. 找到对应 shot_id 的 shot，**仅凭该 shot 的 content 字段作答**
2. **此阶段禁止读取 content-quiz-answers.json、events.json、states.json**——你是观众，只能看到画面描述
3. 如果 content 中没有相关信息，答案写"无法从 content 中判断"
4. 将每题的 audience_answer 写入 `{project_path}/content-quiz-result.json`

**第二步：读取标准答案，逐题对比**

所有题目答完并写入 result 后，读取 `{project_path}/content-quiz-answers.json`，逐题对比，更新 `{project_path}/content-quiz-result.json`：

```json
{
  "total": 10,
  "passed": 7,
  "failed": 3,
  "results": [
    {
      "question_id": "q_001",
      "shot_id": "evt_xxx_shot_1",
      "question": "题目原文",
      "expected_answer": "标准答案",
      "audience_answer": "观众基于 content 给出的答案",
      "passed": true
    }
  ]
}
```

- 答案与标准答案一致 → `passed: true`
- 答案与标准答案不一致，或无法作答 → `passed: false`，同时记录为 `failed_quiz` issue（severity 固定为 error）写入 audience-review.json

如果 `content-quiz.json` 不存在，跳过此步。

#### F. 节奏与连贯性

按 shot_order 连续"观看"所有 shot 的 content 和 duration_seconds：

- 是否有段落让你觉得画面一直在闪切，还没看清就跳到下一个了？
- 到了一个新场景时，是否有足够的时间让你认出这是哪里、谁在场？
- 高潮段落是否给了你足够的停留去感受情绪，还是一闪而过？

**问自己：如果我是第一次看这个视频，节奏舒服吗？有没有段落让我觉得喘不过气或者看不清？**

issue type: `fragmented_pacing`

### Step 3: 写入审查报告

将审查结果写入 `{project_path}/audience-review.json`：

```json
{
  "status": "PASS | HAS_ISSUES",
  "issues": [
    {
      "type": "missing_visual_coverage | incomplete_event | broken_causality | state_jump | semantic_error | failed_quiz",
      "severity": "error | warning",
      "event_id": "evt_xxx",
      "shot_id": "evt_xxx_shot_N（如适用）",
      "description": "用一句话描述观众会感到什么困惑",
      "detail": "具体哪个状态变化/动作/因果链缺失",
      "question_id": "仅 failed_quiz 类型填写，对应 content-quiz.json 中的题目 ID",
      "audience_answer": "仅 failed_quiz 类型填写，观众基于 content 给出的答案"
    }
  ],
  "summary": {
    "total_events": 10,
    "events_with_issues": 3,
    "errors": 2,
    "warnings": 1
  }
}
```

**severity 判断：**
- **error**：观众一定会注意到的问题（关键动作缺失、状态无理由跳变、因果断裂）
- **warning**：观众可能会注意到的问题（次要动作跳过、过渡略显突兀但能理解）

无问题则 `status: "PASS"`，`issues: []`。

## 输出

在项目路径下生成：
- `audience-review.json` — 审查报告
- `content-quiz-result.json` — 答题测试结果（如有 content-quiz.json）

## 错误处理

- **项目文件缺失**：报告调用方，说明缺少哪个文件。
- **content-quiz.json 不存在**：跳过 Step 2E，其他维度正常审查。
