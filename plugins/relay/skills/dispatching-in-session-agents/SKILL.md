---
name: dispatching-in-session-agents
description: Use to dispatch a primitive role through the parent harness's subagent tool — resolves bindings from bindings/presets.yaml, validates capabilities, materializes role bodies, prepends the in-session-autonomous preamble, and captures verification tokens and sidecars from the returned value.
user-invocable: false
---

# dispatching-in-session-agents

## Overview

Dispatches a primitive role through the **parent harness's subagent (Agent) tool** — the
in-session counterpart of `dispatching-acpx-agents`. Both honor the same
`(role_slug, binding, inputs) → result` interface (spec §5.1). Unlike the acpx wrapper, there
is no dispatcher script; the parent agent runs the three steps below directly.

Shared §5.1 wrapper contract, result shape, role resolution order, and agentType derivation
table: see `docs/dispatch-contract.md`. This skill keeps only its in-session locus-delta
(parent coordinator runs the sub-agent steps directly; no external process spawn) below.

Bindings come from the single top-level `bindings/presets.yaml` (spec §5.3), keyed by role slug
under a `roles:` mapping.

**Note:** tools / isolation / max-turns are carried **natively** by each `agents/*.md`
frontmatter (the native-subagent shape), so the binding entry supplies only `mechanism` +
`provides` (+ optional overrides) and the agent file supplies the rest. Model and effort are
the exception: they come from the binding's flat tier pair via `scripts/resolve-tier.sh`, so a
role's in-session tier is declared beside its acpx `modalities.*` tiers in one bindings file
instead of drifting in agent frontmatter. (The two dispatch paths still read different fields
— the flat pair here, `modalities.*` on the acpx side — and may deliberately differ per role;
see the 4.14.0 CHANGELOG's "Not addressed" note.)

## What to do per dispatch

### (a) Resolve binding overrides from `bindings/presets.yaml`

Look up the role slug under `roles:`. Override precedence:

```
CLI flag  >  binding entry (presets.yaml roles.<slug>)  >  agent frontmatter default
```

In-session bindings have `mechanism: in-session` and always run the Claude engine. The binding's
flat `model:`/`effort:` pair is the in-session tier source, resolved through
`scripts/resolve-tier.sh` — the single resolution site; never read the fields by hand. Tiers are
ON unless `.claude/relay.json` sets `"in_session_tiers": false`. A role whose tier resolves to
`model=inherit` has `opts.model` omitted so the node inherits the session model, while its
`opts.effort` still applies; `inherit` is how the never-downshift roles are expressed as of
4.14.0, replacing the hardcoded `plan-writer`/`spec-simulator`/`panel-moderator` downshift
exception that each command body used to repeat. The `modalities.claude` block is the
acpx-claude dispatch tier, not an in-session source. Any
`isolation` / `max_turns` the binding sets overrides the
agent's native frontmatter; anything it omits falls through to `agents/<slug>.md`. Validate the
role's `requires` against the binding's `provides`; reject before dispatch if any is missing.

### (b) Resolve role file and derive agentType (§5 resolution order)

Resolve the role file in the order `docs/dispatch-contract.md` gives (`RELAY_ROLE_PATH`
override, then `roles/<slug>.md`, then `agents/<slug>.md` for kept agents only). Derive the
agentType from the binding: `role-class: registered` uses the binding's explicit `agentType:`
verbatim; otherwise:

| `role-class: writer` | `relay:leaf-worker` |
|---|---|
| `role-class: reader` | `relay:leaf-reader` |

The two generic leaves require an injected role body assembled from the resolved role file.

### (c) Build the prompt + prepend the in-session-autonomous preamble

Materialize the role body from the resolved role file (everything after the YAML frontmatter),
substituting `{{SLOT}}` placeholders from the inputs. Prepend the **in-session-autonomous
preamble**: the subagent runs autonomously, asks no clarifying questions, does not commit (the
parent commits for it), forbids `AskUserQuestion`, and emits each verification token on its own
line in its final return value before stopping. Append the role's Output Contract reminder.

Invoke the parent harness's Agent (subagent) tool using the DERIVED agentType (from the derivation
table above) with the assembled role body as the prompt. For role-backed dispatches, the `roles/<slug>.md`
body (frontmatter-stripped, slots filled, preamble prepended) is passed to the generic leaf.

### (d) Capture envelope tokens from the Agent-tool return value

Invoke the parent harness's Agent (subagent) tool with the wrapped prompt. The capture region is
the **full return value** (spec §5.6). Apply `^([A-Z][A-Z0-9_]*)(=(.*))?$` per line to capture
each declared `envelope_token` (bare-marker presence or value after `=`), and validate every
required sidecar exists and is non-empty. Retry up to `binding.retries` on `verification_failed`;
return the structured result on terminal states.

## Capability matrix (spec §5.4)

The in-session mechanism provides `parent_harness_tool:agent` (always), `git_write` (always),
`worktree_isolation` (only when the entry-point command created a worktree), and the
parent-harness MCP capabilities (`playwright`/`context7`/`perplexity`) when those MCPs are
installed in the parent harness (detected at boot).

## Writer-Role Landing Contract

The in-session leg of the contract in `docs/dispatch-contract.md` (pin injection before step
(c), post-return landing-verify after step (d), the outcome table). Deltas for this skill:

- The path is `${WORKTREE:-$REPO_ROOT}`. `WORKTREE` is the env var the entry-point command
  sets when it created a worktree for this session; fall back to `REPO_ROOT` when no worktree
  isolation is active. The `worktree_isolation` capability flag is a sandboxing hint to the
  fixer, not a path variable. As of v4.46.0 every source-modifying L3 command prints
  `RELAY_WT_ACTIVE=<toplevel>` in its Step 0.55 block after the worktree gate settles, and
  the Workflow-generation step fills the `{{WORKTREE_PATH}}` and `{{EXPECTED_HEAD}}` slots of
  every writer-role `agent()` node's composed prompt with that literal (§5 table, in-session
  writer row), so the path reflects the run's active worktree; the `REPO_ROOT` fallback still
  covers a caller that supplies nothing.
- Add `WORKTREE_PATH` (= `${WORKTREE:-$REPO_ROOT}`) and `EXPECTED_HEAD` (the captured SHA)
  to the slot substitution context; the fixer's `Pre-Flight Base Pin` section reads
  `{{WORKTREE_PATH}}` and `{{EXPECTED_HEAD}}`.
- On edits present, the parent coordinator commits the dirty tree (the "parent commits for
  it" clause of the in-session-autonomous preamble). On a failure, record it as a finding in
  the refining loop or a blocked task in L3 implement.

## See also

- `skills/dispatching-acpx-agents/` — sibling wrapper for the cross-process dispatch mechanism (ships its own `acpx-dispatch.sh` driver script).
- Spec §5.1 (wrapper contract), §5.2 (responsibilities), §5.3 (bindings registry), §5.4 (capability matrix), §5.5 (preambles), §5.6 (output channel).
