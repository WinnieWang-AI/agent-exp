# 观众审查问题修复参考

制片人转来观众审查发现的问题时，加载本文件。按 issue type 选择修复方式。

## 修复方式

| issue type | 修复方式 |
|------------|---------|
| missing_visual_coverage | 补 shot 或在现有 shot 的 content 中补充变化过程 |
| incomplete_event | 补 shot 覆盖缺失的动作 |
| broken_causality | 补过渡 shot 或调整前后 shot 的 content 建立因果 |
| state_jump | 补 state_changes 或调整 active_during |
| failed_quiz | 对照标准答案，在 content 中补充缺失的空间位置信息，使观众仅凭 content 能答对 |

修复后重新执行校验（workflow-validate.md）。
