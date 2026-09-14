---
name: dispatching-acpx-agents
description: Use to dispatch a primitive role through `acpx <engine> exec` (claude, codex, opencode) — resolves bindings from bindings/presets.yaml, validates capabilities, materializes the role body, prepends the agents-autonomous preamble, and captures verification tokens and sidecars from the child's stdout. The cross-process counterpart of dispatching-in-session-agents.
user-invocable: false
---

# dispatching-acpx-agents

## Overview

Implements the spec §5.2 dispatcher contract for the acpx mechanism — the cross-process counterpart of `dispatching-in-session-agents`. Both honor the same `(role_slug, binding, inputs) → result` interface (spec §5.1).

Shared §5.1 wrapper contract, result shape, role resolution order, and agentType derivation table: see `docs/dispatch-contract.md`. This skill keeps only its out-of-session locus-delta (driver env-var names, driver envelope, fast-path / v2-candidate driver) below.

It takes a `(role_slug, binding, inputs)` tuple, materializes the substituted role body from `roles/<slug>.md` (falling back to registered `agents/<slug>.md` only for kept registered agents), drives the engine child via `acpx` (claude / codex / opencode), captures verification tokens and sidecars from the child's stdout, and returns a structured result. Bindings come from the single top-level `bindings/presets.yaml` (spec §5.3), keyed by role slug under a `roles:` mapping.

Files in this wrapper:

- **`SKILL.md`** (this file) — the wrapper's responsibilities, for discovery and review.
- **`preamble.md`** — the agents-autonomous preamble, verbatim from spec §5.5.
- **`acpx-dispatch.sh`** — dispatcher entry point (bash + yq + jq) implementing the §5.2 contract.
- **`codex-session-driver.sh`** — thin codex-session turn driver, spawned as a child of `acpx-dispatch.sh`.
- **`claude-session-driver.sh`** — thin claude-session turn driver, spawned as a child of `acpx-dispatch.sh` for `acpx-claude` dispatches.
- **`opencode-session-driver.sh`** — thin opencode-session turn driver, spawned as a child of `acpx-dispatch.sh` for `acpx-opencode` dispatches.
- **`parse-turn-protocol.sh`** — reads `verify_artifact` from the role file's top-level frontmatter.

## Wrapper responsibilities (per spec §5.2)

1. **Resolve bindings.** Read `bindings/presets.yaml`, look up the role slug under `roles:`, instantiate per-role dispatch handles. Precedence: CLI flag > binding entry > agent frontmatter default.
2. **Validate capabilities.** A role's `requires:` is a CAPABILITY namespace (`read_files`, `run_bash`, `write_files`); what satisfies it is the tool set of the leaf the role's `role-class` derives (`writer` → `relay:leaf-worker`, `reader` → `relay:leaf-reader`) — never the binding's `provides:`, which is the disjoint envelope-token namespace (see `delegate-leaf/SKILL.md` and `scripts/capability-validate.js` → `validateRoleAgainstTools`). This gate is enforced statically over every role by `tests/unit/skill-structure/test_capability_gate.py`, so a mismatched role fails the suite before it can be dispatched. The legacy `requires ⊆ provides` intersection applies ONLY to kept native-agent files that carry no `role-class`; for those, a miss emits one `MISSING_CAPABILITY=<id>` line on stderr per miss, exit code 2 in `--validate-only` mode.
3. **Materialize the role body.** Resolve the role file via the §5 resolution order in `docs/dispatch-contract.md` (`RELAY_ROLE_PATH` override, then `roles/<slug>.md`, then `agents/<slug>.md`). Do `{{SLOT}}` substitution for inputs and sidecar paths in one pass, write the prompt to a per-run scratch path under `$WORKTREE/.acpx-prompts/<run-id>/`.

   `role-class` drives the in-session agentType only; acpx dispatch reads `mechanism` from the binding and ignores `role-class`:

   | `role-class: writer` | `relay:leaf-worker` |
   |---|---|
   | `role-class: reader` | `relay:leaf-reader` |
4. **Wrap with scaffolding.** Prepend `preamble.md` (the §5.5 agents-autonomous preamble); append the Output Contract reminder. The preamble carries the autonomy posture, commit policy, retry policy, and output channel — the HOW the role omits.
5. **Resolve the modality, then execute via acpx.** Effective mechanism is `ACPX_MECHANISM_OVERRIDE` when set (the coordinator passes the dispatch-map mechanism for the run's mode — `claude`/`codex`/`hybrid`), else the static `binding.mechanism` (hybrid-mode default). The mechanism selects the per-engine `modalities` block: `acpx-claude` → `modalities.claude` (`opus` + effort); `codex-session`/`acpx-codex` → `modalities.codex` (work-type model + effort); the flat `model:`/`effort:` pair is the in-session tier source, resolved by `scripts/resolve-tier.sh` (gated by `in_session_tiers`, default on) — acpx dispatch consults only the flat `model` as a last-resort fallback (inline bindings, opencode), exactly as before; the flat `effort` is never applied on the opencode path (the opencode modality blocks deliberately omit effort — `set effort` returns ACP -32602). **`acpx-claude` / `acpx-opencode`:** route through a dedicated session driver (`claude-session-driver.sh` / `opencode-session-driver.sh`). The driver calls `acpx <engine> sessions ensure --name <session>`, then `acpx <engine> set model <m> -s <session>` and `acpx <engine> set effort <e> -s <session>` (soft-degrade: on rc≠0, log `[warn]` and continue at adapter default), then runs the turn via `acpx --format json --json-strict --approve-all --permission-policy <policy> --cwd <cwd> --timeout <t> <engine> -s <session> <prompt>` — omitting `--model` and `--effort` per-turn (session record auto-reapplies both). Both permission flags are unconditional; see **The permission grant** below. **`codex-session`:** the codex driver now uses the same shape — `set model <m>`, `set reasoning_effort <e>`, `set mode agent-full-access`, then a turn with no `--model`. **`acpx-codex`** (one-shot `exec`) still passes a plain, adapter-advertised model id via `--model` and rides reasoning effort on `CODEX_CONFIG`, because `exec` has no `set` subcommand and acpx rejects the bracket encoding. The `--effort` CLI flag was removed; it was never a valid `openclaw/acpx` flag.
6. **Capture and verify.** Apply `^([A-Z][A-Z0-9_]*)(=(.*))?$` per line to the last 200 lines of stdout (spec §5.6). For each declared `output-token`, record bare-marker presence or the value after `=`. Validate every required sidecar exists and is non-empty. Retry up to `binding.retries` on `verification_failed`; return the structured result on terminal states.

## Turn protocol — reading top-level frontmatter

`parse-turn-protocol.sh` reads `verify_artifact` from the role file's top-level frontmatter (migrated from the `relay:` sub-block in PR3; role files under `roles/` carry `verify_artifact` at the root frontmatter level). It exports:

- `TP_TERMINAL_TOKEN` — PINNED to `ROLE_DONE`, NOT derived positionally from `relay.envelope_tokens` (several roles don't list `ROLE_DONE` first, and `server-runner` has none).
- `TP_VERIFY_ARTIFACT` — from the top-level `verify_artifact` key (with `{{SLOT_*}}` substitution). Only the 4 folding roles (`implementer`/`test-writer`/`fix-coder`/`plan-writer`) carry it; an empty value signals "fast-path eligible, no freshness gate" to `acpx-dispatch.sh`.

`TP_MAX_TURNS` and `TP_NUDGE_PROMPT` are no longer exported by the parser — the `delegate-and-watch` watcher owns multi-turn management.

`{{SLOT_*}}` substitution is macOS bash-3.2 compatible (`{{REPO_ROOT}}`/`{{PLAN_PATH}}` resolve from `SLOT_*` env via indirect expansion, no `eval`).

## Session driver env-var contract (spec §5.4)

All three session drivers (`codex-session-driver.sh`, `claude-session-driver.sh`, `opencode-session-driver.sh`) run as child subprocesses of `acpx-dispatch.sh`; their stdout is the envelope returned to the parent. Drivers are single-turn. The canonical per-mechanism table, with the meaning of each var, is in `docs/dispatch-contract.md` (Driver env-var table). The names:

- Shared, required (`:?required`; the driver aborts if unset): `ACPX_ENGINE`, `ACPX_MODEL`, `ACPX_CWD`, `ACPX_TIMEOUT`, `ACPX_SESSION_NAME`, `ACPX_PROMPT_FILE`.
- Shared, caller-optional (default in-driver): `ACPX_TERMINAL_TOKEN` (default `ROLE_DONE`), `ACPX_VERIFY_ARTIFACT` (default empty).
- codex only (9 vars total): `CODEX_CONFIG` — codex effort rides this var, never the model id.
- claude/opencode only: `ACPX_PERMISSIONS` (role intent; no longer gates any flag). opencode routes through the same driver block as claude and never carries `CODEX_CONFIG`.
- all engines: `ACPX_EFFORT` (the codex driver now applies it via `set reasoning_effort`) and `ACPX_POLICY_FILE` (absolute path to `bindings/acpx-policy.json`; each driver falls back to the plugin-relative path when empty).
- codex only: `CODEX_CONFIG` is still written to the sidecar for one release so a watcher on the 4.50.0 contract sources it cleanly, but `codex-session-driver.sh` no longer reads it. Remove in 4.52.0.
- Sidecar-only, caller-optional (all mechanisms): `RELAY_MAX_TURNS` (turn cap, default 10; a sidecar value read by delegate-and-watch, not a driver env var — no driver reads it), `ACPX_SESSION_NAME_OVERRIDE`, `RELAY_ROLE_PATH`.

`acpx-dispatch.sh` writes all resolved driver vars to the `~/.acpx/sessions/${session}.env` sidecar before it starts the driver; the `delegate-and-watch` watcher sources that sidecar at entry. `ACPX_VERIFY_ARTIFACT` comes from `TP_VERIFY_ARTIFACT` (the role's top-level `verify_artifact`), so a folding role gets a non-empty artifact path and the watcher applies the two-predicate freshness gate (mtime bump AND content-hash change) before it reports `done`.

## Driver envelope contract

The driver's stdout envelope contains exactly:

- `ROLE_RESULT=<DONE|NOT_DONE|BLOCKED|ERRORED|NEEDS_DECISION>`
- `TURNS_USED=<N>`
- `BLOCKED_REASON=<single line>` (only when `ROLE_RESULT=BLOCKED`)
- `QUESTION_TEXT=<single line>` (only when `ROLE_RESULT=NEEDS_DECISION`)
- Verification tokens from the final turn's reply, filtered by `extract_envelope`: any line matching `^[A-Z][A-Z0-9_]*=.*$`, plus the terminal-token line.
- Terminal token line (`ROLE_DONE`).

Intermediate-turn output never reaches the parent; it goes only to `~/.acpx/sessions/${session}.driver.log`.

## Codex fast-path branch

When a role declares `max_turns: 1` AND has no `verify_artifact`, the dispatcher bypasses the driver subprocess and invokes `acpx codex exec -f` directly. The fast path still prepends the `<<DO_NOT_LOAD_SKILLS>>` preamble and applies the same `extract_envelope` filter, so context isolation holds across both dispatch paths.

### The codex registry override is gone (4.51.0)

Relay 4.6.1 added `ACPX_CODEX_AGENT_OVERRIDE`, which replaced the `codex` positional
with `--agent "npx -y @agentclientprotocol/codex-acp@latest"`, because acpx pinned its
codex adapter to a broken `@agentclientprotocol/codex-acp@^0.0.44`. acpx **0.12.1**
moved that pin to `^1.1.5`, which resolves to the same adapter the override fetched.
Relay's floor is now 0.13.2 (`scripts/acpx-floor.sh`), so every codex path passes the
plain `codex` positional and the override and its env var are removed.

Removing it also unblocked the session driver. `--agent` cannot be combined with a
positional engine, and the session subcommands need that positional to scope the
session by agent identity — with the override in force, `sessions ensure` labelled the
session `claude`. That is why `codex-session-driver.sh` could never use the override,
and why it could not set reasoning effort through session config. It now does; see
below.

## The permission grant

Every acpx turn relay runs passes both flags, unconditionally:

```
--approve-all --permission-policy <plugin>/bindings/acpx-policy.json
```

`--approve-all` answers each ACP permission request. The policy file
(`{"defaultAction": "approve"}`) sets the same answer for acpx's per-tool rule engine,
so a future acpx that consults the policy before the mode gives the same result.
Together they are the widest grant acpx exposes.

Codex keeps a sandbox of its own behind acpx's layer, so codex paths widen that too:
the session driver runs `set mode agent-full-access`, and the one-shot `exec` path —
which has no `set` subcommand — carries `approval_policy: never` and
`sandbox_mode: danger-full-access` in `CODEX_CONFIG` (see `build_codex_config`).

Before 4.51.0 `--approve-all` was gated on `permissions: approve-all` exactly. That
silently broke the three roles bound to `approve-reads` (`code-reviewer`,
`doc-reference-reviewer`, `ui-code-evaluator`): acpx's default mode is `--approve-reads`
and its non-TTY fallback is `deny`, so those workers had every write request refused
and nothing reported it. `permissions` in `bindings/presets.yaml` now records the
role's intent only — **read-only is enforced by the role body, not by the substrate.**

The path reaches the drivers as `ACPX_POLICY_FILE`, written into the session sidecar so
a delegate-and-watch re-invocation carries it. Each driver falls back to the
plugin-relative path when the var is empty.

## Envelope capture (`acpx-envelope.sh`)

Every acpx call runs under `--format json --json-strict` and pipes the raw ACP
JSON-RPC stream through `acpx-envelope.sh`, which returns the turn's final assistant
text. Callers then apply the unchanged frozen contract — the capture regex
`^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$` and the `^BLOCKED:` / `^NEEDS_DECISION:` first-line
sentinels — to that text. Only the source of the text changed.

`--format quiet` printed the assistant text with no structure, so a chunk boundary
landing mid-line could glue two envelope lines together and corrupt the parse. The JSON
stream carries a `messageId` on every chunk, so the script groups chunks by message,
concatenates them in stream order, and emits the last message. Live 0.13.2 samples show
claude splitting mid-token (`"ST"` then `"ATUS=ok\nROLE_DONE"`) and codex emitting one
chunk per word; both rebuild byte for byte. Codex also tags chunks with
`_meta.codex.phase`, so only `final_answer` chunks are kept and commentary is dropped;
claude and opencode send no phase and every chunk is kept.

The script also reports session-config replay failure. acpx >= 0.13.1 re-applies a
reconnected session's saved model and config options and reports when that fails
instead of continuing on adapter defaults. When the stream carries
`Failed to replay saved session`, the script emits `ERRORED_REASON=config_replay_failed`
as its first line; each driver classifies that as `ROLE_RESULT=ERRORED` before any
other outcome, so `delegate-and-watch` routes it to `errored` and never re-dispatches
the worker on a model it did not ask for.

The raw stream is kept beside the extracted text (`<session>.turn.ndjson`, and
`<stdout>.ndjson` on the one-shot paths) for forensics.

## v2 candidate — `codex-session-driver.sh`

`codex-session-driver.sh` is a **v2 candidate** for consolidation: either **merged** into `acpx-dispatch.sh` (which already inlines a fast-path mirroring the driver's `extract_envelope` filter) or **upstreamed** to the ACPX CLI as a first-class multi-turn `exec` mode. v1 keeps it a separate thin bash driver so the turn loop is auditable in isolation; a v2 follow-up evaluates the merge/upstream once the contract stabilizes. `[inferred]`

## Writer-Role Landing Contract

The acpx leg of the contract in `docs/dispatch-contract.md` (pin injection, post-return landing-verify, the outcome table). Deltas for this skill:

- The coordinator, not `acpx-dispatch.sh`, captures `EXPECTED_HEAD` from `WORKTREE` (the env var the caller sets before it invokes the script) and puts `EXPECTED_HEAD` and `WORKTREE_PATH` in the `inputs` map.
- `acpx-dispatch.sh` materializes them as `SLOT_EXPECTED_HEAD` and `SLOT_WORKTREE_PATH` in the standard `{{SLOT}}` substitution pass (step 3); the fixer's `Pre-Flight Base Pin` section reads `{{EXPECTED_HEAD}}` and `{{WORKTREE_PATH}}`.
- Run the landing-verify in `WORKTREE` after `acpx-dispatch.sh` returns, before you trust `ROLE_DONE` or any output token.

## --validate-only mode

```
bash acpx-dispatch.sh --validate-only --role <path-to-role.md> --binding <preset-slug> [--presets-path <path>]
```

Exit codes: `0` = pass; `2` = capability mismatch (stderr names every missing capability, prefixed `MISSING_CAPABILITY=`); `3` = role-file parse error. Runs no child process.

## Mechanism scope

| mechanism | Pattern | Engine |
|-----------|---------|--------|
| `acpx-claude` | A (persistent) or B (one-shot) | claude via acpx |
| `acpx-codex` | B (forced) | codex via acpx |
| `acpx-opencode` | A or B | opencode via acpx |
| `codex-session` | thin driver running `acpx codex -s <name>` turns | codex via acpx |

Bindings with `mechanism=in-session` route to `dispatching-in-session-agents`; `acpx-dispatch.sh` rejects them at the mechanism-dispatch step.

## Files

- `acpx-dispatch.sh` — entry script implementing the §5.2 contract in bash with `yq` and `jq`.
- `codex-session-driver.sh` — thin codex-session turn driver (v2 merge/upstream candidate).
- `claude-session-driver.sh` — thin claude-session turn driver for `acpx-claude` dispatches.
- `opencode-session-driver.sh` — thin opencode-session turn driver for `acpx-opencode` dispatches.
- `parse-turn-protocol.sh` — reads `verify_artifact` from the role file's top-level frontmatter, pins `terminal_token=ROLE_DONE`.
- `preamble.md` — agents-autonomous preamble (verbatim from spec §5.5).

## See also

- Spec §5.1 (wrapper contract), §5.2 (responsibilities), §5.3 (bindings registry), §5.4 (capability matrix), §5.5 (preambles), §5.6 (output channel).
- `skills/dispatching-in-session-agents/` — sibling wrapper for the parent-harness mechanism.
- `docs/agent-roster.md` — primitive contract and `requires`/`provides` semantics.
