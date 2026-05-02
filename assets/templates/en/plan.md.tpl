# [Plan Title]

> Created: [date]
> Status: in progress
> Mode: direct | staged | collaborative
> Coordinator: [@name] <!-- "none" if absent. The coordinator assigns tasks, drives status transitions, reconciles reviews, handles handoffs/conflicts, re-breaks down unreasonable task assignments (e.g., when Owner reports granularity/dependency/scheme issues), and closes the plan when all stages complete. -->

## Task Assignment

| Task / Stage | Owner | Status | Reviewer | Notes |
|--------------|-------|--------|----------|-------|
| Stage 1: ... | @agent-a | queue | @reviewer | <!-- required in collaborative mode; single-agent can collapse to one row --> |
| Stage 2: ... | @agent-b | blocked | @reviewer | <!-- example: blocked, awaiting coordinator re-breakdown --> |

## Goal

<!-- One paragraph: what this plan is trying to achieve and why. -->

## Stages

<!--
Stage breakdown principles:
1. Each stage should fit in one context window (rule of thumb: ~5-10 files).
2. After each stage, the system must be in a working state (no "stage 1 removes old, stage 2 adds new" splits).
3. Minimize inter-stage dependencies, but make execution order explicit.
4. Every stage needs a verifiable completion criterion so a fresh-context agent can tell if it's done.
5. If run in parallel, stages must be independently claimable with clear owner / reviewer / handoff boundaries.
6. Status transitions must be traceable: who can claim, who reviews, how to bounce a failed review.
-->

<!--
Status transitions:
- `queue`: not yet claimed; coordinator or executor can take it.
- `claimed`: claimed but not yet actively in progress — prevents double-pickup.
- `in_progress`: actively being implemented.
- `review`: implementation done, waiting for a reviewer or fresh-context review.
- `blocked`: task is blocked and requires coordinator intervention. Use cases: Owner discovers unreasonable granularity/dependencies/approach, or encounters unsolvable dependency issues. Actions: (1) Change status to `blocked`, (2) Write reason in Notes column, (3) Document details and suggestions in "Decision Log", (4) Notify coordinator. Coordinator should then re-break down the task or resolve dependencies, then change status back to `queue` for reassignment.
- `✅ completed`: reviewed and confirmed ready to hand off / merge.
- In single-agent mode you can go straight from `queue` to `in_progress`.
- If review fails, bounce back to `in_progress` and record the reason in "Completion Notes" or "Decision Log".
- If Owner discovers that task granularity, dependencies, or technical approach are unreasonable, use the `blocked` status to report to coordinator, rather than silently sub-contracting or forcing execution.
-->

### Stage 1: [Title]
- **Goal**: <!-- what this stage delivers -->
- **Files touched**: <!-- expected file list, to help orient a new-context agent -->
- **Completion criterion**: <!-- how you'll know it's done, e.g. "endpoint X returns Y", "tests pass" -->
- **Owner**: <!-- current owner; single-agent mode just names the executor -->
- **Reviewer**: <!-- person or role doing review; "TBD" is fine -->
- **Status**: queue | claimed | in_progress | review | blocked | ✅ completed
- **Completion notes**: <!-- filled in on completion: what actually changed, any deviation from plan, any leftover issues -->
- **Handoff summary**: <!-- filled in on completion: what the next-stage agent needs to know — files touched, current system state, unexpected findings, what to read first -->

### Stage 2: [Title]
- **Goal**: ...
- **Files touched**: ...
- **Completion criterion**: ...
- **Preconditions**: <!-- prior stages this depends on -->
- **Owner**: ...
- **Reviewer**: ...
- **Status**: queue
- **Completion notes**:
- **Handoff summary**:

### Stage 3: [Title]
...

## Decision Log

<!-- Key decisions made during execution: what was chosen and why.
Crucial for later stages run by fresh-context agents who don't know the earlier reasoning.
Example:
- 2026-03-30: Planned JWT; switched to session cookies because mobile doesn't handle Bearer refresh.
-->

## Risks & Leftovers

<!-- Known risks, technical debt, unresolved issues -->
