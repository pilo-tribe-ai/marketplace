---
name: setting-up-relay
description: Use to provision a machine for relay before running /relay:implement with the acpx engine or a codex agent — checks the acpx CLI version + flow subcommand, runs the engine-aware superpowers dependency check, and provisions missing codex skills. Interactive; run via /relay:setup.
user-invocable: false
---

# setting-up-relay

Interactive provisioning coordinator. It makes the acpx flow (Workstream C) and the engine-aware
dependency check (Workstream D) runnable on a fresh machine. Runs only on the claude orchestrator;
only leaf skills are provisioned into codex. This is a skill + command, no agents — see
`docs/agent-roster.md` for the agent-roster inventory.

## Inputs

- `RELAY_ENGINE`, `RELAY_AGENT` — exported by `parse-engine-agent.sh` (the `/relay:setup` command
  sources it). They select which dependency sets to check and provision.

## Step 0.1 — acpx preflight

Assert the `acpx` CLI is on PATH, its version meets the floor, and the `flow`
subcommand is present. `scripts/acpx-floor.sh` holds the floor number and the
rationale; never restate the number here:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/acpx-floor.sh"   # prints RELAY_ACPX_VERSION=<v>, or fails
acpx flow --help >/dev/null 2>&1                     # must exit 0
```

On the claude engine, also assert the `dispatching-acpx-agents` relay skill is installed (relay's
acpx dispatch depends on it). When the floor script fails it already prints the remediation
(`npm install -g acpx@latest`) — show that line and stop.

## Step 1 — Engine-aware dependency check

Run the dependency prober in executed mode, passing `RELAY_AGENT` so it derives the probe set
(CLAUDE set when agent ∈ {claude, hybrid, opencode}; CODEX set when agent ∈ {codex, hybrid};
hybrid checks both):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-deps.sh" --agent "$RELAY_AGENT" --format json
```

Parse the per-set matrix `{"<set>":{"<skill>":"ok"|"missing"}}` (a hybrid run emits both a
`claude` and a `codex` block) and drive **per-skill** interactive remediation — install exactly
what is `missing`, not an all-or-nothing abort. A missing claude-side install points the user at
`/plugin install superpowers`.

## Step 2 — Codex skill provisioning (agent = codex or hybrid)

Install the upstream skills listed in `scripts/upstream-superpowers-skills.txt` (the closed
obra/superpowers set plus `engineering`) into `~/.codex/skills/<name>/`.

**Primary path (agentic).** Hand each `(repo, subpath)` row from the manifest to `acpx codex exec`,
instructing it to fetch that repo's `<subpath>/SKILL.md` (plus supporting files) into
`~/.codex/skills/<name>/` and echo a per-skill done marker. Confirm success by re-probing
`~/.codex/skills/<name>/SKILL.md` (the check the dependency prober uses); absence after the exec
returns means failure.

**Fallback** (a skill still missing after the exec, or codex lacks a skill-installer). For each
still-missing row, print the exact hand-run invocation:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/install-skill-from-github.py" <repo> <subpath> --dest ~/.codex/skills
```

`install-skill-from-github.py` needs `python3` + `git` on PATH + network egress (public repos only,
no auth). If `git` or network is unavailable, print a clear error and the manual steps rather than
failing silently.

The claude engine provisions via the marketplace, so no codex copy is needed there.

## Output

A readiness report: acpx version, per-set dependency matrix, and each skill's provisioning result
(already-present / installed / still-missing-with-instructions).
