# Relay Architecture

> Orientation for engineers reading or changing relay. Start here, then follow the
> links into the four contract documents for exact detail.
>
> Companion: [`contributing.md`](contributing.md) — how to make a change land.
> Counts and paths in this file are asserted by
> `tests/unit/skill-structure/test_docs_freshness.py`; see
> [Keeping this document honest](#keeping-this-document-honest).

## What relay is

Relay is an **orchestration layer, not a capability layer**. It ships no SDLC
primitive of its own — brainstorming, plan and spec authoring, TDD, debugging,
worktrees and code review are all delegated to `superpowers:*`, and every command
runs a presence check that blocks if superpowers is missing.

What relay adds is the machinery *between* those primitives:

- a **dispatch abstraction** that lets one unit of delegated work run either as an
  in-session Claude subagent or as an out-of-process worker on a different vendor's
  model, behind a single `(role_slug, binding, inputs) → result` envelope;
- a **generic adversarial refinement engine** with four target adapters;
- a **thin command surface** where each command classifies the task, resolves a
  dispatch axis, guarantees worktree isolation, and then emits exactly one dynamic
  `Workflow` — the command body holds no orchestration logic itself;
- a **deterministic reliability spine** that verifies the model-generated workflow
  actually ran every node it started.

The design is best read as a catalogue of countermeasures to specific observed
silent failures. Most unusual decisions in the tree trace back to a documented
incident, and the CHANGELOG entry that introduced them usually names it.

The standing decisions — the ones that are hard to reverse and surprising without
context — are recorded as [ADRs](adr/README.md). This document describes *how relay
works*; the ADRs record *why it was built that way and whether that still holds*.
Where a section below rests on a decision, it links the record.

## Layers

```
L3  commands/*.md      parse args, classify, emit ONE dynamic Workflow
L2  skills/*/SKILL.md  reusable orchestration patterns
L1  roles/ + agents/   role bodies executed inside generic agent containers
```

There is exactly **one orchestration substrate**: Claude Code's native `Workflow`
tool. In-session versus out-of-process is *not* a pipeline-wide fork — it is
demoted to a per-role binding resolved at workflow-generation time. See
[`orchestration-substrates.md`](orchestration-substrates.md).

## The agent / role split

This is the central idea, and the thing to understand before changing anything.

**An agent is a capability container. A role is a behavior payload.**

| | `agents/*.md` | `roles/*.md` |
|---|---|---|
| what it is | a Claude Code subagent registration | engine-neutral prompt text + an I/O contract |
| frontmatter | `name`, `description`, `tools`, optional `model` | `role-version`, `role-class`, `input-slots`, `output-tokens`, `terminal_token`, `requires` |
| must **not** declare | — | `name`, `tools`, `model` |
| count | 7 | 22 |

An agent carries no task; a role carries no tools. `bindings/presets.yaml` is the
join table, and `role-class` mechanically derives the container:

| binding shape | agentType |
|---|---|
| explicit `agentType:` | `relay:code-reviewer`, `relay:scout` |
| `role-class: writer` | `relay:leaf-worker` |
| `role-class: reader` | `relay:leaf-reader` |

### Why the split exists

1. **Tool grants are fixed at registration; behavior is not.** 22 agents would mean
   22 tool surfaces to audit and 22 descriptions in every session's inventory. The
   tool axis collapses to two values, and "which tools" becomes a consequence of
   `role-class` rather than a per-role decision.
2. **Role bodies must be portable off Claude Code entirely.** The same
   `roles/implementer.md` body ships to a codex or opencode process —
   `acpx-dispatch.sh` strips the frontmatter and writes the remainder to a prompt
   file. Those engines have no concept of a Claude Code agent.
3. **Depth-1 enforcement.** Neither leaf lists `Agent` or `Skill`, and unlisted
   tools are absent from the session at initialization, so a dispatched role
   structurally cannot spawn subagents or load skills. This is also why role bodies
   vendor their rubrics inline instead of calling `Skill()`.

### Agent registration is derived, not declared

`agents/<slug>.md` must set `name: <slug>` — bare. The loader prefixes the plugin
namespace, producing `relay:<slug>`. Writing `name: relay:<slug>` prefixes twice and
registers `relay:relay:<slug>`, which no dispatch site references.

Every `*.md` in `agents/` registers, including one with no frontmatter — which
receives an unrestricted tool grant. Documentation therefore lives in `docs/`, never
in `agents/`. Both rules are pinned by
`tests/unit/skill-structure/test_agent_registration.py`; both were shipped bugs
before 4.18.0.

## The envelope — a typed ABI over model output

Roles terminate by emitting a parseable envelope. Four token forms are **frozen**
and require a major bump to change:

| Token | Meaning |
|---|---|
| `ROLE_DONE` | bare terminal marker, own line, last |
| `BLOCKED: <reason>` | first-line sentinel |
| `NEEDS_DECISION: <question>` | first-line sentinel → driver gate |
| `^[A-Z][A-Z0-9_]*=.*$` | KEY=VALUE grammar, scanned over the last 200 stdout lines |

The two sentinels contain a colon and deliberately do *not* match the envelope
regex — they are classified by a dedicated first-line branch. Values are
machine-checked downstream: `FILES_TOUCHED` is validated with
`jq -e 'type == "array" and all(type == "string")'`. Full detail in
[`dispatch-contract.md`](dispatch-contract.md).

## Model tiers are chosen by failure mode

The ladder is picked by *how a role fails*, not by how large its task is. The
governing question is never "is this job hard?" but "if this leaf returns something
plausible and wrong, what catches it?"

| Rung | Criterion |
|---|---|
| `inherit` | **Silent-failure roles** — a wrong-but-plausible output is accepted downstream and nothing catches it. Omits `opts.model` so the node tracks the session model; upgrading the session is the lever that buys these roles capability. |
| `opus` | Critics whose miss mode is a false CLEAN. Every role of the `verification` category. |
| `sonnet` | Execution work that *is* verified downstream — implementers checked by tests, and every role of the `fixes` category, whose output a critic re-reads. |
| `haiku` | Mechanical, narrow decision surface. |

`effort` is an independent axis and still applies on an `inherit` row. Simulator
roles mirror the model of whichever role acts on their artifact next, so a
simulation runs at the tier whose risk it predicts.

Two groups of roles carry a `category` field, and one flag moves each group.
`--fixes-model` addresses `fixes` — the four roles that repair an artifact after a
critic found a problem. `--verification-model` addresses `verification` — the seven
critics that decide whether the work is done. Each flag takes `sonnet`, `opus`, or
`fable`, replaces the model of every role of its category, and changes no `effort`.
`.claude/relay.json` carries the same two values as `fixes_model` and
`verification_model`. `skills/selecting-the-right-model/SKILL.md` holds the full map.

`scripts/resolve-tier.sh` is the **single resolution site** — run
`scripts/resolve-tier.sh --all` and transcribe its output rather than deriving the
table by hand.

## The dispatch axis

Two orthogonal values resolved once at Step 0 by `scripts/parse-engine-agent.sh`:

- **`engine`** ∈ `in-session` · `acpx` · `smart-routing` · `bg-sessions` · `session-tree` — *where* a leaf runs
- **`agent`** ∈ `claude` · `codex` · `opencode` · `hybrid` · `smart-routing` — *which* model family

Resolution is layered **per axis**: flag > `.claude/relay.json` pin > default. The
default layer is **per command**: `/relay:implement` and `/relay:verify` export
`RELAY_DEFAULT_ENGINE=acpx` / `RELAY_DEFAULT_AGENT=claude` before they source the
parser, so their leaf work leaves this session unless a flag or a pin says otherwise.
`/relay:refine`, `/relay:execute` and `/relay:drive` keep `in-session`. The axis line
still prints `source: default` in both cases.
Invariants are enforced loudly and never coerced — `in-session` requires
`agent=claude`; `bg-sessions` requires `agent=claude`; `session-tree` requires
`agent=claude`; `smart-routing` rejects literal worker agents. `session-tree` is a
substrate change, not a per-leaf mechanism: under it a command generates no
Workflow at all — see `docs/orchestration-substrates.md`. v1 scope is
`/relay:implement` only; the other three L3 commands that accept the axis reject
`session-tree` with an engine-not-supported error.

The axis selects a *family*, not a pipeline mode. A single `--engine acpx --agent
codex` run splits: some roles go out-of-process while the three browser critics stay
in-session, because the codex models have no vision. That carve-out is only
expressible because mechanism is a per-role binding.

## The refinement engine

One generic loop — round → critics → optional aggregator → fixer → post-fix →
persist → converge — parameterized by an adapter interface:

```
load()                    → subject snapshot
snapshot(subject)         → opaque pre-state for diffing
diff(snapshot, current)   → structured diff for reporting
post_fix(action)          → re-read | verify-tests | revert-on-fail
persist(round, findings)  → write resume state
recover()                 → read resume state, return last completed round
```

Four thin shims configure it, and two convergence modes exist: `binary` (spec, plan,
pr — converges when no critical or important findings remain) and `scored` (ui —
threshold-AND across five dimensions, with plateau detection flipping the fixer into
`pivot` mode). See [`refinement-contract.md`](refinement-contract.md).

**Three ways a round fails without being a pass** — the loop's design centre:

1. A critic's findings file missing or empty is `record_failure`, never zero findings.
2. `landing_verify_failed` skips post-fix and persist and continues within the cap.
3. A delegated dispatch returning `errored`/`blocked`/`not-done` gets exactly one
   fresh-session retry, then `record_failure`. `max_rounds` is the loop cap, not a
   retry budget.

## The anti-silent-failure spine

Two mechanisms sit between a role claiming success and the coordinator believing it.

**Writer-role landing contract.** Before dispatch the coordinator pins
`EXPECTED_HEAD`. After return — before trusting `ROLE_DONE` — it runs
`git status --short` and `git diff` in the absolute worktree path *the coordinator
knows*, never the agent's self-reported cwd. A role claiming success with an empty
diff and no valid no-change signal is recorded as a dispatch failure.

**The completeness gate.** `scripts/verify-run-completeness.sh` is always-on. A node
soft-failed if it has a `started` journal record and no `result` record for the same
`agentId`. It exists because two real runs lost half their dispatch nodes and still
reported `status: "completed"` with every node reading `state: "done"`. The rejected
predicates are recorded in the source so they are not re-proposed.

The doctrine both express, and the one to preserve when changing this code:

> **Fail to indeterminate, never to a pass.** A check that cannot run reports
> `DEGRADED`, not `CLEAN`. A soft mitigation around a hard failure is how the
> failure becomes silent.

## Where to look

| Question | File |
|---|---|
| **Why is it built this way, and does that still hold?** | [`adr/README.md`](adr/README.md) |
| How is a role dispatched, and what comes back? | [`dispatch-contract.md`](dispatch-contract.md) |
| How does a refinement loop converge? | [`refinement-contract.md`](refinement-contract.md) |
| What substrate runs the orchestration? | [`orchestration-substrates.md`](orchestration-substrates.md) |
| What vocabulary may an L2 skill declare? | [`language-reference.md`](language-reference.md) |
| Which agents exist and what can they touch? | [`agent-roster.md`](agent-roster.md) |
| Which roles exist and who consumes them? | [`../roles/README.md`](../roles/README.md) |
| How do I make a change land? | [`contributing.md`](contributing.md) |

## Keeping this document honest

This file states counts and file paths that drift as the plugin changes. Rather than
relying on reviewer memory, `tests/unit/skill-structure/test_docs_freshness.py`
asserts them against the tree:

- every repo-relative path referenced here resolves to a real file;
- the agent and role counts in the table above match the directories;
- the skill-constant sizes named in [`contributing.md`](contributing.md) match those
  constants, and their sum accounts for every directory under `skills/`;
- the tier rungs named here are exactly the rungs `bindings/presets.yaml` uses;
- the axis enum values match `scripts/parse-engine-agent.sh`.

Changing any of those without updating this document fails the suite. That is the
same mechanism that already pins `"22 roles"` in `roles/README.md` and
`"7 agents total"` in `agent-roster.md` — prose is source code here, so it is tested
like source code.
