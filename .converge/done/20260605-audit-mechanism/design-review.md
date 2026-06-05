---
type: design-review
object_slug: 20260605-audit-mechanism
generated_at: 2026-06-06T00:05:00Z
reviewer_backend: opencode (task tool, fresh context)
reviewer_instance_id: ses_16773dcb7ffernrjckK7CKkbWf
---

# Design Review · 20260605-audit-mechanism

> Single-round advisory review. Findings do NOT block convergence. Report to user for decision.

```yaml
design_review:
  dimensions:
    - name: consistency
      status: concerns_found
      findings:
        - finding: |
            DOC_FILES in audit.py (line 38-43) covers only 4 files: AGENTS.md,
            STRUCTURE.md, docs/overview.md, docs/deployment.md. But the skill
            creates 6+ doc files including docs/audit-checklist.md, docs/CURRENT.md,
            docs/pitfalls.md, docs/api.md. Dead links in those files are invisible
            to the mechanical checker.
          location: "audit.py:38-43 (DOC_FILES list)"
          impact: |
            The audit mechanism has a false-negative blind spot. A broken link
            in docs/CURRENT.md or docs/audit-checklist.md passes mechanical
            checking silently.

        - finding: |
            audit-checklist.md.tpl references `python scripts/changelog.py recent
            --days 30` (line 35), but SKILL.md's script description only mentions
            `titles`, `show`, and `add` subcommands. If `recent` does not exist,
            the template contains a dead instruction.
          location: "audit-checklist.md.tpl:35"
          impact: |
            Agent following the audit checklist will hit a command-not-found error
            at step 4, breaking the audit flow.

        - finding: |
            SKILL.md step 9 says "更新 STRUCTURE.md 索引表" to add audit-checklist.
            But step 2 for small projects says "不生成 STRUCTURE.md". Step 9 says
            "所有规模都要创建" for audit-checklist, but the STRUCTURE.md update
            instruction has no small-project branch.
          location: "SKILL.md:632-636 (step 9, sub-step 2)"
          impact: |
            Agent executing for a small project will try to update a non-existent
            STRUCTURE.md.

    - name: completeness
      status: concerns_found
      findings:
        - finding: |
            The audit checklist (step 4) references `changelog.py recent --days 30`
            without fallback. If the project has no changelog.py or uses a different
            script, the template offers no alternative path.
          location: "audit-checklist.md.tpl:35"
          impact: Template assumes specific script capability exists.

        - finding: |
            No explicit "what to do when audit.py itself is outdated or missing" path.
          location: "audit-checklist.md.tpl:8"
          impact: Minor — agent can re-copy from skill assets, but template doesn't mention this.

    - name: maintainability
      status: clean
      findings:
        - finding: |
            Well-documented across SKILL.md (design philosophy #6, step 7, step 9),
            README.md, and the checklist template's own header comment.
          location: "SKILL.md:115-117, 576-596, 622-653"
          impact: none
        - finding: |
            DRIFT_PATTERNS extensibility explicitly documented in checklist template
            (line 10) with pointer to design philosophy #8.
          location: "audit-checklist.md.tpl:10, audit.py:61-91"
          impact: none

    - name: boundary_clarity
      status: clean
      findings:
        - finding: |
            Clean separation: audit.py mechanical/read-only, audit-checklist.md.tpl
            agent judgment/裁决. No gray zone.
          location: "audit.py:7, audit-checklist.md.tpl:1-4"
          impact: none
        - finding: |
            Subcommands (dead-links, structure, drift) provide granular access
            alongside aggregate `check`. Correct diagnostic workflow.
          location: "audit.py:505-531"
          impact: none

    - name: residue_and_redundancy
      status: concerns_found
      findings:
        - finding: |
            _format_text glyph width inconsistent: "OK"/"MISS" 6-char padded,
            "BROKEN"/"ERROR" 8-char padded. Misaligned output.
          location: "audit.py:391-403, 447-449"
          impact: Cosmetic but undermines credibility.

        - finding: |
            __pycache__/ exists under assets/scripts/. May be copied to target project.
          location: "assets/scripts/__pycache__/"
          impact: Low — Python regenerates .pyc, but stale bytecode on different Python version could cause issues.

    - name: portability
      status: clean
      findings:
        - finding: |
            Handles cross-platform well: UTF-8 encoding, Path.resolve(), forward-slash
            normalization, sys.executable for subprocess.
          location: "audit.py:544-548, 235, 361"
          impact: none

    - name: scalability
      status: concerns_found
      findings:
        - finding: |
            DRIFT_PATTERNS fixed dictionary of 24 tech stacks. Works for common stacks,
            doesn't scale to niche technologies. Each target project ends up with
            divergent fork.
          location: "audit.py:61-91"
          impact: Mechanism works well initially but degrades over time.

        - finding: |
            DOC_FILES fixed list. As project docs grow, dead-link checker doesn't
            automatically cover new files.
          location: "audit.py:38-43"
          impact: Same pattern — works for initial set, doesn't grow with project.

  highlights:
    - finding: |
        DOC_FILES hardcodes only 4 of 6+ doc files created by the skill. Dead links
        in docs/audit-checklist.md, docs/CURRENT.md, docs/pitfalls.md, and docs/api.md
        pass the mechanical check silently.
      why_it_matters: |
        The audit is a trust mechanism. False negatives erode trust. If a file the
        agent created isn't covered by the checker the agent also runs, the agent
        receives contradictory signals.
      suggested_direction: |
        Replace static DOC_FILES with dynamic discovery (glob docs/**/*.md plus
        root files), or at minimum add all files that step 2 creates.

    - finding: |
        audit-checklist.md.tpl references `changelog.py recent --days 30` — a
        subcommand that may not exist. SKILL.md only documents `titles`, `show`,
        `add`.
      why_it_matters: |
        Agent following the checklist hits command-not-found at step 4, breaking
        the audit flow. This is a real bug, not a design preference.
      suggested_direction: |
        Either add `recent` subcommand to changelog.py, or change the template
        to use confirmed subcommands (e.g. `changelog.py titles --limit 0` to
        get recent entries, or `git log --oneline --since="30 days ago"`).
```

## 用户决策记录

- **Highlight 1 (DOC_FILES)**: 已修复。`DOC_FILES` 改为 `_discover_doc_files()` 动态发现 `docs/**/*.md`（排除 `docs/plans/`）。Reviewer 验证通过。
- **Highlight 2 (changelog.py recent)**: 已修复。`recent` 子命令实际存在但未文档化。SKILL.md 3 处 + CHANGELOG.md.tpl 1 处全部补为 `titles/show/add/recent`。初修遗漏 CHANGELOG.md.tpl:7，补修后全仓扫描零遗漏。Reviewer 验证通过。
