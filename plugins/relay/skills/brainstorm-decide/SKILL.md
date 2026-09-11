---
name: brainstorm-decide
description: Use to alternate a warm brainstormer with an isolated decider until a typed verdict routes the loop to exit — each round re-dispatches the brainstormer with WARM session-grounding to surface the next option, dispatches a fresh decider that returns a typed verdict, and branches on the verdict's route value to continue or exit.
user-invocable: false
---

# brainstorm-decide

brainstorm-decide alternates a warm brainstormer with an isolated decider whose typed verdict
routes continue or exit.

## Steps

This skill realizes the `router-loop` L1 shape. Drive it as follows:

1. **Keep the brainstormer WARM.** The brainstormer is a single long-lived session that
   accumulates context across rounds. Do not re-dispatch it cold each pass — use `session-grounding`
   posture WARM to resume the in-flight session with its prior continuation token (the §6.4.1
   acpx-leaf interface) so it surfaces the next option while preserving its prior reasoning.
   Only the acpx leg can resume a session mid-turn (§6.1), so `acpx-leg-required: true` for
   this skill.
2. **Dispatch an ISOLATED decider.** Each round, `delegate` a fresh decider that does not share
   the brainstormer's session — its `session-grounding` is ISOLATED: the brainstormer's latest
   option plus the original objective, nothing more. The decider returns a `typed-output`
   `{ verdict: { value: "<route>" } }`.
3. **Classify the route.** `classify` the decider's `verdict.value` against this skill's own
   closed route enum (§6.3 — each L2 instantiation owns its set): `continue | exit`. Reject any
   value outside that enum rather than guessing a route.
4. **Branch on the verdict.** `branch` on `verdict.value`: when it is `continue`, `loop-until`
   re-enters step 1 and re-dispatches the warm brainstormer for the next option; when it is
   `exit`, leave the loop and surface the decided option.

Calm imperatives only. Describe the target form; cite only tokens from the vocabulary below.

## Vocabulary

```relay-vocab
l1-shape: router-loop
l0-deps: loop-until, delegate, session-grounding, branch, typed-output, classify
acpx-leg-required: true
```
