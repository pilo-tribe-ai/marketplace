---
status: accepted
date: 2026-07-27
---

# Fail to indeterminate, never to a pass — and make the gate always-on

Any check that cannot establish its own evidence reports `INDETERMINATE` or
`DEGRADED`, never `CLEAN`. The run-completeness gate runs on every L3 command with no
opt-out.

## Context

Two `/relay:implement` runs lost half their dispatch nodes and reported success:
`wf_f13a44bd-742` lost 2 of 3 nodes and still returned top-level
`status: "completed"` with every node reading `state: "done"`. Diagnosis covered 38
workflow runs and 426 agent nodes across 5 repositories.

The decisive detail is that the earlier mitigation *caused* the silence. A `safeAgent`
try/catch had been added to survive a prose output contract's misses; by catching a
schema failure and returning `null`, it converted a hard harness error into a
plausible success. A soft mitigation wrapped around a hard failure is how the failure
becomes invisible.

## Considered options

Making the gate opt-in was rejected on the grounds that an opt-in check is enabled by
someone who already suspects a problem, and this failure class produces no symptom to
suspect — the run says it completed. A soft check was rejected because softness is
precisely the defect being fixed.

Two cheaper predicates were tried and discarded, and are recorded in the script so
they are not re-proposed: `lastToolName != "StructuredOutput"` produced nine false
positives, and `state != "done"` was `"done"` on 426 of 426 nodes *including all five
dead ones* — zero signal.

## Consequences

Runs that previously reported success can now report `INCOMPLETE` or `INDETERMINATE`.
That is the intended behavior change, not a regression.

The cost is two file reads and a set difference — no model tokens — against the
~150K tokens and 350 seconds the dead nodes burned in a single observed run.

Because the gate reads private harness artifacts (`wf_*.json` shape, journal keys), an
upstream format change degrades it to `INDETERMINATE` on every run rather than
silently passing. That is the correct failure direction and an accepted fragility.
