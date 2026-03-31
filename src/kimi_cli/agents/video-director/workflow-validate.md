# 校验

## 输入

项目目录下已有导演全部产出：
- `meta.json`、`entities.json`、`events.json`、`states.json`、`shots.json`

## 步骤

### Step 1: 调用校验工具

使用 `ValidateDirectorOutput` 工具，传入项目路径：

```
ValidateDirectorOutput(project_path="{project_path}")
```

工具会自动执行所有跨文件一致性检查：
- entities → events 引用正确
- states → entities 引用正确
- active_during → events 覆盖完整（每个角色/场景/道具在每个事件中有且仅有一个状态）
- shots → events 引用正确，每个事件至少有一个 shot
- shots → states 的 focus_on 引用正确且与 active_during 一致
- 对白分配完整无遗漏无重复
- 总时长与目标时长偏差 ≤ 10%
- 参考图文件存在（warning，不阻塞——参考图由制片人单独调度美术生成）
- 事件时序无环、无孤立事件
- shot ID 唯一

工具会将校验报告写入 `{project_path}/validation-report.json`。

### Step 2: 处理结果

根据工具返回的结果：

**PASS（无 error）：**
- 向调用方汇报校验通过，附带统计摘要（实体数、事件数、状态数、镜头数、总时长）

**FAIL（有 error）：**
- 检查 errors 列表，尝试自动修复可修复的问题：
  - 剧本对白未提取到 events → 从 act-{N}.json 读取 dialogue 类型 beats，补入对应事件的 dialogues 数组，再将新增对白分配到合适的 shot
  - focus_on 引用错误 → 查找正确的状态 ID 替换
  - events→shots 对白遗漏 → 分配到合适的 shot
  - total_duration_seconds 计算错误 → 重新计算
- 修复后重新调用 ValidateDirectorOutput 复检
- 不可自动修复的问题报告给调用方

## 输出

- `{project_path}/validation-report.json` — 校验报告（由工具自动生成）

## 错误处理

- **项目目录不存在**：报告调用方。
- **核心文件缺失**：报告调用方缺少哪些文件。
