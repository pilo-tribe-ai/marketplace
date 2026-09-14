# Refinement Contract

Every refining skill in relay — generic `refining/` and target-specific shims (`refining-specs`, `refining-plans`, `refining-prs`) — must implement and declare the following contract.

## The contract fields and the generic loop

Operative copy: see `skills/refining/SKILL.md`. The 7-field contract table and the generic loop algorithm are maintained there and consulted every refinement round — this doc no longer re-prints them.

## Per-target instantiation (v1)

### refining-specs

```yaml
subject: spec document (markdown)
subject_adapter: adapters/spec.md
critics:
  - role: roles/spec-simulator.md      # via relay:leaf-reader (role-class: reader)
    model: claude
aggregator: none
fixer:
  role: roles/spec-fixer.md            # via relay:leaf-worker (role-class: writer)
  post: re-read
convergence_predicate: "no critical/important findings → CONVERGED"
max_rounds: 5
persistence_marker: sidecar findings file + inline `[inferred]` tags
```

### refining-plans

```yaml
subject: plan document (markdown)
subject_adapter: adapters/plan.md
critics:
  - role: roles/plan-simulator.md      # via relay:leaf-reader (role-class: reader)
    model: claude
aggregator: none
fixer:
  role: roles/plan-fixer.md            # via relay:leaf-worker (role-class: writer)
  post: re-read
convergence_predicate: "no critical/important findings → CONVERGED"
max_rounds: 5
persistence_marker: sidecar findings file + inline `[inferred]` tags
```

### refining-prs

```yaml
subject: pull request (git branch + base ref)
subject_adapter: adapters/pr.md
critics:
  - role: relay:pr-reviewer            # abstract archetype → agents/code-reviewer (registered)
    model: opus
  - role: relay:pr-validator           # abstract archetype → agents/code-reviewer (registered)
    model: sonnet
    debate_enabled: true              # validator challenges reviewer findings
  - role: relay:pr-runner             # abstract archetype → roles/server-runner.md via relay:leaf-reader
    model: haiku                      # baseline test run
aggregator: debate-confirm            # only validator-survived findings advance
fixer:
  role: relay:pr-fixer                 # abstract archetype → roles/fix-coder.md via relay:leaf-worker
  model: sonnet
  post: verify-tests + revert-on-fail
convergence_predicate: "no confirmed findings after debate AND tests pass → CONVERGED"
max_rounds: 5
persistence_marker: git checkpoint commits (`refine(cycle-N): ...`)
```

#### Landing verify (pr adapter)

The landing-verify step runs between `fixer.apply` and `adapter.post_fix` in every pr-adapter
fixing round. When edits are present (`git status --short` non-empty after `fixer.apply`),
the loop commits with `refine(cycle-N): landing-verify` before calling `adapter.post_fix`.
`persist()` detects the already-clean tree and skips its own commit (clean-tree check, not
message parsing). `recover()` treats `refine(cycle-N): landing-verify` commits as round-N
complete, which is correct behavior. See `skills/refining/SKILL.md` §Landing Verify Contract
and `skills/refining/adapters/pr.md` §Landing Contract Integration for full details.

#### PR-target agent mapping (v1)

The `pr-reviewer` / `pr-validator` / `pr-runner` / `pr-fixer` slugs above are abstract
**role archetypes** that resolve per the §5 role resolution order:
- `pr-runner` → `roles/server-runner.md` via `relay:leaf-reader`
- `pr-fixer` → `roles/fix-coder.md` via `relay:leaf-worker`
- `pr-reviewer` / `pr-validator` → `agents/code-reviewer` (kept registered, `relay:code-reviewer`)

Additionally, `roles/doc-reference-reviewer.md` (`relay:leaf-reader`) is wired as a PR critic.
See `skills/refining/adapters/pr.md` for the full pr-archetype→role/agent mapping and the
v1-degeneracy caveat.

## Adapter interface

Each `skills/refining/adapters/<target>.md` declares:

```
load()              → returns subject snapshot
snapshot(subject)   → returns opaque pre-state for diffing
diff(snapshot, current) → returns structured diff for reporting
post_fix(action)    → executes post-fix action; one of:
                      - re-read           (specs, plans)
                      - verify-tests      (PRs, code)
                      - revert-on-fail    (PRs, code)
persist(round, findings, marker)  → writes resume state
recover()           → reads resume state, returns last completed round
```

## convergence_mode extension (v1.4.0)

The engine gains an optional `convergence_mode` field (not required — absent from the 7-field
contract set). When unset, defaults to `binary`; the spec/plan/pr shims inherit `binary` by
absence and their behaviour is unchanged.

| Value | Semantics |
|---|---|
| `binary` | Default. Convergence when `convergence_predicate(findings)` is true or `not critical_or_important(findings)`. Existing spec/plan/pr behaviour. |
| `scored` | Convergence when all critic dimensions score at or above their threshold (threshold-AND). Uses a `scored` aggregator with two named operations: `merge_scores` (dimension → latest score) and `cap` (sort by severity, keep all criticals, fill up to `max_findings_per_cycle`). Plateau detection drives a `pivot` fixer mode when progress stalls. |

The `scored` aggregator replaces the single-callable aggregator for `convergence_mode: scored`
only. Binary shims continue to call `aggregator(findings)` as before.

### refining-ui

```yaml
subject: live website (rendered + source tree)
subject_adapter: adapters/ui.md
convergence_mode: scored
scored:
  dimensions:
    design_quality: 7
    originality: 7
    craft: 7
    functionality: 7
    accessibility: 7
  max_findings_per_cycle: 5
  plateau_window: 3
  plateau_epsilon: 0.5
max_rounds: 10
aggregator: scored   # merge_scores + cap (see convergence_mode extension above)
critics:
  # browser-free; runs in parallel with the browser critics
  - role: roles/ui-code-evaluator.md          # via relay:leaf-reader (role-class: reader)
    model: sonnet  parallel: true
  # browser critics share one Playwright instance — run sequentially
  - role: roles/ui-visual-evaluator.md        # via relay:leaf-reader
    model: sonnet  parallel: false
  - role: roles/ui-ux-evaluator.md            # via relay:leaf-reader
    model: sonnet  parallel: false
  - role: roles/ui-accessibility-evaluator.md # via relay:leaf-reader
    model: sonnet  parallel: false
fixer:
  role: roles/ui-generator.md                 # via relay:leaf-worker (role-class: writer)
  post: re-read
persistence_marker: git score-commits (`refine(ui): round N key=val ...`) + sidecar .relay/ui-refine-findings.json
```

## Future targets (v2 — NOT generic-loop extensions)

These get their own skills with their own adapters, NOT new configs against `refining/`:

| Target | Why standalone | What it shares |
|---|---|---|
| `refining-code` | AST-aware diff/patch; convergence is metric-improvement, not gap-closure | May share `loop-with-convergence` sub-primitive after extraction |
| `refining-architecture` | ADR + dep-graph cross-ref; convergence is policy validation | Same |

After v2 has 2+ of these working, evaluate extracting `skills/loop-with-convergence/` as a thinner sub-primitive than `refining/`.
