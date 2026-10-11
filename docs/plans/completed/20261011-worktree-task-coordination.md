# Worktree task coordination

## Scope

Extend the existing optional Git worktree helper with cooperative task identity, intent, peer review, and admission. Keep its four Git actions callable, its canonical fast-forward hook optional, and the installed runtime independent of a particular Agent host. This task changes only this skill source worktree; it does not install the skill into a host, modify a real knowledge base, contact a server, or change remote state.

## Baseline and isolation

- Base commit: `f357edcae7cd9b164732386e886bb4dc167bb079`.
- Bootstrap helper created a separate `task/20261011-203634-48bf76e0` branch and sibling worktree. The source main worktree remains untouched.
- The existing four-action helper has no persistent task identity beyond Git, no owner/generation, and a temporary-directory PID/TTL integration lock. Its old callers and tests must remain usable.

## Implementation

1. Add a small Git-common-dir registry with atomic task records and a no-timeout mutation/integration lock. Preserve half-created state for inspection; do not silently claim stale owners or locks.
2. Give cooperative tasks one display name input and derive a stable ID, branch, and worktree path. Provide register/resume/list/close around explicit owner and generation. Legacy four-action tasks remain visible as unknown, never silently admitted.
3. Add free-text goal, non-goal, and scope; optional literal repository-relative path hints and committed-SHA dependencies. Review all open peers; mechanically flag path overlap, but leave semantic decisions to Agents. For affected pairs, require the same bounded protocol text from both current revisions, or a scoped recorded override. Bind admission to a review digest and current pair conclusions; unrelated peer changes do not freeze writing.
4. Keep the new gate cooperative: explicit `check --write` checks admission but no new mandatory hook or Git config change. Existing optional fast-forward hook remains separate.
5. Update SKILL.md, workflow reference, AGENTS template, and README to the final contract. State that worktrees isolate uncommitted files/index only, not integration, semantic, or external-state conflicts.

## Verification and review

- Existing four-action and hook regression tests.
- New isolated fixture tests for identity/resume, concurrent entrance, stale revisions, pair conclusion mismatch, unrelated peers, legacy unknown/override, non-overlap, immutable dependencies, lock recovery, and failure preservation.
- Forward-test a fresh Git fixture using the public CLI, not only implementation helpers.
- Run repository checks and diff hygiene, then hand off uncommitted work for at least three independent reviews before any commit or main integration.

## Known separate issue

Windows Git worktree removal can fail on ReadOnly directories; its deletion mechanism has been reproduced elsewhere, but the actor setting ReadOnly remains unknown. This task does not claim source attribution or alter host permissions.

## Completion evidence

- Source worktree implementation and skill guidance are complete and awaiting main-branch integration; no push, host installation, real knowledge-base mutation, or deployment was performed.
- Focused source regression: `python -B -m unittest tests.test_worktree_task_asset tests.test_worktree_coordination tests.test_skill_guidance -q` passed 58/58. The new tests include public CLI forward flow, two-peer scope/protocol admission, unknown legacy override, immutable SHA dependency validation, read-only cross-entry consistency, ignored-file cleanup refusal, and retained audit branch behavior.
- Skill validator: `python -X utf8 -B <skill-creator>/scripts/quick_validate.py <this-skill>` passed. Plain Windows default-encoding invocation could not decode Chinese `SKILL.md` under GBK; the explicit UTF-8 validation mode passed. `git diff --check` passed.
- Three independent reviews accepted the source implementation and guidance: runtime/concurrency review, dependency-and-legacy review, and cross-skill forward behavior review. A separate init-kb-harness task owns its bridge and did not copy this runtime.
- Known exception outside this source worktree: cleanup of temporary tool and synthetic fixture artifacts in the separate local ReadOnly-source investigation was blocked by tool policy. This task did not remove or inspect those artifacts and does not claim that investigation closed. The ReadOnly setter remains unknown; see the separate CCWM active plan.
