# CHANGELOG

## [Today's date, e.g. 2026-04-17]

### Initialize documentation system

- Created agent-first doc structure: AGENTS.md (with hardlinks) + STRUCTURE.md + docs/ hierarchy
- Installed scripts/changelog.py and scripts/agent_links.py to script changelog and hardlink maintenance
- Design philosophy: the repo is the source of truth; record only what code cannot tell you; plans are cross-context handoff protocols

<!--
Notes:
- Date sections in reverse chronological order. Multiple same-day changes share a date section, separated by ### subheadings.
- Before writing, don't read the whole file — use `python scripts/changelog.py titles/show/add` for title trees, local reads, and appends.
- Live work state goes in docs/CURRENT.md; CHANGELOG records history only.
-->
