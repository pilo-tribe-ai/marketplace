---
name: improve-loop
description: Use to re-dispatch one worker role until a critic's verdict reads clean or the iteration cap is spent — each pass runs the worker body, classifies the critic verdict against the closed three-label set (`clean`, `findings`, `no-answer`), and branches forward to exit, back to iterate, or out to an explicit unverified result when the cap or shared budget is exhausted.
user-invocable: false
---

# improve-loop

improve-loop re-dispatches one worker until a critic verdict reads `clean`, or until the cap
is spent — at which point it exits with the findings still open or with an explicitly
unverified result, never with a silent pass.

## Steps

This skill realizes the `loop-until-clean` L1 shape. Drive it as follows:

1. **Define the loop body.** The body is one worker role — the actor that produces or revises
   the artifact under improvement. Each iteration re-dispatches this same body.
2. **Run one pass.** `loop-until` re-runs the worker body, then `classify` the resulting
   critic verdict against the closed three-label set:

   - `clean` — the critic answered and found nothing.
   - `findings` — the critic answered and carries findings.
   - `no-answer` — the critic produced no verdict at all (null, empty, or unparseable).

   A missing verdict is its own label. Never fold it into `clean`.
3. **Branch on the label.** Route each of the three separately:

   - `clean` — `branch` forward. A clean verdict exits the loop.
   - `findings` — `branch` back to re-dispatch the worker body for another pass.
   - `no-answer` — a dispatch failure, never a pass. Re-dispatch the critic once within the
     `cap`, and when that re-dispatch also returns `no-answer`, force exit and surface an
     explicit unverified result. The artifact was never judged, so it may not be reported
     as clean.
4. **Honor the bound.** Each iteration spends from the `cap` (§4.3) — a hard integer ceiling
   on attempts — and from any shared `budget` pooled across the loop. When either is spent
   before a clean verdict, force exit and name which exit it is: findings still open when the
   last label was `findings`, or an explicitly unverified result when the last label was
   `no-answer`. Report neither as clean.

Calm imperatives only. Describe the target form; the worker does the work.

## Vocabulary

```relay-vocab
l1-shape: loop-until-clean
l0-deps: loop-until, classify, cap, budget, branch
acpx-leg-required: false
```
