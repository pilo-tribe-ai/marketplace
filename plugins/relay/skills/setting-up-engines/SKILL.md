---
name: setting-up-engines
description: Use to configure and verify the codex and opencode engines for acpx dispatch from claude — binary/version preflight, per-provider auth checks, live pinned-model probes, and a served-model audit against each engine's own session records. Interactive assistant; run via /relay:engines.
user-invocable: false
---

# setting-up-engines

Interactive assistant that walks the user through making the **codex** and **opencode**
engines dispatchable from claude via acpx, then PROVES it with live probes. Complements
`setting-up-relay` (which provisions relay's own skills/deps); this skill owns the two
external engines end to end: install → auth → probe → audit.

Run every step, report each result as you go, and finish with the readiness table
(Step 5). When a step fails, show the remediation command and — where the fix is
interactive (logins, browser auth) — ask the user to run it, then re-run the failed
probe before moving on. Never mark an engine ready on config inspection alone; only a
live served-model audit counts.

## Step 0 — acpx preflight

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/acpx-floor.sh"   # prints RELAY_ACPX_VERSION=<v>, or fails
```

`scripts/acpx-floor.sh` is the only place that states the floor. It prints the
remediation on failure, so this step never repeats the number.

Why the floor moved to **0.13.2**, in two steps:

- **0.7.0 → 0.12.0.** acpx 0.10.0 cannot apply a model to opencode sessions (`set
  model` persists, then every prompt fails — the opencode adapter does not advertise
  generic ACP model support; 0.12.0 applies it via the working path). The codex flip
  side: 0.12.0 strictly validates `--model` against adapter-advertised plain ids, so
  the pre-0.12 bracket encoding (`gpt-5.6-terra[high]`) no longer works — relay's
  dispatch passes plain ids and rides codex effort on `CODEX_CONFIG`.
- **0.12.0 → 0.13.2.** 0.12.1 refreshed acpx's own adapter pins, moving codex from a
  broken `^0.0.44` to `^1.1.5`; relay's `--agent` override for that broken pin is gone
  at this floor. 0.13.1 keeps `messageId` and `_meta` on message chunks, which
  `acpx-envelope.sh` groups by to rebuild a turn's final text. 0.13.2 restores the
  saved model and config options after a reconnect and reports a replay failure
  instead of running on defaults, which `delegate-and-watch` routes to `errored`.

## Step 1 — resolve the models to verify

Probe the models relay will actually dispatch, not hardcoded ids. Read them from the
active bindings:

```bash
yq '.roles[].modalities.codex.model'    "${CLAUDE_PLUGIN_ROOT}/bindings/presets.yaml" | sort -u
yq '.roles[].modalities.opencode.model' "${CLAUDE_PLUGIN_ROOT}/bindings/presets.yaml" | sort -u
```

## Step 2 — codex: auth + live probe

Binary and auth state:

```bash
codex login status || true    # or: ls ~/.codex/auth.json
```

Live probe (mirrors relay's real one-shot dispatch shape — `--agent` override, plain
model id, effort via the `CODEX_CONFIG` adapter env):

```bash
CODEX_CONFIG='{"model_reasoning_effort":"low"}' \
acpx --cwd /tmp --agent "npx -y @agentclientprotocol/codex-acp@latest" \
  --model "<codex model from Step 1>" --approve-all --timeout 180 \
  exec "Reply with exactly: OK"
```

Audit what actually served — codex records model AND effort per turn in its rollout:

```bash
F=$(ls -t ~/.codex/sessions/*/*/*/rollout-*.jsonl | head -1)
grep -o '"model": "[^"]*"' "$F" | head -1
grep -o '"effort": "[^"]*"' "$F" | head -1
```

Both must match the probe's requested model and effort. `effort` still at its default
means the CODEX_CONFIG env did not reach the adapter.

Remediation: `codex login` (interactive); model not advertised → check the plan tier in
`~/.codex/models_cache.json` (`supported_in_api` flags).

## Step 3 — opencode: auth + live probe

Provider credentials (opencode routes a model to a provider by the model-id **prefix**,
e.g. `opencode-go/kimi-k2.6` can only bill to the `opencode-go` provider):

```bash
jq -r 'keys[]' ~/.local/share/opencode/auth.json   # must list every provider prefix from Step 1
opencode models | grep -F "<opencode model from Step 1>"
```

Live probe (mirrors relay's opencode-session-driver flow: ensure → set model → prompt
→ close; the model binds at the session's FIRST prompt — a later `set model` on a live
session reports success but does NOT switch the serving model, so always probe with a
fresh session):

```bash
S=relay-engine-probe
acpx --cwd /tmp opencode sessions ensure --name "$S"
acpx --cwd /tmp opencode set model "<opencode model from Step 1>" -s "$S"
acpx --cwd /tmp --timeout 180 opencode prompt -s "$S" "Reply with exactly: OK"
acpx --cwd /tmp opencode sessions close "$S"
```

Audit what actually served — opencode records provider + model per message in its
sqlite store:

```bash
sqlite3 ~/.local/share/opencode/opencode.db \
  "SELECT json_extract(data,'\$.providerID'), json_extract(data,'\$.modelID')
   FROM message WHERE json_extract(data,'\$.role')='assistant'
   ORDER BY json_extract(data,'\$.time.created') DESC LIMIT 1;"
```

The row must equal the pinned `provider|model` exactly.

Remediation by error:

| Error | Fix |
|---|---|
| `Invalid API key` | Re-connect the provider: `opencode auth login` (interactive), pick the failing provider — a key minted before a subscription activates is invalid |
| `Insufficient balance` | Model went to a pay-per-token provider (e.g. `opencode/...` Zen) instead of the subscription provider — fix the model-id prefix, or top up |
| `Cannot apply --model ... did not advertise model support` | acpx too old — Step 0 |
| `effort not found` on `set effort` | Expected for open-weight models: they define no acpx effort values; relay's driver soft-degrades and the session runs at the model's default reasoning |

## Step 4 — dry-run relay's own dispatch (optional but recommended)

Confirm relay resolves the same binding end to end without spending tokens:

```bash
ACPX_ROLE_SLUG=code-reviewer ACPX_BINDING_PRESET=code-reviewer \
ACPX_INPUTS_JSON='{}' ACPX_RUN_ID=engine-setup-dryrun ACPX_DRY_RUN=1 \
bash "${CLAUDE_PLUGIN_ROOT}/skills/dispatching-acpx-agents/acpx-dispatch.sh"
```

## Step 5 — readiness report

Emit one table: engine · binary version · auth state · probed model · served
provider/model (from the engine's own records) · verdict. An engine is READY only when
the audit row matches the pinned model; everything else is NOT READY with its
remediation from above.
