
---

The above is a list of messages in a **video camera** agent conversation. Compact this context while preserving all information needed to continue the shot-by-shot generation workflow.

**Must Preserve (verbatim if possible):**
1. **Project identity**: project_path (absolute path)
2. **Meta info**: style_prefix, negative_prefix, aspect_ratio, language
3. **Current progress**: 当前正在处理哪个 shot（shot_id），shot_order 中的位置（第 N / 共 M 个）
4. **Per-shot status summary**: 每个 shot 的 status（done / degraded / failed / planned / in_progress），失败的 shot 记录 error
5. **Active shot plan**: 当前 in_progress 的 shot 的完整 plan（provider、video_mode、reference_images、audio_strategy、need_tts、need_tail_frame、need_first_frame）
6. **Active shot steps**: 当前 in_progress 的 shot 已完成和未完成的步骤（tail_frame / first_frame / video / tts）
7. **Pending retries**: 需要重试的 shot 列表和重试原因
8. **Parallel batch**: 当前并行批次中的 shot 列表和各自状态

**Compress:**
- 已完成（done/degraded）shot 的详细 prompt → 只保留 shot_id + status + provider + mode（prompt 已写入 generation-status.json）
- 工具调用的完整参数 → 只保留关键参数（output_path、mode、provider）
- guide 文件的完整内容 → 不保留（按需重新 ReadFile 加载）

**Remove:**
- 已完成 shot 的完整 prompt 文本
- guide-prompt-video.md、guide-shot-strategy.md、guide-tool-capabilities.md 的完整内容
- shots.json、states.json、meta.json 的完整 JSON 内容（按需重新 ReadFile）
- 重复的错误信息（保留最后一次 + 出现次数）

**Output Structure:**

<project>
- project_path: [absolute path]
- style_prefix: [value]
- negative_prefix: [value]
- aspect_ratio: [value]
- language: [value]
</project>

<progress>
- total_shots: [N]
- done: [N]
- degraded: [N]
- failed: [N]
- in_progress: [N]
- planned: [N]
- current_shot: [shot_id] (第 [X] / 共 [N] 个)
</progress>

<completed_shots>
- [shot_id]: [status] ([provider], [mode])
- ...
</completed_shots>

<active_shot>
- shot_id: [id]
- plan: [full plan object]
- completed_steps: [list]
- next_step: [step name]
</active_shot>

<pending_issues>
- [shot_id]: [error message, retry count]
</pending_issues>
