---
name: refining-prs
description: Use when a PR branch needs automated iterative refinement before merge — stabilizes code through multi-agent review cycles with adversarial validation, test verification, and targeted fixes until the reviewer finds no critical or important issues. Thin shim over relay:refining with the pr adapter.
user-invocable: false
---

# Refining PRs

> BETA (REFINE-4). Proven live in PR #43 and PR #44. Two v1 degeneracies remain; the canonical
> caveat lives in `skills/refining/adapters/pr.md`.

Thin shim over the generic `relay:refining` loop, configured for the pr target.

Core principle: separate evaluation from generation, challenge every finding before acting on
it, and use objective test signals alongside subjective code review. Never let the fixer judge
its own work.

Announce at start: "I'm using the refining-prs skill to iteratively refine this PR through
adversarial review cycles."

## What to do

Invoke `relay:refining` via the Skill tool with adapter slug `pr` and the inline config below.
This shim restates only the invariants it overrides (`aggregator`, the fixer's post-fix action,
`convergence_predicate`, `persistence_marker`). `max_rounds` is inherited (5).

```yaml
# The Workflow supplies resolved literals, for example engine: acpx / agent: opencode.
# If the fields are absent, relay:refining uses in-session / claude.
engine: ${RELAY_ENGINE}
agent: ${RELAY_AGENT}
subject: pull request (git branch + base ref)
subject_adapter: adapters/pr.md
critics:
  - role: agents/code-reviewer              # kept registered agent — pr-reviewer archetype (model hint: opus)
    leaf: relay:code-reviewer
    model: opus
  - role: agents/code-reviewer              # kept registered agent — pr-validator stance
    leaf: relay:code-reviewer
    model: opus                             # 4.14.0: binding wins — code-reviewer's flat tier is opus
    debate_enabled: true                    # validator challenges the reviewer's findings
  - role: roles/server-runner.md            # reader role → dispatched via relay:leaf-reader (live-server only)
    leaf: relay:leaf-reader
    model: haiku
  - role: roles/doc-reference-reviewer.md  # reader role → dispatched via relay:leaf-reader; no archetype mapping
    leaf: relay:leaf-reader
    model: opus                            # 4.46.0: binding wins — category verification, flat tier is opus
aggregator: debate-confirm         # OVERRIDE of default `none` — only validator-survived findings advance
fixer:
  role: roles/fix-coder.md         # writer role → dispatched via relay:leaf-worker
  leaf: relay:leaf-worker
  model: sonnet
  post: verify-tests + revert-on-fail   # OVERRIDE of default post `re-read`
convergence_predicate: "no confirmed findings after debate AND tests pass → CONVERGED"  # OVERRIDE — extends default with a tests-pass condition
persistence_marker: git checkpoint commits (`refine(cycle-N): ...`)   # OVERRIDE of default inline marker
```

## PR-target role mapping

The config names abstract `pr-*` archetypes. `agents/code-reviewer` handles `pr-reviewer` and
`pr-validator`; the second instance gets a VALIDATOR-STANCE prefix — "challenge the reviewer's
findings; argue why each is wrong or low-priority". `roles/server-runner.md`
(`relay:leaf-reader`) is live-server only, not a test runner; `verify-tests` runs via
`roles/fix-coder.md` (`relay:leaf-worker`). The authoritative archetype → agent/role mapping
lives in `skills/refining/adapters/pr.md`.

Model-hint precedence: the `model:` values above mirror `bindings/presets.yaml` (resolved by
`scripts/resolve-tier.sh`); where they differ, the binding wins.
