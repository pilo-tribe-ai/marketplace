# Relay Language Reference

Internal vocabulary for relay's layered Workflow DSL (design: `docs/superpowers/specs/2026-06-04-relay-layered-workflow-dsl-design.md`). **L0 keywords** and **L1 patterns** are model-internal — the language Claude composes a dynamic Workflow in; they are never a surface a user types (DSL design §2.1–§2.2). This file is the durable artifact and the unit of vocabulary evolution. Changes are PR-gated (§10).

## Authoring Guidelines

These govern how entries below are written so the same English reliably generates the same Workflow structure (DSL design §7):

1. Define the target as a JSON schema, not prose — constrained decoding is the only documented guarantee of a repeatable shape.
2. Exploit Opus literalism + lower effort for predictable pipelines; state scope explicitly ("every stage, not just the first").
3. Use XML tags as the structure primitive; 3–5 diverse `<example>`-wrapped few-shots as a format-lock when no schema is available.
4. Match prompt style to output style (markdown-in → markdown-out).
5. Verb mood selects mode: imperative → implementation; interrogative/hedged → advisory prose.
6. Calm plain imperatives, not emphatic caps ("Use this when…", not "CRITICAL: You MUST").
7. Frame positively; describe the exact target form rather than prohibiting wrong forms.
8. Avoid the reserved token "think" when thinking is disabled (use "consider" / "evaluate" / "reason through").
9. Explain the "why" (e.g. isolated runtime, no fs → delegate all disk I/O to leaves) so the model generalizes the constraint.
10. Anchor with a one-sentence role + numbered steps to enforce order and reduce cross-run variance.

## L0 — Keyword Glossary

| name | category | definition |
|---|---|---|
| sequence | control-flow | Run steps in a fixed order, each starting after the previous completes. |
| for-each | control-flow | Iterate a body once over each item in a collection. |
| loop-until | control-flow | The single canonical bounded-iteration primitive; re-runs and re-classifies work each pass until a clean predicate or bound is hit. |
| parallel | control-flow | Dispatch independent branches concurrently and join on all completions. |
| branch | control-flow | Select exactly one continuation based on a tested condition. |
| abort | control-flow | Terminate the workflow immediately with a failure/stop status. |
| skip | control-flow | Bypass a step or unit, recording it as intentionally not executed. |
| park | control-flow | Suspend at a resumable pause (status:waiting) and await external resume/input; distinct from abort and engine-managed resume. Workflow-graph control flow only — not reachable from a leaf/agent node, which has exactly one turn and no resumable pause; a leaf that would park must emit a typed failure instead. |
| cap | bounds | A hard integer ceiling on iterations or attempts before forced exit. |
| budget | bounds | A shared consumable allowance (e.g. attempt/token pool) spent across steps until exhausted. |
| role | actors | A named unit of delegated work with a declared mandate and requires/provides. |
| mechanism-resolve | actors | Resolve which dispatch mechanism a role uses via a layered precedence stack (CLI flag > binding > presets > frontmatter) before the mode-blind delegate. |
| capability-validate | actors | Check a role's declared requires against the tool set of the leaf its role-class derives, and reject the dispatch before execution on any miss. |
| delegate | actors | Mode-blind dispatch of a role to its pre-resolved mechanism leaf. |
| session-grounding | actors | The grounding posture of a delegated actor: WARM (reused handle accumulating context) vs ISOLATED (fresh session per dispatch). |
| leaf-constraint | actors | The tool allowlist, isolation mode, and permission tier of a dispatched leaf (allowedTools, disallowedTools, network flags). |
| compute | work | A deterministic in-script transformation over data, with no delegation. |
| classify | work | Map an input to exactly one member of a closed label set. |
| join-by-key | work | Merge external results into seeded units by a shared key. |
| typed-output | work | An actor returns a typed, schema-validated object consumed as data with zero file I/O — the primary value-extraction channel. Schema-at-the-seam: apply the schema at the Workflow-script query seam, not on the Agent-tool return; L1 patterns that need typed output reference this entry rather than repeating the pattern. |
| freshness-verify | work | A two-predicate disk-identity gate (mtime bump AND content-hash change) before a folding role's DONE is trusted. |
| produce | state | Write a new durable artifact (file or typed value) as a step's output. |
| read | state | Load an existing artifact as input to a step. |
| checkpoint | state | Persist completed-work state to durable storage for resume. |
| marker | state | A small durable signal recording status or progress for later detection. |
| mutate-in-place | state | Apply a targeted edit to an existing artifact rather than rewriting it. |
| done-criterion | bounds | The single binary, checkable terminal condition a run is driven to; PASS/FAIL with no judgement call. |
| clean-streak | bounds | A required count of consecutive clean full-run passes (N=2 default) proving stability, not just reachability; any fix resets it to 0. |
| circuit-breaker | bounds | A per-step fix-cycle cap; on the cap the step is written to a blocked register with a fallback and the loop continues rather than stopping. |
| oracle | state | The durable artifact defining the steps, each step's pass condition, and the binary done criterion; reconciled to reality at closeout. |
| fresh-seed-reset | state | A single recorded reset command that returns the run to a known-clean seed, with the prior run's mutations queried-as-gone rather than assumed. |
| evidence-before-assertion | work | Mark a step PASS only when backed by real output actually seen; never fake, mock, or stub to make the done criterion pass. |
| closeout | state | The done criterion's tail: reconcile the oracle to reality, write the operator-facing summary, true up blockers, and commit the durable artifacts. |

## L1 — Pattern Library

| name | shape | l0-deps | when-to-use | acpx-leg-required | example |
|---|---|---|---|---|---|
| pipeline | Ordered stages, each reading predecessor artifacts and producing its own, with a validating entry guard and resume-from-any-boundary. | sequence, produce, read, checkpoint, marker | Use when work is a fixed ordered set of stages, each consuming the prior stage's artifact, needing resume-from-boundary. | false | spec → plan → implement → verify |
| loop-until-clean | Bounded improvement loop: re-dispatch a body of roles, then classify the critic verdict into a closed three-label set — clean exits, findings iterates, no-answer is a dispatch failure and never a pass; collapses converge + bounded-retry + shared-budget-cycle. | loop-until, classify, cap, budget, branch | Use when a body must repeat until a quality predicate is met or a cap/budget is exhausted. | false | spec-refine critic↔fixer until CONVERGED |
| multi-turn-dispatch | Within-role driver: delegate one actor with a WARM session-grounding posture, then re-dispatch that same actor across turns until its own terminal envelope. | delegate, session-grounding, loop-until, marker | Use when one actor must be driven across multiple turns while maintaining a warm accumulated context. | true | drive a long-running implementer turn-by-turn |
| router-loop | Bounded alternating-actor loop: each iteration re-dispatches a WARM actor and freshly-dispatches an ISOLATED decider whose typed verdict drives a branch back or forward. | loop-until, delegate, session-grounding, branch, typed-output, classify | Use when a warm worker and an isolated decider must alternate, the decider routing continue/exit each round. | true | brainstorm ↔ grounded decide |
| fan-out-aggregate | For-each independent actor in parallel, sync on all completions, merge typed outputs. | for-each, parallel, delegate, join-by-key, typed-output | Use when N independent units can run concurrently and their typed outputs are merged. | false | parallel scouts over subsystems |
| quorum-decide | Fan-out of fixed mandated roles (isolated); a neutral synthesizer detects majority; a split escalates once to a moderator. | parallel, delegate, role, typed-output, branch | Use when a decision needs multiple fixed independent perspectives with majority detection and one escalation. | false | three-panelist design decision |
| gate | Test a condition and select one continuation: proceed, skip, abort, or park. The single branching shape. | branch, classify, skip, abort, park | Use when control must fork to exactly one of proceed/skip/abort/park on a tested condition. | false | server-ready? proceed else abort |
| delegate-and-verify | Resolve mechanism, capability-validate, run leaf, capture typed output/markers, freshness-verify folding roles, bounded re-dispatch retry. | mechanism-resolve, capability-validate, delegate, leaf-constraint, typed-output, marker, freshness-verify, loop-until | Use whenever a single role is dispatched and its result must be validated before trust. | false | dispatch implementer, verify diff freshness |
| resume-from-checkpoint | On entry, detect completed work from durable on-disk state and skip redundant re-execution. | read, checkpoint, marker, skip | Use at the entry of any resumable pipeline to skip already-completed units. | false | skip phases with a CONVERGED marker |
| normalize-and-rollup | Seed all units to a default status, join external results by key, apply a closed-form rollup to one terminal verdict. Single deterministic pass. | produce, join-by-key, compute, mutate-in-place | Use when many unit results must fold deterministically into one verdict. | false | roll scenario results into pass/fail |
| drive-to-done | Autonomous, oracle-gated run-to-done loop: orient → delegate one step to a leaf → verify the pass condition from real evidence → branch (PASS: log + advance · FAIL: diagnose + fix, capped, then re-prove from step 0) → record, until consecutive clean runs meet the done criterion; circuit breaker on a step's cap continues; ends in closeout. | oracle, done-criterion, clean-streak, fresh-seed-reset, circuit-breaker, evidence-before-assertion, closeout, loop-until, classify, cap, checkpoint, delegate, typed-output | Use when a long-running, multi-step process must be driven autonomously to a verifiable done criterion without a human in the loop, surviving /compact and worktree loss. | false | drive an oracle to its done criterion over hours |
