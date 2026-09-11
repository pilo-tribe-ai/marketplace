# Relay Dispatch Contract

> Operative reference for `relay:dispatching-acpx-agents` and `relay:dispatching-in-session-agents`.

## Public envelope contract

The following four tokens are **frozen** — their exact byte sequences are pinned in
`tests/unit/skill-structure/test_envelope_tokens.py` and must not change without a major
version bump:

1. **`ROLE_DONE`** — bare terminal token. Emitted on its own line as the last output line
   when a role completes successfully. No suffix, no argument.
2. **`BLOCKED: <reason>`** — first-line sentinel. When the first non-empty content line of
   a turn starts with `BLOCKED:`, the watcher classifies the turn as `blocked` and surfaces
   the text after the colon as the blocked reason.
3. **`NEEDS_DECISION: <question>`** — first-line sentinel. When the first non-empty content
   line starts with `NEEDS_DECISION:`, the watcher classifies the turn as `needs-decision`
   (terminal; session left open-but-detached per S1 spike outcome), and surfaces the text
   after the colon as the question for the driver gate.
4. **`KEY=VALUE` envelope grammar** — any line matching `^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$`
   is an envelope line. The dispatcher captures these from the last 200 lines of stdout.

**Explicitly NOT frozen:** per-role `envelope_tokens` (role-defined, vary per role) and
`ROLE_RESULT=<value>` (internal driver↔watcher plumbing, not part of the public surface).

**Background-session transport.** `docs/bg-dispatch-contract.md` carries the same four
frozen tokens over a different transport: the envelope travels in a message body or a
handoff file instead of on stdout. The tokens are unchanged. The two tokens that document
adds, `DECISION:` and `ESCALATION from …:`, are provisional and are not part of this
frozen set.

## §5.1 Wrapper Contract

Every dispatch invocation conforms to the `(role_slug, binding, inputs) → result` envelope:

- **`role_slug`** — key in `bindings/presets.yaml`; resolved per the §5 resolution order below.
- **`binding`** — `bindings/presets.yaml` entry: `role-class`, `model`, `mechanism`,
  `one_shot`, `max_turns`, `permissions`, `timeout_seconds`, `retries`, `provides`,
  `modalities`; optional `agentType` (registered bindings only), `verify_artifact` (4 roles).
- **`inputs`** — slot substitution context (`{{SLOT_*}}` variables resolved before dispatch).
- **`result`** — stdout captured after the `ROLE_DONE` terminal token; `output-tokens` list
  from the role file's frontmatter `output-tokens` key.

The result shape every dispatch skill returns:

```
dispatch(role_slug, binding, inputs) →
  {
    status: "completed" | "verification_failed" | "timeout" | "engine_error",
    output: <captured stdout, or the captured envelope for bg-sessions>,
    tokens: { <token-name>: <captured-value> },
    sidecars: { <sidecar-name>: <absolute-path> },
    elapsed_seconds: <float>,
    attempt_count: <int>,
  }
```

### Role resolution order

`RELAY_ROLE_PATH` override → `roles/<slug>.md` → `agents/<slug>.md` (kept agents only);
typed error `ROLE_FILE_MISSING` otherwise. The fallback to `agents/` is valid only for the
7 kept registered agents (`code-reviewer`, `scout`, `leaf-worker`, `leaf-reader`,
`gatherer`, `strategist`, `analyst`).

### agentType derivation table

| binding shape | agentType |
|---------------|-----------|
| explicit `agentType:` on the binding | use it verbatim (`relay:code-reviewer`, `relay:scout`) |
| `role-class: writer` | `relay:leaf-worker` |
| `role-class: reader` | `relay:leaf-reader` |

`role-class` drives the in-session agentType only (via the Agent tool or Workflow `agent()`).
acpx dispatch reads `mechanism` from the binding and ignores `role-class` entirely.

### Override Precedence

CLI flag > user binding (`--user-bindings`) > `presets.yaml` binding > agent frontmatter default.

### Envelope-Token Capture

The dispatcher applies `^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$` per line to the last 200 lines of
stdout. For each declared `output-token`, the bare-marker presence or value after `=` is
recorded. Note: `BLOCKED:` and `NEEDS_DECISION:` lines do NOT match this regex (they contain
a colon); they are classified by the watcher's dedicated first-line branch, not by the
envelope filter.

## Locus-Specific Deltas

Each dispatch skill keeps ONLY its locus-delta here; see the skill bodies for full driver
details.

### `relay:dispatching-acpx-agents` (locus: out-of-session)

- Driver env vars: see the table below. `acpx-dispatch.sh` writes them to the
  `~/.acpx/sessions/${session}.env` sidecar before it starts the driver. The
  `delegate-and-watch` watcher sources that sidecar at entry.
- Session name resolution: `ACPX_SESSION_NAME_OVERRIDE` is honored ahead of the default
  `${ACPX_RUN_ID}-${ACPX_ROLE_SLUG}` key.
- External role file: `RELAY_ROLE_PATH` is honored ahead of `agents/<slug>.md`; typed error
  on missing path (no silent fallback).
- Fast path: `codex-session` roles with no `verify_artifact` bypass the driver subprocess
  and invoke `acpx codex exec -f` directly.
- `ROLE_RESULT` internal enum: `DONE | NOT_DONE | BLOCKED | ERRORED | NEEDS_DECISION`.

#### Driver env-var table (canonical)

All three session drivers (`codex-session-driver.sh`, `claude-session-driver.sh`,
`opencode-session-driver.sh`) are single-turn. The multi-turn loop, the nudge prompt, the
turn cap, and the `sessions close` trap live in the `delegate-and-watch` watcher. No driver
reads a turn cap. The sidecar holds 9 driver vars for codex and 10 for claude/opencode, plus
the sidecar-only vars.

| Var | codex | claude / opencode | Set by | Meaning |
|---|---|---|---|---|
| `ACPX_ENGINE` | required | required | caller | engine subcommand: `codex`, `claude`, or `opencode` |
| `ACPX_MODEL` | required | required | caller | plain, adapter-advertised model id; no bracket or effort suffix |
| `ACPX_CWD` | required | required | caller | absolute cwd (the worktree); every session and turn passes the same `--cwd` |
| `ACPX_TIMEOUT` | required | required | caller | per-turn acpx timeout in seconds |
| `ACPX_SESSION_NAME` | required | required | caller | `${run_id}-${role_slug}` session key |
| `ACPX_PROMPT_FILE` | required | required | caller | path to the materialized, preamble-prepended prompt |
| `ACPX_TERMINAL_TOKEN` | defaulted | defaulted | driver | default `ROLE_DONE` |
| `ACPX_VERIFY_ARTIFACT` | defaulted | defaulted | driver | default empty; the watcher applies the freshness gate |
| `CODEX_CONFIG` | required | — | caller | JSON merged into the codex-acp session config; carries `model_reasoning_effort`. Codex effort rides this var, never the model id |
| `ACPX_EFFORT` | — | required | caller | `low`, `medium`, `high`, `xhigh`; applied via `acpx <engine> set effort <e> -s <session>` (soft-degrade on rc≠0) |
| `ACPX_PERMISSIONS` | — | required | caller | `approve-all` gates `--approve-all` on each turn; any other value omits the flag |

Sidecar-only vars (all mechanisms, caller-optional, no driver reads them):

| Var | Meaning |
|---|---|
| `RELAY_MAX_TURNS` | turn cap for the `delegate-and-watch` loop, default 10; the sidecar appends `RELAY_MAX_TURNS=${RELAY_MAX_TURNS:-10}` |
| `ACPX_SESSION_NAME_OVERRIDE` | replaces the default session key in every dispatch block |
| `RELAY_ROLE_PATH` | absolute path to an external role file; documented external API (`ROLE_PATH` is an undocumented internal) |

The driver receives the required vars with `:?required`, so it aborts when one is unset.
`acpx-dispatch.sh` sets `ACPX_VERIFY_ARTIFACT` from the role's top-level `verify_artifact`
key, so a folding role gets a non-empty artifact path in the sidecar.

### `relay:dispatching-in-session-agents` (locus: in-session)

- Parent coordinator runs the sub-agent steps directly; no external process spawn.
- Preamble prepended from `skills/dispatching-acpx-agents/preamble.md`.

## Capability Matrix Intent

The `modalities` block in `presets.yaml` declares per-engine model+effort. The coordinator
selects the correct entry based on `RELAY_AGENT` (claude/codex/hybrid). Hybrid routes to the
engine declared in `modalities.hybrid.engine`.

## Writer-Role Landing Contract

For every dispatch where the role has `role-class: writer`, the dispatcher applies two
additional contract steps. This section is the canonical cross-skill reference. The
satellites (`dispatching-in-session-agents`, `dispatching-acpx-agents`, `delegate-leaf`,
`delegate-and-watch`) carry only their own deltas and point here.

### Pre-dispatch pin injection

Immediately before building the role prompt, the **coordinator** (not the dispatcher script)
captures:

```bash
EXPECTED_HEAD=$(git -C "${WORKTREE:-$REPO_ROOT}" rev-parse HEAD)
```

For in-session dispatch, `WORKTREE` is the env var set by the entry-point command (fallback:
`REPO_ROOT`). For acpx dispatch, `WORKTREE` is the env var set by the caller before invoking
`acpx-dispatch.sh`. The coordinator adds `EXPECTED_HEAD` and `WORKTREE_PATH` to the slot
substitution context. `acpx-dispatch.sh` materializes them as `SLOT_EXPECTED_HEAD` and
`SLOT_WORKTREE_PATH` via the standard `{{SLOT}}` substitution pass (step 3).

### Post-return landing-verify

After the dispatcher returns (Agent tool return value or `acpx-dispatch.sh` exit), before
trusting `ROLE_DONE` or any output token, the coordinator runs:

```bash
git -C "${WORKTREE:-$REPO_ROOT}" status --short
git -C "${WORKTREE:-$REPO_ROOT}" diff
```

Always in the **absolute worktree path known to the coordinator** — never the agent's
self-reported cwd.

| Outcome | Action |
|---|---|
| Edits present (non-empty `git status --short`) | Sanity-check diff vs `FILES_TOUCHED`; coordinator commits dirty tree |
| Edits absent + valid no-change signal + pre-flight pin confirmed | Accept as legitimate no-change |
| Edits absent + no valid no-change signal (or unverified base) | Record as dispatch failure; same mechanism as other failures |

Valid no-change signals: `FILES_TOUCHED=[]` with a stated reason (fix-coder);
`ROUND_RESULT=addressed=0` with a stated reason (spec-fixer, plan-fixer).

An unverified base ("not applicable" claim from a role whose pre-flight pin failed or was
skipped) is the Variant B signature and is always a failure, regardless of no-change claim.
