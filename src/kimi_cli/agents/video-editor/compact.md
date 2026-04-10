
---

The above is a list of messages in a **video editor** agent conversation. Compact this context while preserving all information needed to continue the assembly workflow.

**Must Preserve (verbatim if possible):**
1. **Project identity**: project_path (absolute path)
2. **Current workflow step**: 当前在哪个步骤（裁剪 / 转场+拼接 / BGM叠加 / 字幕 / 校准验证），下一步是什么
3. **Shot order**: shot_order 列表（shot_id 顺序）
4. **Per-step output**: 每个已完成步骤的输出文件路径（裁剪后片段、拼接结果、混音结果、最终成片）
5. **Pending operations**: 未完成的操作和原因
6. **BGM info**: BGM 文件路径、时间线编排（哪段 BGM 对应哪些 shot）
7. **Missing assets**: 缺失的素材列表（已上报调用方的）
8. **Subtitle data**: SRT 文件路径（如已生成）

**Compress:**
- VideoEdit 工具调用的完整参数 → 只保留操作类型 + 输入输出路径
- shots.json / music-status.json 的完整内容 → 只保留已提取的关键字段
- guide-timeline.md 的完整内容 → 不保留（按需重新 ReadFile）

**Remove:**
- workflow-assemble.md、guide-timeline.md 的完整内容
- 已被后续步骤覆盖的中间文件路径
- 重复的错误信息（保留最后一次 + 出现次数）

**Output Structure:**

<project>
- project_path: [absolute path]
- total_shots: [N]
- shot_order: [shot_id_1, shot_id_2, ...]
</project>

<workflow_state>
- current_step: [裁剪 / 转场+拼接 / BGM叠加 / 字幕 / 校准验证]
- next_action: [下一步要做什么]
</workflow_state>

<completed_steps>
- 裁剪: [done/pending] → [output paths or count]
- 拼接: [done/pending] → [output path]
- BGM叠加: [done/pending] → [output path]
- 字幕: [done/pending] → [srt path + output path]
- 校准验证: [done/pending] → [final output path]
</completed_steps>

<bgm_info>
- bgm_path: [path]
- timeline: [arrangement summary]
</bgm_info>

<pending_issues>
- [issue description]
</pending_issues>
