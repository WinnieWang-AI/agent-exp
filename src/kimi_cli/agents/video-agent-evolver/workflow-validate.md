# 知识离线验证流程

本文件描述验证流程的设计规范，实际执行由 `scripts/knowledge-validate.py` 完成。

## 输入

- `knowledge/pending/{role}.yaml` — 待验证知识条目（含 rule、problem、eval_method）
- `output/.sessions/*/optimization-points.yaml` — 各 session 的优化点

## 流程

### Step 1: 加载待验证知识

读取 `knowledge/pending/` 下所有角色文件，筛选 `status=pending` 的条目。

### Step 2: 匹配优化点

对每条 pending 知识，从所有 session 的 optimization-points.yaml 中匹配相关优化点：

匹配条件：
- 优化点的 `agent` 与知识的角色 tag 对应
- 优化点的 `problem` 与知识的 `problem` 语义相关（关键词匹配或嵌入相似度）

匹配结果：一条知识对应 N 个优化点（N 个可验证的 case）。

如果匹配到的优化点不足（< 3 个），暂不验证，等待更多 session 数据积累。

### Step 3: 重跑子 agent 阶段

对每个匹配的优化点：

1. 从优化点的 `task_params` 获取原始调用参数（prompt + context_files）
2. 将知识的 `rule` 注入到 context_files 中（生成临时知识文件）
3. 调用对应子 agent 执行（通过 KimiCLI 编程式调用）
4. 收集重跑的 op graph metrics

### Step 4: 按 eval_method 评估

根据知识条目的 `eval_method` 选择评估方式：

**metrics 类评估**（eval_method 以 `metrics:` 开头）：
- `metrics: error_count` — 对比重跑的 error_count vs baseline_metrics.error_count
- `metrics: retry_count` — 对比重试次数
- `metrics: duration` — 对比耗时
- 收益 = (baseline - rerun) / baseline

**VLM 类评估**（eval_method 以 `vlm:` 开头）：
- 用 AnalyzeImage 工具评估重跑产出的图片/视频
- 评估维度从 eval_method 中提取（如 `vlm: 面部一致性`）
- 与 baseline 产出进行对比评分（0-10 分）
- 收益 = (rerun_score - baseline_score) / 10

### Step 5: 计算 score 并更新状态

对一条知识的所有验证 case 汇总：
- `score` = 所有 case 改善比例的平均值 × 10，范围 0~10（10 = 100% 改善）
- `validation` = 各 case 的详细结果记录（case_id、session、单项得分、评估描述）
- `score_meaning` = 对分数的一句话解释（如："3 个 case 平均减少 45% 错误"）

判定标准：
- score > 1.0（即平均改善 10% 以上）→ `status=verified`
- score ≤ 1.0 → 保持 `status=pending`，记录 validation 结果供人工参考
- score < -1.0（负收益）→ `status=deprecated`

### Step 6: 写入知识库

**通用/个性化判定**：
- 统计验证 case 涉及的不同 user_id
- 跨 ≥3 个不同用户均有效 → 写入 `knowledge/public/{role}.yaml`，status=online
- 仅对 ≤2 个用户有效 → 写入 `knowledge/users/{user_id}/{role}.yaml`，status=online

**写入时必须保留以下字段**（缺失任一则为数据不完整）：
- `rule` + `rationale`：规则本体和原因
- `problem` + `eval_method`：解决什么问题、怎么验证
- `source`（含 `session` + `evidence` + `extracted_at`）：从哪来的
- `score` + `score_meaning`：得了多少分、分数含义
- `validation`（含 `cases` 列表 + `avg_score` + `validated_at`）：每个验证 case 的详情

## 输出

- 更新 `knowledge/pending/{role}.yaml` 中条目的 status、score、validation
- 验证通过的条目复制到 `knowledge/public/` 或 `knowledge/users/`，status=online
- 验证日志输出到 stdout

## 运行方式

```bash
python scripts/knowledge-validate.py [--knowledge-dir knowledge/] [--sessions-dir output/.sessions/]
```
