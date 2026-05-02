# AI Collaboration Guide

> This file is auto-loaded by AI frameworks and always resident in context, so keep it lean.
> Put behavior rules and information pointers here only — not facts that can be derived from code or other docs.

## Hardlink Declaration

`AGENTS.md`, `CLAUDE.md`, `GEMINI.md` are hardlinks to the same file — read any one.
Check consistency before and after edits: `python scripts/agent_links.py check --verbose`.
Rebuild only when the hardlink group is broken: `python scripts/agent_links.py repair`. If `CLAUDE.md` / `GEMINI.md` content differs from `AGENTS.md`, review first, then use `python scripts/agent_links.py repair --force`.

## Information Map

- Doc index: [STRUCTURE.md](STRUCTURE.md)
- System design & decisions: [docs/overview.md](docs/overview.md)
- API conventions: [docs/api.md](docs/api.md)
- Deployment & environment: [docs/deployment.md](docs/deployment.md)
- Known pitfalls: [docs/pitfalls.md](docs/pitfalls.md)
- Plans for complex tasks: [docs/plans/](docs/plans/)
- Current task state (single-owner handoff / global entry): [docs/CURRENT.md](docs/CURRENT.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)

<!-- Trim based on Step 0: drop api.md line if no API, drop deployment.md if no deployment. -->

## Behavior Rules

### Hard constraints (never violate)
- **No secrets in repo**: API keys live in env files (e.g. `.env`); never hard-coded.
- **Don't touch build artifacts**: <!-- list build-artifact paths, e.g. dist/, build/, data/, node_modules/ --> are generated; do not modify unless the task explicitly requires it.
- **Don't bypass hooks**: when `.githooks/pre-commit` is enabled, fix lint failures before committing — never use `--no-verify`.
- **Must run end-of-task checklist**: every task ends with the checklist at the bottom. Do not skip. Do not report completion before running it.
<!-- Add project-specific hard constraints, e.g.:
- **Front-end/back-end sync**: after changing backend schema, update frontend type defs.
- **No prod schema edits**: schema changes must go through migrations.
-->

### Default preferences (deviate with good reason)
- **Read before writing**: read files before editing; understand existing logic first.
- **Follow existing style**: match the codebase's style; don't introduce new patterns.
- **Occam**: do not add entities without necessity; before adding files, fields, scripts, rules, or workflow steps, name the concrete problem they solve.
- **Bitter Lesson**: general methods beat hard-coded priors; prefer model capability, semantic search, structured tools, and default workflows over task enumerations, keyword rules, and premature classifications.
- **Match mode to complexity**: small tasks use direct mode; complex tasks need a plan file. When multiple agents work in parallel, put the source-of-truth in the plan file, not a global CURRENT.md.
- **Per-task mode selection**: the project has a default collaboration style, but pick the mode for each task based on complexity, risk, and whether it's parallel.
- **Prefer fresh reviewer perspective for verification**: for high-risk changes, get a new-context or reviewer review — "executor self-check" is not "verified".

## Testing Requirements

<!-- Fill based on the project. Examples:
- Has a test suite: backend `pytest`, frontend `npm test` — must pass after changes.
- No automated tests: backend changes at minimum verify `GET /health` and affected endpoints; frontend changes run `npm run lint` and a manual smoke test.
-->

## Commit Conventions

Use Conventional Commits: `feat:` / `fix:` / `chore:` etc. PRs must describe scope and migration steps.

**Commit early and often**: stage source files and commit after each functional milestone; exclude binary build artifacts.

## Documentation Maintenance

**Core principle: only record what you cannot read from code.** Directory structure, module responsibilities, tech stack, function signatures — all derivable from code — do not go into docs. Docs record design rationale, collaboration constraints, and information not derivable from code.

1. **No duplication**: each fact lives in exactly one place. Logic shown in a flowchart isn't repeated in a responsibility table.
2. **No implementation details**: CSS breakpoints, field lists, SQL DDL — one line + a pointer to the source file.
3. **Merge alike**: one responsibility table covers front-end and back-end, not two.
4. **Keep supplemental text terse**: notes below a flowchart describe what the chart doesn't, not the steps themselves.
5. **Don't duplicate what code/git can tell you**: file paths, signatures, defaults change with code — readers should look at the source; docs only explain "why".

**`docs/` boundaries**

6. New design decisions go in [docs/overview.md](docs/overview.md); interface changes in [docs/api.md](docs/api.md); deployment/env constraints in [docs/deployment.md](docs/deployment.md); pitfalls in [docs/pitfalls.md](docs/pitfalls.md).
7. Update the relevant `docs/*.md` first, then write [CHANGELOG.md](CHANGELOG.md). Changelog records summaries, not full content.
8. When a single doc approaches 300 lines, split it by topic and index the split in [STRUCTURE.md](STRUCTURE.md); don't keep piling onto one file.
9. For cross-module complex tasks, drop a lightweight plan in `docs/plans/active/` before starting; move to `docs/plans/completed/` when done.

**CHANGELOG rules**

10. Date sections in reverse order (newest first). Multiple changes on the same day share a date section, separated by `###` subheadings.
11. Before writing to [CHANGELOG.md](CHANGELOG.md), **don't read the whole file**. Use `python scripts/changelog.py titles --limit 5` for the title tree, `python scripts/changelog.py show --date YYYY-MM-DD` or `--match keyword` for local reads, and `python scripts/changelog.py add --title "..." --body "..."` to append entries.
12. Current task state belongs in [docs/CURRENT.md](docs/CURRENT.md), not in CHANGELOG.
13. Record only "what changed, why, migration impact". No code snippets; no repeating `docs/` content.

## End-of-Task Checklist (hard constraint)

Docs are the only cross-session memory. If code changes and docs don't follow, the next session will act on stale info and cause chained errors. **Every task ends by walking this checklist before reporting back.**

- [ ] **Verify**: does the affected feature still work? Frontend: no white screen / no console errors. Backend: service starts cleanly.
- [ ] **Reviewer perspective**: for high-risk / cross-module tasks, did a fresh-context reviewer check it? If not, call it out explicitly in the reply or plan.
- [ ] **Architecture docs (docs/)**: any architecture change (new module, new interface, flow change, new config, port/env shift)? Update the relevant `docs/` file per the maintenance principles above.
- [ ] **CHANGELOG.md**: worth recording? If so, use `python scripts/changelog.py add ...` to append to today's date section; use only `titles/show` for local reads.
- [ ] **Hardlinks**: if this file was edited, run `python scripts/agent_links.py check --verbose`; repair with `python scripts/agent_links.py repair` only when broken.
- [ ] **Skip conditions**: pure formatting, comment tweaks, or changes already logged in this session can skip doc updates — but the verify step is never skipped.
