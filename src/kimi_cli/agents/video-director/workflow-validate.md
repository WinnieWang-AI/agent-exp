# 校验

## 输入

项目目录下已有导演全部产出：
- `meta.json`、`entities.json`、`events.json`、`states.json`、`shots.json`

## 步骤

### Step 1: 语义自检

在调用工具前，逐事件审查以下两项。发现问题直接修复（补 shot、调整 content、补 state_changes），不只是记录。

#### A. 状态变化的视觉覆盖

遍历每个 event 的 `state_changes`，对每个变化判断：

- **镜头内发生**（变化过程是观众需要看到的，如：物体被打碎、角色换装、天气突变）→ 必须有 shot 表现变化过程，不能只展示变化后的结果
- **离场发生**（变化发生在镜头外，观众能从上下文推断，如：A 让 B 去修东西，下一场 B 拿着修好的东西回来）→ 可以不展示过程，但前后 shot 的 content 要让观众能推断出发生了什么

判断依据：变化的发起动作是否在当前事件的 shots 中可见。如果发起动作在镜头内（角色当场做了某事），过程就应该在镜头内；如果发起动作是指令性的（"去做 X"），过程可以离场。

缺失视觉覆盖的 → 补一个过渡 shot 或在现有 shot 的 content 中补充变化过程描述。

#### B. 事件覆盖完整性

对每个 event，检查其 shots 是否完整表达了事件意图：

- event 的核心 interactions 是否都有对应 shot 表现
- 关键 state_changes 是否有镜头支撑（与 A 联动）
- 相邻 event 之间的因果衔接：如果 event B 的前提是 event A 的结果，shots 中是否建立了这个因果（观众能看到 A 的结果，才能理解 B 为什么发生）

缺失的 → 补 shot 或调整现有 shot 的 content。补 shot 后同步更新 `shots.json` 的 `shot_order` 和相关 `focus_on`。

### Step 2: 调用校验工具

使用 `ValidateDirectorOutput` 工具，传入项目路径：

```
ValidateDirectorOutput(project_path="{project_path}")
```

工具会自动执行所有跨文件一致性检查：
- entities → events 引用正确
- states → entities 引用正确
- active_during → events 覆盖完整（每个角色/场景/道具在每个事件中有状态覆盖）
- shots → events 引用正确，每个事件至少有一个 shot
- shots → states 的 focus_on 引用正确且与 active_during 一致
- 对白分配完整无遗漏无重复
- 总时长与目标时长偏差 ≤ 10%
- 参考图文件存在（warning，不阻塞——参考图由制片人单独调度美术生成）
- 事件时序无环、无孤立事件
- shot ID 唯一

工具会将校验报告写入 `{project_path}/validation-report.json`。

### Step 3: 处理结果

根据工具返回的结果：

**PASS（无 error）：**
- 向调用方汇报校验通过，附带统计摘要（实体数、事件数、状态数、镜头数、总时长）

**FAIL（有 error）：**
- 检查 errors 列表，尝试自动修复可修复的问题：
  - 剧本对白未提取到 events → 从 act-{N}.json 读取 dialogue 类型 beats，补入对应事件的 dialogues 数组，再将新增对白写入合适 shot 的 content 中
  - focus_on 引用错误 → 查找正确的状态 ID 替换
  - events→shots 对白遗漏 → 写入合适 shot 的 content 中
  - total_duration_seconds 计算错误 → 重新计算
- 修复后重新调用 ValidateDirectorOutput 复检
- 不可自动修复的问题报告给调用方

## 输出

- `{project_path}/validation-report.json` — 校验报告（由工具自动生成）

## 错误处理

- **项目目录不存在**：报告调用方。
- **核心文件缺失**：报告调用方缺少哪些文件。
