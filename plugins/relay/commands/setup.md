---
description: "Provision this machine for relay: acpx preflight, engine-aware superpowers dependency check, and codex skill provisioning. Run once on a fresh machine before /relay:implement with the acpx engine or a codex agent."
disable-model-invocation: true
argument-hint: "[engine] [agent]"
allowed-tools: Bash, Skill
---

## Step 0 — Argument parsing

`/relay:setup` PROVISIONS dependencies, so it must NOT gate on them — gating would abort before
it could fix anything. Source only the argument validator to learn which engine/agent to
provision for:

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/parse-engine-agent.sh" "$@" || exit 1
```

The parser takes **all** positionals (`"$@"`) so it can reject extras: it validates
`engine`/`agent`, applies defaults, enforces the `in-session ⇒ claude` invariant, and exports
`RELAY_ENGINE`/`RELAY_AGENT`. No spec-path is accepted; any 3rd positional is rejected.

## Step 1 — Invoke the setup coordinator

Invoke the `relay:setting-up-relay` Skill, passing `$RELAY_ENGINE` / `$RELAY_AGENT`. It runs the
acpx preflight, the engine-aware dependency check
(`check-deps.sh --agent $RELAY_AGENT --format json`), and codex skill provisioning, then prints a
readiness report.
