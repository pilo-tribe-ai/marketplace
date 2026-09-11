---
name: parallel-gather
description: Use to fan out to N independent workers that run concurrently and merge their typed outputs by key — each worker is dispatched in parallel, the loop syncs on all completions, then a join-by-key merge folds the typed outputs into one aggregated result.
user-invocable: false
---

# parallel-gather

parallel-gather fans out to N independent workers and merges their typed outputs.

## Steps

This skill realizes the `fan-out-aggregate` L1 shape. Drive it as follows:

1. **Fan out the workers.** `for-each` independent worker, `delegate` it to run `parallel` with
   the others — each worker is self-contained and shares no state with its siblings, so they may
   run concurrently (§4.3). Reject any worker that depends on a sibling's result: such a
   dependency means the units are not independent and belong in a pipeline, not a fan-out.
2. **Each worker returns a typed output.** Every worker produces a `typed-output` keyed for the
   merge — the key identifies which slice of the aggregate this worker owns, and the value is its
   typed result. No worker writes outside its own key.
3. **Sync on all completions.** Do not aggregate early. Wait until every fanned-out worker has
   completed and surfaced its `typed-output`; the merge runs once, after the full set is in.
4. **Join by key.** `join-by-key` merges the collected typed outputs into one aggregated result,
   folding each worker's keyed slice into its place. The merged result is the skill's output.

Calm imperatives only. Describe the target form; the workers do the work.

## Vocabulary

```relay-vocab
l1-shape: fan-out-aggregate
l0-deps: for-each, parallel, delegate, join-by-key, typed-output
acpx-leg-required: false
```
