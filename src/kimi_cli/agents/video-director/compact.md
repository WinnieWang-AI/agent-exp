
---

The above is a list of messages in a **video production director** agent conversation. Compact this context while preserving all information needed to continue the video production workflow.

**Must Preserve (verbatim if possible):**
1. **Project identity**: project_name, all session_ids (`graph_*`, `create_*`, `create_audio_*`)
2. **User requirements**: 主题、视觉风格、画面比例、语言、时长
3. **Current workflow step**: 当前在哪个 Step（1/1.4/1.5/1.6/1.8a/1.8b/2a/2b/2c/3），下一步是什么
4. **Story structure summary**: 角色列表（id + 名称）、事件列表（id + 简述）、镜头数量
5. **Asset status**: 每个实体/状态的参考图生成状态（已生成/未生成/失败）、每个 shot 的视频生成状态、音频生成状态
6. **User confirmations**: 用户已确认的内容（故事结构、参考图、视频等）
7. **Pending issues**: 未解决的错误（错误码、错误消息）、用户的修改要求
8. **Output attempts**: 当前 attempt_n、最近一次输出 attempt 路径（相对项目目录）
9. **Output paths**: story-graph.json 路径、项目目录路径、最终输出路径
10. **Last error**: 最近一次错误（时间、agent、错误码、错误消息）及累计次数（如有）

**Compress:**
- Subagent 返回的详细报告 → 只保留结论（PASS/FAIL + 一句原因）
- 多轮重试的中间过程 → 只保留最终结果
- 评估细节 → 只保留每项的判定结果

**Remove:**
- 完整的 JSON 文件内容（story-graph.json、shot-plan.json 等）
- 重复的错误信息（保留最后一次 + 出现次数）
- Subagent prompt 的详细内容

**Output Structure:**

<project>
- project_name: [name]
- project_dir: [path]
- story_graph_path: [path]
- session_ids: graph_[x], create_[x], create_audio_[x]
</project>

<user_requirements>
- 主题: [topic]
- 风格: [style]
- 画面比例: [ratio]
- 语言: [language]
- 时长: [duration]
</user_requirements>

<workflow_state>
- current_step: [Step X.X]
- next_action: [what to do next]
- user_confirmed: [list of confirmed items]
- attempt_n: [N]
</workflow_state>

<story_summary>
- 角色: [id: name, ...]
- 事件: [id: brief, ...]
- 镜头数: [N]
- 音频: [BGM/对白 状态]
</story_summary>

<asset_status>
- 实体参考图: [id: status, ...]
- 状态参考图: [id: status, ...]
- Shot 视频: [id: status, ...]
- 音频: [id: status, ...]
- 最终输出: [path or 未生成]
</asset_status>

<pending_issues>
- [issue description + error info if any]
</pending_issues>
