#!/usr/bin/env python3
"""converge 编排器 — 用 scheduler library API 驱动 converge 循环。

状态追踪由 scheduler.py 管理，分支逻辑（reviewer → executor → feedback）
由本脚本实现。

用法: python converge_orchestrator.py --slug <slug> [--dir .workflow]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# scheduler library API
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "dynamic-workflow-skill" / "scripts"))
from scheduler import load_state, save_state, get_next_action, apply_result

CONVERGE_DIR = Path(__file__).parent.parent / ".converge" / "active"
WORKFLOW_DIR = Path(__file__).parent.parent / ".workflow"


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _converge_slug():
    return datetime.now(timezone.utc).strftime("%Y%m%d") + "-audit-mechanism"


# ==== prompt templates (自足，不依赖外部文件) ====

REVIEWER_PROMPT_TEMPLATE = """You are a plan reviewer in an iterative convergence loop. This is Round {round}.

## Convergence Object
The "audit mechanism" for the init-agent-docs skill — consisting of:
1. `assets/scripts/audit.py` — mechanical document consistency checker
2. `assets/templates/zh/audit-checklist.md.tpl` — agent-facing audit checklist template
3. Wiring changes in `SKILL.md` — step 1 (script copy), step 7 (self-check), step 9 (audit initialization)

## Required reading (in order)
1. C:\\Users\\chenr\\.agents\\skills\\init-agent-docs\\assets\\scripts\\audit.py
2. C:\\Users\\chenr\\.agents\\skills\\init-agent-docs\\assets\\templates\\zh\\audit-checklist.md.tpl
3. C:\\Users\\chenr\\.agents\\skills\\init-agent-docs\\SKILL.md (focus on steps 1, 7, 9 and design philosophy)
{attempts_md_section}

## 前置自检（快速扫描）

Before technical review, answer 5 design-level questions:

1. **产物身份自洽**：Does this artifact clearly know what it is? Name, description, implementation point to the same problem?
2. **产物边界诚实**：Does the claimed scope match actual capability? Any false expansion?
3. **产物数据纯度**：Is it a pure tool or a tool+data hybrid? Any hardcoded business data?
4. **职责边界自洽**：Are component responsibilities clear? Any gray zones?
5. **命名一致性**：Same concept same name across files?

If any answer is "no" → list as blocking issue (severity = conceptual).

## 确定性检查

Try running:
```bash
cd C:\\Users\\chenr\\.agents\\skills\\init-agent-docs
python assets/scripts/audit.py check --verbose
python assets/scripts/audit.py --help
```

If execution fails, note `deterministic_check: skipped (reason: ...)` and proceed to semantic review.

## Antipattern 巡查（Round ≥ 2）

Read attempts.md and check for executor antipatterns:
- **minimum_patch**: Only fixed the exact location without checking upstream?
- **solution_anchoring**: Anchored to previous reviewer's preferred approach?
- **over_compromise**: Weakened requirements to satisfy reviewer?
- **past_commitment_anchoring**: Blindly continued past Accepted approach?

Also check design-layer antipatterns:
- **false_generality**: Claims general but actually specialized (or vice versa)?
- **identity_crisis**: Name/description/implementation inconsistent?
- **data_tool_coupling**: Tool layer carries business data or environment hardcoding?
- **environment_lock-in**: Hardcoded paths, usernames, IPs?

## Your task

Identify blocking issues in the artifact. Output verdict + structured issue list.

## Output format (YAML in markdown code block)

```yaml
round: {round}
verdict: <可执行 | 阻断需修复 | 需重新设计>
deterministic_check: <pass | fail | skipped>
deterministic_check_skip_reason: <string>  # only if skipped
blocking_issues:
  - id: 1
    description: |
      <single-paragraph plain language>
    attribution: <plan_defect | executor_limit>
    severity: <conceptual | architectural | structural | implementation>
    plan_amendment_required: <true | false>
    location: <plan section reference or N/A>
suggestion_issues:
  - description: ...
antipattern_observations:
  - round_referenced: {round}
    type: <type from list>
    evidence: |
      <quote from attempts.md>
```

## 硬纪律

1. Only verdict = 可执行 allows convergence. "修齐 N 条可进入" is forbidden.
2. Every blocking issue must have binary attribution (plan_defect / executor_limit).
3. Do not be vague. "建议改成" vs "必须重写" are different signals.
4. Verify fixes actually work — don't just trust attempts.md claims.
"""

EXECUTOR_PROMPT_TEMPLATE = """You are a plan executor in an iterative convergence loop. This is Round {round}.

## Required reading (in order)

1. C:\\Users\\chenr\\.agents\\skills\\init-agent-docs\\assets\\scripts\\audit.py
2. C:\\Users\\chenr\\.agents\\skills\\init-agent-docs\\assets\\templates\\zh\\audit-checklist.md.tpl
3. C:\\Users\\chenr\\.agents\\skills\\init-agent-docs\\SKILL.md
4. C:\\Users\\chenr\\.agents\\skills\\init-agent-docs\\.converge\\active\\{slug}\\attempts.md
5. C:\\Users\\chenr\\.agents\\skills\\init-agent-docs\\.converge\\active\\{slug}\\round-{round}.md

## Your task

Fix ALL blocking issues from the reviewer's Round {round} output. Each fix must be immediately appended to attempts.md.

## Blocking issues to fix

{blocking_issues_text}

## Output format

For each issue, output:

```yaml
issue_id: <reviewer's id>
approach: <one-line fix idea>
diff: |
  <unified diff or markdown before/after>
attempt_log_entry: |
  ## Round {round} attempt · issue {id}
  - source: converge_loop
  - reviewer_backend: opencode (task tool, fresh context)
  - Issue: <exact reviewer quote>
  - Issue 归因（reviewer 判定）: <plan_defect | executor_limit>
  - plan_amendment_required: <true | false>
  - Approach: <one-line>
  - Diff: <hash | inline>
  - R{round} verdict: <留空，reviewer 验收时填>
```

## 硬纪律 — 路径依赖防护

1. **反折中**: 当前 reviewer 与 attempts.md 中"过往 Accepted"方向相反时，按当前要求做，不发明中间值。
2. **打破"过往同意"惯性**: attempts.md 中所有过往 entry 视为历史记录，不是 commitment。
3. **打破"上轮 reviewer 偏好"锚定**: 当前 reviewer 提结构性切换时，不在原方案内打补丁。
4. **修复 scope 上溯**: 每个 issue 修复时自问：上游决策是否也受影响？
5. **plan_amendment_required**: 先修 plan 本体段落，再做下游修改。
"""


def _write_round(slug, round_num, reviewer_output, orchestrator_notes=""):
    """写入 round-N.md"""
    path = CONVERGE_DIR / slug / f"round-{round_num}.md"
    content = f"""---
round: {round_num}
reviewer_backend: opencode (task tool, fresh context)
reviewer_instance_id: (see orchestrator state)
generated_at: {_timestamp()}
---

# Round {round_num} · {slug}

## Reviewer 完整输出

{reviewer_output}

## Orchestrator 处理记录

{orchestrator_notes}
"""
    path.write_text(content, encoding="utf-8")


def _write_attempts(slug, attempts_entries):
    """写入 attempts.md"""
    path = CONVERGE_DIR / slug / "attempts.md"
    content = "# Attempt Log — " + slug + "\n\n"
    for entry in attempts_entries:
        content += entry + "\n\n"
    path.write_text(content, encoding="utf-8")


def _write_state(slug, phase, round_num, notes=""):
    """写入 _orchestrator-state.md"""
    path = CONVERGE_DIR / slug / "_orchestrator-state.md"
    content = f"""---
type: orchestrator-state
object_slug: {slug}
generated_at: {_timestamp()}
last_updated_at: {_timestamp()}
---

# Orchestrator State · {slug}

## Current Position

- current_round: {round_num}
- current_phase: {phase}
- last_completed_action: {notes}
- next_pending_action: (see phase)
- progress_summary: {notes}

## Round 0 State

- contract_status: skipped
- skip_reason: Single-scope audit mechanism, no ambiguity

## Active Instance Registry

| Round | Instance ID | Role | Status |
|-------|-------------|------|--------|
| (managed by scheduler) | | | |

## Compact Recovery Notes

- {_timestamp()} · {notes}
"""
    path.write_text(content, encoding="utf-8")


def _parse_verdict(reviewer_output):
    """从 reviewer 输出中提取 verdict 和 blocking issues."""
    # Simple YAML block extraction
    try:
        # Find the YAML block
        start = reviewer_output.find("```yaml")
        end = reviewer_output.find("```", start + 7)
        if start == -1 or end == -1:
            # Try ```yml
            start = reviewer_output.find("```yml")
            end = reviewer_output.find("```", start + 6)
        if start == -1 or end == -1:
            return {"verdict": "unknown", "blocking_issues": [], "raw": reviewer_output}

        yaml_block = reviewer_output[start:end].strip()
        # Remove the ```yaml prefix
        yaml_block = yaml_block.split("\n", 1)[1] if "\n" in yaml_block else yaml_block

        # Parse key fields manually (no yaml dependency)
        verdict = "unknown"
        blocking_issues = []
        for line in yaml_block.split("\n"):
            line = line.strip()
            if line.startswith("verdict:"):
                verdict = line.split(":", 1)[1].strip()
            elif line.startswith("- id:"):
                issue_id = line.split(":", 1)[1].strip()
                blocking_issues.append({"id": issue_id})

        return {"verdict": verdict, "blocking_issues": blocking_issues, "raw": reviewer_output}
    except Exception as e:
        return {"verdict": "parse_error", "blocking_issues": [], "raw": reviewer_output, "error": str(e)}


def _get_attempts_md_path(slug):
    return str(CONVERGE_DIR / slug / "attempts.md")


def _get_round_md_path(slug, round_num):
    return str(CONVERGE_DIR / slug / f"round-{round_num}.md")


def run_converge(slug, max_rounds=5):
    """主 converge 循环."""
    print(f"[Orchestrator] Starting converge for {slug}")
    print(f"[Orchestrator] Max rounds: {max_rounds}")

    # Create converge directory
    converge_dir = CONVERGE_DIR / slug
    converge_dir.mkdir(parents=True, exist_ok=True)

    # Initialize state file
    _write_state(slug, "running", 0, "Converge loop initialized")

    # Load scheduler state
    wf_slug = "converge-audit"
    state = load_state(wf_slug, str(WORKFLOW_DIR))

    attempts_entries = []
    round_num = 0

    while round_num < max_rounds:
        round_num += 1
        print(f"\n{'='*60}")
        print(f"[Round {round_num}] Starting...")

        # --- Step 1: Dispatch reviewer from scheduler ---
        action = get_next_action(state)
        save_state(state, str(WORKFLOW_DIR))
        print(f"[Scheduler] Action: {action['action']}")

        if action["action"] == "done":
            print("[Scheduler] Loop converged (dry threshold reached)")
            break

        if action["action"] == "stop":
            print(f"[Scheduler] Stopped: {action.get('reason')}")
            break

        # --- Step 2: Build reviewer prompt ---
        attempts_section = ""
        if round_num > 1 and attempts_entries:
            attempts_content = "\n\n".join(attempts_entries)
            attempts_section = f"\n4. C:\\Users\\chenr\\.agents\\skills\\init-agent-docs\\.converge\\active\\{slug}\\attempts.md\n\n## Attempts so far\n\n{attempts_content}"

        reviewer_prompt = REVIEWER_PROMPT_TEMPLATE.format(
            round=round_num,
            attempts_md_section=attempts_section,
        )

        # --- Step 3: Spawn reviewer (via task tool — we return prompt for orchestrator to spawn) ---
        print(f"[Round {round_num}] Spawning reviewer...")
        print(f"[Round {round_num}] PROMPT_START")
        print(reviewer_prompt)
        print(f"[Round {round_num}] PROMPT_END")

        # For now, return the prompt. The orchestrator (main conversation) will
        # spawn the task and feed back the result.
        return {
            "action": "spawn_reviewer",
            "round": round_num,
            "prompt": reviewer_prompt,
            "slug": slug,
            "state_action": action,
        }

    # If we get here, we exhausted rounds without convergence
    _write_state(slug, "budget_soft_stop", round_num, f"Reached max_rounds={max_rounds}")
    save_state(state, str(WORKFLOW_DIR))
    return {"action": "budget_soft_stop", "round": round_num}


def process_reviewer_result(slug, round_num, reviewer_output):
    """处理 reviewer 输出，决定下一步."""
    wf_slug = "converge-audit"
    state = load_state(wf_slug, str(WORKFLOW_DIR))

    # Parse verdict
    parsed = _parse_verdict(reviewer_output)
    verdict = parsed["verdict"]
    blocking_count = len(parsed["blocking_issues"])

    print(f"[Round {round_num}] Verdict: {verdict}, Blocking issues: {blocking_count}")

    # Write round-N.md
    _write_round(slug, round_num, reviewer_output)

    if verdict == "可执行" or blocking_count == 0:
        # Converged!
        print(f"[Round {round_num}] CONVERGED — verdict = 可执行")

        # Apply loop feedback (dry = 0 new findings)
        apply_result(state, "_finder", "review", result=json.dumps({"verdict": verdict}))
        save_state(state, str(WORKFLOW_DIR))

        _write_state(slug, "completed", round_num, f"Converged at R{round_num}")

        return {
            "action": "converged",
            "round": round_num,
            "verdict": verdict,
        }
    else:
        # Has blocking issues — need executor
        print(f"[Round {round_num}] Blocking issues found, spawning executor...")

        # Apply result for this round's finder
        apply_result(state, "_finder", "review", result=json.dumps({
            "verdict": verdict,
            "blocking_count": blocking_count,
        }))
        save_state(state, str(WORKFLOW_DIR))

        # Build executor prompt
        blocking_text = ""
        for issue in parsed["blocking_issues"]:
            blocking_text += f"- Issue #{issue['id']}: (see round-{round_num}.md for details)\n"

        executor_prompt = EXECUTOR_PROMPT_TEMPLATE.format(
            round=round_num,
            slug=slug,
            blocking_issues_text=blocking_text,
        )

        return {
            "action": "spawn_executor",
            "round": round_num,
            "prompt": executor_prompt,
            "blocking_issues": parsed["blocking_issues"],
            "verdict": verdict,
        }


def process_executor_result(slug, round_num, executor_output, attempts_entries):
    """处理 executor 输出，准备下一轮."""
    # Append executor output to attempts
    attempts_entries.append(f"## Round {round_num}\n\n{executor_output}")

    # Write attempts.md
    _write_attempts(slug, attempts_entries)

    # Update state
    _write_state(slug, f"round_{round_num}_executor_done", round_num,
                 f"Executor completed R{round_num} fixes")

    return {
        "action": "next_round",
        "round": round_num,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default=_converge_slug())
    parser.add_argument("--action", default="start", choices=["start", "reviewer-result", "executor-result"])
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--result-file", help="File containing agent output")
    parser.add_argument("--dir", default=str(WORKFLOW_DIR))
    args = parser.parse_args()

    if args.action == "start":
        result = run_converge(args.slug)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "reviewer-result":
        if not args.result_file:
            print("--result-file required for reviewer-result", file=sys.stderr)
            sys.exit(1)
        output = Path(args.result_file).read_text(encoding="utf-8")
        result = process_reviewer_result(args.slug, args.round, output)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "executor-result":
        if not args.result_file:
            print("--result-file required for executor-result", file=sys.stderr)
            sys.exit(1)
        output = Path(args.result_file).read_text(encoding="utf-8")
        # Load existing attempts
        attempts_path = CONVERGE_DIR / args.slug / "attempts.md"
        existing = []
        if attempts_path.exists():
            existing = [attempts_path.read_text(encoding="utf-8")]
        result = process_executor_result(args.slug, args.round, output, existing)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
