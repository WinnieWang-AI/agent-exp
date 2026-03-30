# 修改已有故事

## 输入

调用方通过 prompt 传入：
- **修改指令**：具体要改什么（如"把大灰狼改成狐狸"、"增加一个猎人的前史场景"、"删除第二幕第一场"）
- **故事文件**：通过 `context_files` 注入或指定项目路径

## 步骤

### Step 1: 读取现有故事

读取项目目录下的所有故事文件：
- `meta.json` — 了解视频规格
- `entities.json` — 了解现有角色/场景/道具
- `outline.json` — 了解故事结构
- 相关的 `act-{N}.json` — 了解需要修改的场景详情

如果 `context_files` 中已注入文件内容，直接使用，无需重复 ReadFile。

### Step 2: 分析修改范围

根据修改指令判断影响范围：

| 修改类型 | 影响的文件 |
|---------|-----------|
| 修改角色外形/特征 | entities.json |
| 增删角色 | entities.json + outline.json + 相关 act-{N}.json |
| 修改场景内容（对白、动作） | 相关 act-{N}.json |
| 增删场景 | outline.json + 相关 act-{N}.json |
| 调整场景顺序 | outline.json（可能影响 act-{N}.json 的分配） |
| 修改角色关系 | entities.json |
| 修改地点描述/区域 | entities.json + 使用该地点的 act-{N}.json 中的 location_state |
| 修改道具 | entities.json + 使用该道具的 act-{N}.json 中的 prop_states |
| 修改故事大纲（幕结构） | outline.json + act-{N}.json 文件名/内容 |

### Step 3: 执行修改

按影响范围逐个文件修改。修改时注意：

1. **保持 ID 稳定**：不要改变未受影响的元素的 ID。只有新增元素才分配新 ID。
2. **级联更新**：删除角色时，同时清理 outline 中的 `characters` 引用和 act 中的 `characters_present`、`character_states`、相关 beats。
3. **保留未受影响的内容**：只修改指令涉及的部分，不要重写整个文件。用 ReadFile 读取现有内容，修改后用 WriteFile 写回。
4. **场景 ID 递增**：新增场景的 ID 从现有最大编号继续递增，不复用已删除的 ID。

### Step 4: 自检一致性

修改完成后，检查受影响范围的一致性：

1. **ID 引用完整**：所有 outline/act 中引用的角色/场景/道具 ID 在 entities.json 中存在
2. **characters_present 一致**：角色列表与 beats 中实际出场的角色一致
3. **关系时间有效**：角色关系的 `from`/`until` 引用的场景 ID 仍然存在
4. **空间连贯**：角色不会在不合理的场景中突然出现
5. **状态连贯**：角色/地点/道具的状态变化在前后场景间合理衔接

发现问题直接修复。

## 输出

更新后的故事文件（只更新受影响的文件）。向调用方返回修改摘要：
- 修改了哪些文件
- 具体改了什么（如"将 char_wolf 的 name 改为狐狸，更新了 3 个场景中的 beats"）
- 是否发现并修复了一致性问题

## 错误处理

- **修改指令不明确**：报告调用方，说明需要澄清的具体问题。
- **修改导致逻辑矛盾**：尝试自动修复（如删除角色后补充替代情节）。无法自动修复时报告调用方。
- **文件读写失败**：重试 1 次，仍失败则报告调用方。
