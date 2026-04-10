#!/usr/bin/env python3
"""
Knowledge offline validation script.

Validates pending knowledge entries by:
1. Matching them to optimization points from historical sessions
2. Re-running the relevant sub-agent stage with knowledge injected
3. Evaluating results per the entry's eval_method
4. Updating knowledge status and score

Usage:
  python scripts/knowledge-validate.py [--knowledge-dir DIR] [--sessions-dir DIR]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Role mapping (same as task.py)
# ---------------------------------------------------------------------------

AGENT_TO_ROLE = {
    "video-screenwriter": "screenwriter",
    "screenwriter": "screenwriter",
    "video-director": "director",
    "director": "director",
    "video-camera": "camera",
    "camera": "camera",
    "video-editor": "editor",
    "editor": "editor",
    "video-composer": "composer",
    "composer": "composer",
    "video-audience": "audience",
    "audience": "audience",
    "art-designer": "art-designer",
    "video-producer": "producer",
    "producer": "producer",
}

ROLE_TO_AGENT = {}
for agent, role in AGENT_TO_ROLE.items():
    if role not in ROLE_TO_AGENT:
        ROLE_TO_AGENT[role] = agent

# Minimum number of optimization points to attempt validation
MIN_OPT_POINTS = 1

# Score threshold for verification (0-10 scale: 1.0 = 10% improvement)
SCORE_VERIFIED_THRESHOLD = 1.0
SCORE_DEPRECATED_THRESHOLD = -1.0

# Minimum distinct users for public knowledge
MIN_USERS_PUBLIC = 3


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_pending_knowledge(knowledge_dir: Path) -> dict[str, list[dict]]:
    """Load all pending knowledge entries, grouped by role."""
    pending_dir = knowledge_dir / "pending"
    if not pending_dir.exists():
        return {}

    result: dict[str, list[dict]] = {}
    for f in pending_dir.glob("*.yaml"):
        role = f.stem
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                pending = [e for e in data if e.get("status") == "pending"]
                if pending:
                    result[role] = pending
        except Exception as e:
            print(f"Warning: failed to read {f}: {e}", file=sys.stderr)
    return result


def load_all_optimization_points(sessions_dir: Path) -> list[dict]:
    """Load optimization points from all sessions."""
    points: list[dict] = []
    for f in sessions_dir.glob("*/optimization-points.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                points.extend(data)
        except Exception as e:
            print(f"Warning: failed to read {f}: {e}", file=sys.stderr)
    return points


def extract_user_id_from_session(session_id: str, sessions_dir: Path) -> str | None:
    """Try to extract user_id from session metadata."""
    meta_path = sessions_dir / session_id / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return meta.get("user_id")
        except Exception:
            pass
    # Fallback: try to infer from session output directory structure
    return "default"


# ---------------------------------------------------------------------------
# Matching: knowledge <-> optimization points
# ---------------------------------------------------------------------------

def match_knowledge_to_opt_points(
    knowledge: dict, role: str, opt_points: list[dict]
) -> list[dict]:
    """Find optimization points relevant to a knowledge entry.

    Matching criteria:
    - opt point's agent matches the knowledge's role
    - opt point's problem shares keywords with knowledge's problem
    """
    k_problem = knowledge.get("problem", "").lower()
    k_tags = set(knowledge.get("tags", []))

    matched = []
    for opt in opt_points:
        # Role match
        opt_agent = opt.get("agent", "")
        opt_role = AGENT_TO_ROLE.get(opt_agent, opt_agent)
        if opt_role != role:
            continue

        # Problem keyword overlap
        opt_problem = opt.get("problem", "").lower()
        if not opt_problem or not k_problem:
            continue

        # Substring matching: extract key phrases (2-4 chars) from knowledge problem,
        # check how many appear in the opt point's problem.
        # This handles Chinese text without word segmentation.
        import re as _re

        def _extract_ngrams(s: str, min_n: int = 2, max_n: int = 4) -> set[str]:
            """Extract character n-grams from text (after removing punctuation/spaces)."""
            clean = _re.sub(r'[\s，、。；：！？,;:!?\(\)\[\]\{\}]+', '', s)
            ngrams: set[str] = set()
            for n in range(min_n, max_n + 1):
                for i in range(len(clean) - n + 1):
                    ngrams.add(clean[i:i + n])
            return ngrams

        k_ngrams = _extract_ngrams(k_problem)
        o_ngrams = _extract_ngrams(opt_problem)
        overlap = k_ngrams & o_ngrams
        # Require significant overlap relative to the smaller set
        min_size = min(len(k_ngrams), len(o_ngrams)) or 1
        overlap_ratio = len(overlap) / min_size
        if overlap_ratio >= 0.3:
            matched.append(opt)

    return matched


# ---------------------------------------------------------------------------
# Re-run sub-agent
# ---------------------------------------------------------------------------

async def rerun_subagent(
    agent_name: str,
    prompt: str,
    context_files: list[str],
    knowledge_rule: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Re-run a sub-agent with knowledge injected, return op graph metrics.

    Returns dict with keys: error_count, tool_call_count, duration_s, tokens
    """
    from kaos.path import KaosPath
    from kimi_cli.agentspec import get_agents_dir
    from kimi_cli.app import KimiCLI
    from kimi_cli.session import Session
    from web.op_graph import parse_chat_to_op_graph

    # Find agent file
    agent_file = get_agents_dir() / agent_name / "agent.yaml"
    if not agent_file.exists():
        # Try with video- prefix
        agent_file = get_agents_dir() / f"video-{agent_name}" / "agent.yaml"
    if not agent_file.exists():
        return {"error": f"Agent file not found for {agent_name}"}

    work_dir = KaosPath.unsafe_from_local_path(Path.cwd())

    # Create a temporary session for the re-run
    session = await Session.create(work_dir)
    session_output_dir = output_dir / f"validate_{session.id}"
    session_output_dir.mkdir(parents=True, exist_ok=True)

    # Inject knowledge rule into a temporary file
    knowledge_file = session_output_dir / "injected_knowledge.md"
    knowledge_file.write_text(
        f"以下是经过验证的领域知识，请在工作中参考：\n\n1. {knowledge_rule}\n",
        encoding="utf-8",
    )

    # Build effective context_files with knowledge
    effective_context = list(context_files) + [str(knowledge_file)]

    # Build prompt with context files
    parts = []
    for fp in effective_context:
        p = Path(fp)
        if p.exists():
            content = p.read_text(encoding="utf-8")
            if len(content) > 50_000:
                content = content[:50_000] + f"\n... [truncated]"
            parts.append(f"<file path=\"{fp}\">\n{content}\n</file>")
    effective_prompt = "\n".join(parts) + "\n\n" + prompt if parts else prompt

    try:
        cli = await KimiCLI.create(
            session,
            agent_file=agent_file,
            session_output_dir=str(session_output_dir),
            yolo=True,
        )
        cancel = asyncio.Event()
        async for _ in cli.run(effective_prompt, cancel):
            pass

        # Parse the re-run's chat.jsonl to get metrics
        chat_path = Path(cli.session.context_file).parent / "chat.jsonl"
        # The session's chat.jsonl might be in the session dir
        if not chat_path.exists():
            # Try the session output dir
            for candidate in session_output_dir.rglob("chat.jsonl"):
                chat_path = candidate
                break

        if chat_path.exists():
            op_graph = parse_chat_to_op_graph(chat_path)
            metrics = op_graph.get("metrics", {})
            return {
                "error_count": metrics.get("error_count", 0),
                "tool_call_count": metrics.get("tool_call_count", 0),
                "duration_s": metrics.get("total_duration_s", 0),
                "total_tokens": metrics.get("total_input_tokens", 0) + metrics.get("total_output_tokens", 0),
            }
        else:
            return {"error": "No chat.jsonl found after re-run"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_metrics(
    eval_method: str,
    baseline: dict,
    rerun: dict,
) -> tuple[float, str]:
    """Evaluate using metrics comparison.

    Returns (score, description).
    Score > 0 means improvement, < 0 means regression.
    """
    if "error" in rerun:
        return 0.0, f"Re-run failed: {rerun['error']}"

    # Parse which metric to compare
    metric_name = eval_method.replace("metrics:", "").strip()

    baseline_val = baseline.get(metric_name, 0)
    rerun_val = rerun.get(metric_name, 0)

    if baseline_val == 0:
        if rerun_val == 0:
            return 0.0, f"{metric_name}: baseline=0, rerun=0, no change"
        else:
            return -1.0, f"{metric_name}: baseline=0, rerun={rerun_val}, regression"

    improvement = (baseline_val - rerun_val) / baseline_val
    desc = f"{metric_name}: baseline={baseline_val}, rerun={rerun_val}, improvement={improvement:.1%}"
    return improvement, desc


def evaluate_case(
    eval_method: str,
    baseline_metrics: dict,
    rerun_metrics: dict,
) -> tuple[float, str]:
    """Evaluate a single validation case.

    Routes to the appropriate evaluator based on eval_method prefix.
    """
    if eval_method.startswith("metrics:"):
        return evaluate_metrics(eval_method, baseline_metrics, rerun_metrics)
    elif eval_method.startswith("vlm:"):
        # VLM evaluation requires image/video analysis
        # For now, return a placeholder — full VLM eval requires AnalyzeImage tool
        return 0.0, f"VLM evaluation not yet implemented: {eval_method}"
    else:
        # Try as generic metrics comparison
        return evaluate_metrics(f"metrics: {eval_method}", baseline_metrics, rerun_metrics)


# ---------------------------------------------------------------------------
# Knowledge promotion
# ---------------------------------------------------------------------------

def promote_knowledge(
    entry: dict,
    role: str,
    user_ids: set[str],
    knowledge_dir: Path,
) -> str:
    """Write a verified knowledge entry to public or user knowledge library.

    Returns the destination ("public" or "users/{user_id}").
    """
    entry_online = dict(entry)
    entry_online["status"] = "online"

    if len(user_ids) >= MIN_USERS_PUBLIC:
        dest_file = knowledge_dir / "public" / f"{role}.yaml"
        dest_label = "public"
    else:
        user_id = next(iter(user_ids), "default")
        dest_file = knowledge_dir / "users" / user_id / f"{role}.yaml"
        dest_label = f"users/{user_id}"

    dest_file.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    if dest_file.exists():
        try:
            existing = yaml.safe_load(dest_file.read_text(encoding="utf-8")) or []
        except Exception:
            existing = []

    # Avoid duplicates
    existing_ids = {e.get("id") for e in existing}
    if entry_online.get("id") not in existing_ids:
        existing.append(entry_online)
        dest_file.write_text(
            yaml.dump(existing, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    return dest_label


# ---------------------------------------------------------------------------
# Main validation loop
# ---------------------------------------------------------------------------

async def validate_knowledge(
    knowledge_dir: Path,
    sessions_dir: Path,
) -> None:
    """Main validation loop."""
    print("Loading pending knowledge...")
    pending_by_role = load_pending_knowledge(knowledge_dir)
    if not pending_by_role:
        print("No pending knowledge to validate.")
        return

    print("Loading optimization points...")
    all_opt_points = load_all_optimization_points(sessions_dir)
    if not all_opt_points:
        print("No optimization points found. Run evolver analysis first.")
        return

    total_pending = sum(len(v) for v in pending_by_role.values())
    print(f"Found {total_pending} pending entries, {len(all_opt_points)} optimization points.\n")

    validated_count = 0
    promoted_count = 0

    for role, entries in pending_by_role.items():
        print(f"=== Role: {role} ({len(entries)} pending) ===")

        for entry in entries:
            kid = entry.get("id", "?")
            rule = entry.get("rule", "")
            eval_method = entry.get("eval_method", "")
            print(f"\n  [{kid}] {rule[:60]}...")

            if not eval_method:
                print(f"    SKIP: no eval_method defined")
                continue

            # Match to optimization points
            matched_opts = match_knowledge_to_opt_points(entry, role, all_opt_points)
            if len(matched_opts) < MIN_OPT_POINTS:
                print(f"    SKIP: only {len(matched_opts)} matching opt points (need >= {MIN_OPT_POINTS})")
                continue

            print(f"    Matched {len(matched_opts)} optimization points")

            # Validate against each optimization point
            case_scores: list[float] = []
            case_details: list[dict] = []
            user_ids: set[str] = set()

            for opt in matched_opts:
                opt_id = opt.get("id", "?")
                session_id = opt.get("session", "")
                agent_name = opt.get("agent", "")
                baseline = opt.get("baseline_metrics", {})
                task_params = opt.get("task_params", {})
                prompt = task_params.get("prompt", "")
                context_files = task_params.get("context_files", [])

                if not prompt:
                    print(f"    [{opt_id}] SKIP: no prompt in task_params")
                    continue

                print(f"    [{opt_id}] Re-running {agent_name}...", end=" ", flush=True)

                # Determine output dir for re-run
                validate_output = sessions_dir / session_id / ".validate"
                validate_output.mkdir(parents=True, exist_ok=True)

                # Re-run with knowledge
                rerun_metrics = await rerun_subagent(
                    agent_name=agent_name,
                    prompt=prompt,
                    context_files=context_files,
                    knowledge_rule=rule,
                    output_dir=validate_output,
                )

                # Evaluate
                score, desc = evaluate_case(eval_method, baseline, rerun_metrics)
                print(f"score={score:.2f} ({desc})")

                case_scores.append(score)
                case_details.append({
                    "opt_id": opt_id,
                    "session": session_id,
                    "score": round(score, 3),
                    "description": desc,
                })

                # Track user
                uid = extract_user_id_from_session(session_id, sessions_dir)
                if uid:
                    user_ids.add(uid)

            if not case_scores:
                print(f"    No valid cases evaluated")
                continue

            # Aggregate score: improvement ratio (0~1) × 10 → 0~10 scale
            avg_ratio = sum(case_scores) / len(case_scores)
            score_10 = round(max(-10.0, min(10.0, avg_ratio * 10)), 1)
            entry["score"] = score_10
            # Human-readable explanation of the score
            pct = abs(round(avg_ratio * 100))
            direction = "改善" if avg_ratio >= 0 else "恶化"
            entry["score_meaning"] = f"{len(case_scores)} 个 case 平均{direction} {pct}%"
            entry["validation"] = {
                "cases": case_details,
                "avg_improvement_ratio": round(avg_ratio, 3),
                "score": score_10,
                "validated_at": time.strftime("%Y-%m-%d"),
            }

            # Update status
            if avg_score > SCORE_VERIFIED_THRESHOLD:
                entry["status"] = "verified"
                validated_count += 1
                print(f"    VERIFIED (avg_score={avg_score:.3f})")

                # Promote to knowledge library
                dest = promote_knowledge(entry, role, user_ids, knowledge_dir)
                promoted_count += 1
                print(f"    Promoted to {dest}")
            elif avg_score < SCORE_DEPRECATED_THRESHOLD:
                entry["status"] = "deprecated"
                print(f"    DEPRECATED (avg_score={avg_score:.3f})")
            else:
                print(f"    INCONCLUSIVE (avg_score={avg_score:.3f}), keeping pending")

        # Write back updated pending entries
        pending_file = knowledge_dir / "pending" / f"{role}.yaml"
        all_entries = []
        if pending_file.exists():
            try:
                all_entries = yaml.safe_load(pending_file.read_text(encoding="utf-8")) or []
            except Exception:
                all_entries = []

        # Update entries in-place by id
        entry_map = {e.get("id"): e for e in entries}
        for i, e in enumerate(all_entries):
            eid = e.get("id")
            if eid in entry_map:
                all_entries[i] = entry_map[eid]

        pending_file.write_text(
            yaml.dump(all_entries, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    print(f"\nDone. Validated: {validated_count}, Promoted: {promoted_count}")


def main():
    parser = argparse.ArgumentParser(description="Validate pending knowledge entries")
    parser.add_argument("--knowledge-dir", default="knowledge",
                        help="Path to knowledge directory")
    parser.add_argument("--sessions-dir", default="output/.sessions",
                        help="Path to sessions directory")
    args = parser.parse_args()

    asyncio.run(validate_knowledge(
        knowledge_dir=Path(args.knowledge_dir),
        sessions_dir=Path(args.sessions_dir),
    ))


if __name__ == "__main__":
    main()
