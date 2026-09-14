---
status: accepted
date: 2026-07-24
---

# Select model tiers by failure mode, not by task difficulty

Each role's tier answers one question: *if this leaf returns something plausible and
wrong, what catches it?* Roles whose output is verified downstream sit at `sonnet`;
critics whose miss mode is a false CLEAN sit at `opus`; mechanical, script-backed
roles sit at `haiku`; and roles whose wrong answer nothing catches carry `inherit`,
which omits `opts.model` so the node tracks the session model.

## Considered options

The intuitive axis is task size — big job, big model. It was rejected because it
optimises the wrong thing. A "small" job whose wrong answer is silently accepted
downstream is far more expensive than a "large" job that tests will reject in the
next step, and sizing by difficulty systematically under-resources exactly the roles
that most need capability.

Pinning the frontier model by name was also rejected: the name changes every release
and the pin goes stale silently. `inherit` expresses "track whatever the session is
running" and stays correct, which is why launching a session on a stronger model is
the lever that buys those roles more capability.

## Consequences

`effort` remains an independent axis and still applies to an `inherit` row, so a role
can track the session model while carrying a pinned reasoning budget.

Simulator roles mirror the *model* of whichever role acts on their artifact next —
`spec-simulator` → `plan-writer`, `plan-simulator` → `implementer` — so a simulation
runs at the tier whose risk it is predicting. This is why two otherwise similar
simulators sit at different rungs.

4.46.0 applied the rule to two named groups instead of role by role. A role may carry
a `category` — `fixes` or `verification` — and every role of one category takes one
model: `fixes` is `sonnet`, because a critic re-reads the result of the fix;
`verification` is `opus`, because a critic is re-read by nobody. Three roles moved to
reach it, and each move follows the rule rather than an exception to it:
`fix-planner` down to `sonnet`, `doc-reference-reviewer` up to `opus`, and the four
`ui-*-evaluator` roles up to `opus`.

Grouping is what makes the two flags possible. `--fixes-model` and
`--verification-model` move a whole group in one argument, so a run can trade cost
against confidence without editing the bindings file. The flag enum is narrower than
the ladder — `sonnet`, `opus`, `fable`. `haiku` is out because neither group holds a
mechanical role. `inherit` is out because it is a per-role property, and a flag that
set it would erase the property rather than choose a model. `fable` is in, although
no static pin names it: the staleness argument above is about a pin that lives in the
repository, and it does not reach a per-run choice a person makes and can undo.

Tiers are ON by default as of 4.14.0; `"in_session_tiers": false` in
`.claude/relay.json` opts out. `scripts/resolve-tier.sh` is the single resolution
site and command bodies transcribe its output rather than deriving the table by hand,
because five hand-maintained copies had already drifted. A test asserts every rung
stays in use: the ladder silently collapsed to sonnet-and-opus once before, which
made the whole mechanism a no-op while still looking configured.
