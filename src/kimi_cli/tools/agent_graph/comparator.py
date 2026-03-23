"""Three-way comparison engine for ExecutionPlans."""

from __future__ import annotations

from kimi_cli.tools.display import ExecutionPlan, Gap, PlanComparison, PlanStep


def _build_step_index(plan: ExecutionPlan) -> dict[str, PlanStep]:
    return {s.id: s for s in plan.steps}


def _signature(step: PlanStep) -> tuple[str, str, str]:
    """Produce a comparable signature for a step: (kind, agent, tool)."""
    return (step.kind, step.agent.lower(), step.tool.lower())


def _match_steps(
    base: ExecutionPlan,
    other: ExecutionPlan,
) -> tuple[list[tuple[PlanStep, PlanStep]], list[PlanStep], list[PlanStep]]:
    """Match steps between two plans by signature similarity.

    Returns:
        (matched_pairs, unmatched_in_base, unmatched_in_other)
    """
    base_steps = list(base.steps)
    other_steps = list(other.steps)
    matched: list[tuple[PlanStep, PlanStep]] = []
    used_other: set[int] = set()

    for bs in base_steps:
        bs_sig = _signature(bs)
        best_idx = -1
        best_score = 0
        for i, os in enumerate(other_steps):
            if i in used_other:
                continue
            os_sig = _signature(os)
            score = sum(a == b for a, b in zip(bs_sig, os_sig))
            # Boost score if labels share words
            common_words = set(bs.label.lower().split()) & set(os.label.lower().split())
            score += len(common_words) * 0.5
            if score > best_score:
                best_score = score
                best_idx = i
        # Require at least kind+agent match (score >= 2) or kind+tool match
        if best_idx >= 0 and best_score >= 1.5:
            matched.append((bs, other_steps[best_idx]))
            used_other.add(best_idx)

    unmatched_base = [s for i, s in enumerate(base_steps) if s not in [m[0] for m in matched]]
    unmatched_other = [s for i, s in enumerate(other_steps) if i not in used_other]

    return matched, unmatched_base, unmatched_other


def _compare_pair(
    a: ExecutionPlan,
    b: ExecutionPlan,
    a_label: str,
    b_label: str,
) -> list[Gap]:
    """Compare two execution plans and produce gaps."""
    gaps: list[Gap] = []
    layers = (a_label, b_label)

    matched, only_a, only_b = _match_steps(a, b)

    # Missing steps: in A but not in B
    for step in only_a:
        gaps.append(Gap(
            gap_type="missing_step",
            layers=layers,
            step_id=step.id,
            description=f"'{step.label}' exists in {a_label} but has no match in {b_label}",
            severity="warning",
            suggestion=f"Consider whether {b_label} should include this step",
        ))

    # Extra steps: in B but not in A
    for step in only_b:
        gaps.append(Gap(
            gap_type="extra_step",
            layers=layers,
            step_id=step.id,
            description=f"'{step.label}' exists in {b_label} but has no match in {a_label}",
            severity="info",
            suggestion=f"Check if this step is necessary or can be removed",
        ))

    # Tool differences in matched pairs
    for sa, sb in matched:
        if sa.tool and sb.tool and sa.tool.lower() != sb.tool.lower():
            gaps.append(Gap(
                gap_type="tool_diff",
                layers=layers,
                step_id=sa.id,
                description=(
                    f"Step '{sa.label}' uses '{sa.tool}' in {a_label} "
                    f"but '{sb.tool}' in {b_label}"
                ),
                severity="info",
                suggestion="Evaluate which tool choice is more appropriate",
            ))

        # Resource differences
        a_in = set(sa.resources_in)
        b_in = set(sb.resources_in)
        if a_in and b_in and a_in != b_in:
            gaps.append(Gap(
                gap_type="resource_diff",
                layers=layers,
                step_id=sa.id,
                description=(
                    f"Step '{sa.label}' consumes different resources: "
                    f"{a_label}={sorted(a_in)}, {b_label}={sorted(b_in)}"
                ),
                severity="info",
            ))

    # Order / parallelism differences
    if a.step_order and b.step_order:
        # Compare sequential batch count
        a_serial = len(a.step_order)
        b_serial = len(b.step_order)
        if a_serial != b_serial:
            gaps.append(Gap(
                gap_type="order_diff",
                layers=layers,
                description=(
                    f"{a_label} has {a_serial} sequential batches, "
                    f"{b_label} has {b_serial}"
                ),
                severity="warning" if abs(a_serial - b_serial) > 1 else "info",
                suggestion="Fewer sequential batches = more parallelism = faster execution",
            ))

        # Check for parallelism differences
        a_parallel_count = sum(1 for batch in a.step_order if len(batch) > 1)
        b_parallel_count = sum(1 for batch in b.step_order if len(batch) > 1)
        if a_parallel_count != b_parallel_count:
            gaps.append(Gap(
                gap_type="parallel_diff",
                layers=layers,
                description=(
                    f"{a_label} has {a_parallel_count} parallel batches, "
                    f"{b_label} has {b_parallel_count}"
                ),
                severity="info",
                suggestion="More parallel batches can improve throughput",
            ))

    return gaps


def _diagnose(gaps: list[Gap]) -> str:
    """Generate a high-level diagnosis from gaps."""
    ideal_vs_predicted = [g for g in gaps if g.layers == ("ideal", "predicted")]
    predicted_vs_actual = [g for g in gaps if g.layers == ("predicted", "actual")]
    ideal_vs_actual = [g for g in gaps if g.layers == ("ideal", "actual")]

    parts: list[str] = []

    if ideal_vs_predicted:
        n_warn = sum(1 for g in ideal_vs_predicted if g.severity in ("warning", "error"))
        if n_warn > 0:
            parts.append(
                f"Prompt 设计问题（{n_warn} 个警告）：prompt 没有引导 agent 走最优路径。"
                f"主要差异包括步骤缺失或顺序不同。"
            )
        else:
            parts.append("Prompt 设计与理想方案基本一致。")

    if predicted_vs_actual:
        n_warn = sum(1 for g in predicted_vs_actual if g.severity in ("warning", "error"))
        if n_warn > 0:
            parts.append(
                f"执行偏差（{n_warn} 个警告）：agent 实际行为偏离了 prompt 的预期。"
                f"可能是 prompt 规则不够强，或 LLM 在执行时忽略了某些约束。"
            )
        else:
            parts.append("Agent 实际行为基本遵循 prompt 设计。")

    if ideal_vs_actual:
        n_warn = sum(1 for g in ideal_vs_actual if g.severity in ("warning", "error"))
        if n_warn > 0:
            # Determine root cause
            prompt_issues = len([g for g in ideal_vs_predicted if g.severity in ("warning", "error")])
            exec_issues = len([g for g in predicted_vs_actual if g.severity in ("warning", "error")])
            if prompt_issues > exec_issues:
                parts.append(
                    f"整体效果差距主要来自 prompt 设计——agent 忠实执行了 prompt，"
                    f"但 prompt 本身的方案不是最优的。优先优化 prompt。"
                )
            elif exec_issues > prompt_issues:
                parts.append(
                    f"整体效果差距主要来自执行偏差——prompt 设计接近最优，"
                    f"但 agent 没有准确执行。需要加强 prompt 约束力或改进工具。"
                )
            else:
                parts.append(
                    f"整体效果差距来自两方面：prompt 设计和执行偏差都有贡献。"
                )
        else:
            parts.append("实际执行与理想方案接近，系统运行良好。")

    return "\n".join(parts) if parts else "分析完成，未发现显著差异。"


def compare(
    ideal: ExecutionPlan | None,
    predicted: ExecutionPlan | None,
    actual: ExecutionPlan | None,
    task_description: str = "",
) -> PlanComparison:
    """Perform three-way comparison of execution plans.

    Any layer can be None — comparison will use available layers.

    Args:
        ideal: Layer 1 ideal plan (LLM-generated).
        predicted: Layer 2 predicted behavior (from prompt).
        actual: Layer 3 actual execution trace.
        task_description: The task being analyzed.

    Returns:
        PlanComparison with gaps and diagnosis.
    """
    gaps: list[Gap] = []

    if ideal and predicted:
        gaps.extend(_compare_pair(ideal, predicted, "ideal", "predicted"))
    if predicted and actual:
        gaps.extend(_compare_pair(predicted, actual, "predicted", "actual"))
    if ideal and actual:
        gaps.extend(_compare_pair(ideal, actual, "ideal", "actual"))

    # Sort: errors first, then warnings, then info
    severity_order = {"error": 0, "warning": 1, "info": 2}
    gaps.sort(key=lambda g: severity_order.get(g.severity, 3))

    diagnosis = _diagnose(gaps)

    return PlanComparison(
        task_description=task_description or (actual or predicted or ideal or ExecutionPlan(
            source="ideal", task_description="", steps=[]
        )).task_description,
        ideal=ideal,
        predicted=predicted,
        actual=actual,
        gaps=gaps,
        diagnosis=diagnosis,
    )
