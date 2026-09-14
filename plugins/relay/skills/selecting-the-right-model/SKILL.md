---
name: selecting-the-right-model
description: Reference map of how relay picks a model and effort for each leaf role — the tier ladders (POLICY), where the per-role tiers live (INVENTORY), and the two scripts that resolve them for in-session and acpx dispatch (RESOLUTION).
user-invocable: false
---

# selecting-the-right-model

This skill is the **reference map** for model selection, not a runtime step. Nothing invokes
it; two scripts do the actual resolving, and this file explains what they decide and why.
Read it when changing a tier, adding a role, or working out why a leaf ran on the model it did.

Relay never picks a model per *task instance*. It picks one per **role**, ahead of time, and
the tier lives beside the role in `bindings/presets.yaml`. Dispatch reads that pin; it does
not re-reason about it. Three layers:

## Layer 1 — POLICY (which tier a role belongs in)

Tiers are chosen by **failure mode**, not by task size. The question is never "is this job
hard?" but "if this leaf returns something plausible and wrong, what catches it?"

### In-session ladder (the flat `model:` field)

| Tier | When | Roles today |
|---|---|---|
| `inherit` | **Silent-failure** roles: a wrong-but-plausible output is accepted downstream and nothing catches it. Omits `opts.model` so the node runs on the session model — launching the session on a stronger model is how you buy these roles more capability. | `plan-writer`, `spec-simulator`, `panel-moderator` |
| `opus` | Bounded top-tier reasoning. Critics whose miss mode is a false CLEAN. Every role of the `verification` category sits here. | 7 roles: `spec-reviewer`, `code-reviewer`, `doc-reference-reviewer`, and the four `ui-*-evaluator` roles |
| `sonnet` | Standard execution work that **is** verified downstream — implementers checked by tests plus code-reviewer, generators by evaluators, and every role of the `fixes` category, whose output a critic re-reads. | 12 roles incl. `implementer`, `test-writer`, `fix-planner`, `fix-coder`, `ui-generator` |
| `haiku` | Mechanical roles with a narrow decision surface. | `server-runner`, `navigator` |

`effort` (`low | medium | high | xhigh`) is an **independent axis** — it applies on an
`inherit` row too. A never-downshift role inherits the model but keeps its pinned effort.

**Simulator mirroring.** A simulator takes the **model** of the role that acts on its artifact
next (`spec-simulator` → `plan-writer`; `plan-simulator` → `implementer`), so the simulation
reflects the execution tier whose risk it is predicting. This is why `plan-simulator` sits at
`sonnet` while `spec-simulator` sits at `inherit`. Effort may sit one notch below the mirrored
role's (`spec-simulator` high vs `plan-writer` xhigh — a one-shot simulation, not authoring);
`plan-simulator` matches `implementer` on both axes.

### acpx ladders (the `modalities.*` blocks)

Cross-process workers have no session to inherit from, so `inherit` is meaningless there and
each engine carries its own pin:

| Engine | Ladder |
|---|---|
| `claude` | `opus` at every role; only `effort` varies. |
| `codex` | `gpt-5.6-sol` (demanding planning/architecture) · `gpt-5.6-terra` (everything else — code-writing against a vetted plan, and everyday judgment/review). Effort is baked into the id as `${model}/${effort}`. |
| `opencode` | `opencode-go/kimi-k2.7-code` (sol slot) · `opencode-go/kimi-k2.6` (terra slot). No effort key — open-weight models reject `set effort` with ACP -32602. |

### The two category overrides

Two groups of roles carry a `category:` field, and one flag addresses each group:

| category | roles | default | flag |
|---|---|---|---|
| `fixes` | `spec-fixer`, `plan-fixer`, `fix-planner`, `fix-coder` | `sonnet` | `--fixes-model` |
| `verification` | `spec-reviewer`, `code-reviewer`, `doc-reference-reviewer`, `ui-visual-evaluator`, `ui-ux-evaluator`, `ui-accessibility-evaluator`, `ui-code-evaluator` | `opus` | `--verification-model` |

The two categories carry the same rule the ladder above states, in one word each: a fix is
re-read by a critic, so it runs one rung below; a critic is re-read by nobody, so it runs at
the top. The flags let a run move both groups without editing the bindings file. Each flag
takes exactly one of `sonnet`, `opus`, `fable`, and replaces the model of every role of its
category. It changes no other role, and it changes no `effort`.

That enum is deliberately narrower than the per-role ladder. `haiku` is absent because
neither category holds a mechanical role: a critic or a fixer on `haiku` is a downgrade
nobody asks for on purpose. `inherit` is absent because it is a per-role property — "this
role must track the session model" — so a flag that set it would erase the property instead
of choosing a model. `fable` is present although no role pins it: the staleness argument that
keeps a frontier name out of the static pins does not reach a per-run choice a person makes
and can undo.

`/relay:implement`, `/relay:refine`, `/relay:execute` and `/relay:drive` accept both flags.
`.claude/relay.json` accepts the same two values as the keys `fixes_model` and
`verification_model`. Resolution is the layering every other axis uses — flag, then pin, then
the per-role default beside the role. `resolve-tier.sh --all` names both values and their
source in its header, so a flag that reached no row is visible.

Two commands take neither flag, on purpose. `/relay:diagnose` has no Step 0, so it reads the
`.claude/relay.json` pins only. `/relay:verify` dispatches no role: its nodes are pinned
wrappers around `/simplify`, `/code-review` and `/verify`, and relay does not own the model
of a command it did not write.

## Layer 2 — INVENTORY (where the tiers are recorded)

`bindings/presets.yaml` is the inventory: 24 roles, each with a flat `model:`/`effort:` pair
plus a `modalities` block per engine. It is the only place a **per-role** tier is written down
(the one exception is the role-independent watcher node-kind pin — see Layer 3). There is no
runtime model-list query — pins are static and reviewed by hand.

**Staleness** is therefore a maintenance property, not a runtime check: a pin goes stale when a
provider retires or renames a model id, and it surfaces at dispatch as an engine-side error.
The **stub** at `tests/fixtures/model-inventory-stub.yaml` is the hand-maintained record of the
ids each engine is expected to serve — no test currently loads it, so it does not catch drift
on its own. When an engine's lineup moves, update the stub and the `modalities` pins together.

## Layer 3 — RESOLUTION (the two scripts that read it)

| Dispatch path | Resolver | Reads |
|---|---|---|
| in-session `agent()` | `scripts/resolve-tier.sh` | flat `model:`/`effort:` |
| acpx worker | `skills/dispatching-acpx-agents/acpx-dispatch.sh` | `modalities.<engine>` per the effective mechanism |

`resolve-tier.sh --all` prints the whole table and is the **single resolution site** for
in-session tiers — every L3 command body calls it rather than restating the ladder, so the
tiers cannot drift from the bindings file. Rows read:

```
role                         model    effort
implementer                  sonnet   high
plan-writer                  inherit  xhigh
```

`model=inherit` means omit `opts.model`, keep `opts.effort`.

One tier lives outside the inventory: the `delegate-and-watch` **outer watcher** `agent()`
node is a node-kind constant (not a role) pinned inside `resolve-tier.sh` — query it with
`resolve-tier.sh watcher`; it is also printed in the `--all` header. It honors the same
`in_session_tiers` gate and resolves to `inherit` when tiers are off. Rationale lives in
`skills/delegate-and-watch/SKILL.md` § Watcher tier.

**The gate.** In-session tiers are ON unless `.claude/relay.json` sets
`"in_session_tiers": false`, in which case every row prints `inherit` and leaves take the
session model — the pre-4.14.0 behavior, kept as an escape hatch. `parse-engine-agent.sh`
exports the decision as `RELAY_IN_SESSION_TIERS`; `resolve-tier.sh` honors that variable when
set and otherwise reads the config itself, so `/relay:diagnose` (which has no Step 0) resolves
correctly standalone.

## Invariants

- A tier is per role, never per task instance. Dispatch reads the pin; it does not re-derive it.
- Effort values outside `{low, medium, high, xhigh}` are rejected, not coerced.
- `inherit` is in-session only; acpx paths must carry a concrete id in `modalities.*`.
- Command bodies never restate the ladder — they call `resolve-tier.sh` and transcribe it.

Calm imperatives only.
