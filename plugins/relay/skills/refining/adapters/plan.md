# Adapter: plan

Identical to `adapters/spec.md` with `plan_path` as the subject and task-level diff granularity.
The caller binds `plan_path` from the spine's `PLAN_PATH` token before this adapter runs.

## Interface

- `load()` — read the plan at `plan_path`; a missing file returns `SUBJECT_MISSING`.
- `snapshot(subject)` — the plan's pre-text before any fixer runs this round.
- `diff(snapshot, current)` — task/section-level diff for the round report.
- `post_fix(action)` — `re-read` the file from disk after `plan-fixer` patches it.
- `persist(round, findings, marker)` — sidecar findings file + inline `[inferred]` tags + the
  `Refinement: ... round N` marker in `## Refinement Status`.
- `recover()` — read that marker and return the last completed round.
