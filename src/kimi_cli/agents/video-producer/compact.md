
---

The above is a list of messages in a **video production producer** agent conversation. Compact this context while preserving all information needed to continue the video production workflow.

**Must Preserve (verbatim if possible):**
1. **Project identity**: project_name, project_dir (absolute path), all session_ids (screenwriter/director/art/camera/composer/editor)
2. **User requirements**: 主题、风格、画面比例、语言、时长
3. **Current workflow phase**: 当前在哪个阶段（需求确认 / 项目初始化 / 剧本创作 / 制作规划 / 摄影+作曲 / 后期组装 / 交付），下一步是什么
4. **Screenplay summary**: 角色列表（id + 名称）、场景列表（id + 名称）、幕数、总场景数（从编剧回复中提取）
5. **Production plan summary**: 事件数、状态节点数、镜头数、总时长、校验结果（PASS/FAIL）
6. **Asset status**:
   - 参考图：实体图成功/失败数、状态图成功/失败数
   - 视频片段：成功/失败/总数（从 generation-status.json 摘要）
   - BGM：成功/失败/总数（从 music-status.json 摘要）
   - 成片：最近一次输出路径、attempt 编号
7. **User confirmations**: 用户已确认的阶段（剧本 / 制作计划 / 成片）
8. **Pending issues**: 未解决的错误（错误码、错误消息、出自哪个 agent）、用户的修改要求
9. **Key file paths**: meta.json / entities.json / events.json / states.json / shots.json / generation-status.json / music-status.json 的项目相对路径（不需要逐个列出内容）

**Compress:**
- Subagent 返回的详细报告 → 只保留结论（成功/失败 + 一句摘要）
- 导演校验报告 → 只保留 PASS/FAIL + 主要错误列表（如有）
- 多轮重试的中间过程 → 只保留最终结果
- 编剧返回的故事细节 → 只保留角色/场景/幕数

**Remove:**
- 完整的 JSON 文件内容（meta.json、entities.json、events.json、states.json、shots.json 等）
- 重复的错误信息（保留最后一次 + 出现次数）
- Subagent prompt 的详细内容（保留 subagent_name 和一句意图即可）
- 已被后续步骤覆盖的中间状态

**Output Structure:**

<project>
- project_name: [name]
- project_dir: [absolute path]
- session_ids: screenwriter_[x], director_[x], art_[x], camera_[x], composer_[x], editor_[x]
</project>

<user_requirements>
- 主题: [topic]
- 风格: [style]
- 画面比例: [ratio]
- 语言: [language]
- 时长: [duration]
</user_requirements>

<workflow_state>
- current_phase: [需求确认 / 项目初始化 / 剧本创作 / 制作规划 / 美术设计 / 摄影+作曲 / 后期组装 / 交付]
- next_action: [下一步要做什么]
- user_confirmed: [已确认的阶段列表]
- attempt_n: [N]（成片输出编号，首次为 1）
</workflow_state>

<screenplay_summary>
- 标题: [title]
- 角色: [id: name, ...]
- 场景: [id: name, ...]
- 幕数: [N]，总场景数: [N]
</screenplay_summary>

<production_plan_summary>
- 事件数: [N]
- 状态节点数: [N]
- 镜头数: [N]
- 总时长: [N]s
- 校验: [PASS / FAIL + 主要错误]
</production_plan_summary>

<asset_status>
- 参考图（实体）: 成功 [N] / 失败 [N]
- 参考图（状态）: 成功 [N] / 跳过 [N] / 失败 [N]
- 视频片段: 成功 [N] / 失败 [N] / 总 [N]
- BGM: 成功 [N] / 失败 [N] / 总 [N]
- 成片: [attempt_N.mp4 路径 or 未生成]
</asset_status>

<pending_issues>
- [issue: agent + error code + message, 出现次数]
</pending_issues>
