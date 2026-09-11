---
name: delegate-leaf
description: Use to dispatch one resolved leaf role and verify its result before trusting it — resolve the role's mechanism, run a capability-validate pre-step that rejects the dispatch when the binding lacks a required capability, run the leaf, capture its typed output and markers, freshness-verify any folding roles, and bounded-retry the dispatch on a recoverable miss.
user-invocable: false
---

# delegate-leaf

delegate-leaf dispatches one resolved leaf role and verifies its result before trust.

## Steps

This skill realizes the `delegate-and-verify` L1 shape. Drive it as follows:

1. **Resolve the mechanism.** `mechanism-resolve` the leaf role against its binding —
   determine which engine and surface the role runs on and the capabilities that binding
   provides.
2. **Capability-validate (pre-step).** Before dispatching, check the role's `requires:` list
   against the derived leaf's fixed tool set (or the registered agent's tool set for kept agents).
   A role with `requires: [write_files]` may not bind to `role-class: reader` (the `relay:leaf-reader`
   leaf has no Write/Edit tools). When a mismatch is detected, reject the dispatch with a typed
   `CAPABILITY_MISMATCH` error — do not run the leaf. The
   `${CLAUDE_PLUGIN_ROOT}/scripts/capability-validate.js` helper implements exactly this check:
   `validateRoleAgainstTools(roleRequires, agentTools) -> { ok, missing, unknown }`. Pass the
   role's `requires:` and the tool list from the derived agent's frontmatter. When `ok` is
   `false`, reject and report — `missing` lists capabilities the tool set cannot satisfy,
   `unknown` lists declared capabilities with no mapping (a typo in `requires:` fails the gate
   rather than passing silently).

   > **Do not pair `requires:` against the binding's `provides:`.** They are disjoint
   > namespaces — `requires` holds capabilities (`read_files`), `provides` holds envelope
   > tokens (`ROLE_DONE`, `FILES_TOUCHED`) — so their set difference is the whole of
   > `requires` for every role, and the check would reject every dispatch. This skill
   > documented that pairing until 4.20.0; it never fired only because nothing called the
   > helper. `acpx-dispatch.sh` skips its own intersection for role files for the same
   > reason, with a comment saying so.

   The gate is also enforced statically over every role by
   `tests/unit/skill-structure/test_capability_gate.py`, so a mismatch fails the suite before
   it can be dispatched. That matters because this step is prose a coordinator may skip;
   the static check cannot be.
3. **Run the leaf.** With `ok` true, `delegate` to the single leaf `role` under its
   `leaf-constraint` — the leaf does its own work and may not itself dispatch.
4. **Capture typed output and markers.** Read the leaf's `typed-output` and any `marker`
   tokens it emitted; these are the evidence the result is trustworthy.

   **Writer-role landing-verify (mandatory sub-step for `role-class: writer` dispatches):**
   After parsing the output, run the landing-verify from `docs/dispatch-contract.md` (Writer-Role
   Landing Contract) in the absolute path passed to the fixer as `{{WORKTREE_PATH}}`. Markers
   unique to this skill: on a failure record `landing_verify_failed` and do not proceed to
   Step 5; on a legitimate no-change proceed to Step 5 with `landing_no_change=true`.
5. **Freshness-verify folding roles.** For a folding role whose output is read back into the
   parent, `freshness-verify` that the captured output came from this dispatch — not a stale
   prior run — before folding it in.
6. **Bounded re-dispatch retry.** On a recoverable miss (empty or malformed `typed-output`,
   a failed freshness check), `loop-until` a clean capture within the §4.3 retry bound, then
   re-dispatch. When the bound is spent without a clean result, surface a structured failure
   rather than trusting the leaf.

Calm imperatives only. Describe the target form; the leaf does the work.

## Vocabulary

```relay-vocab
l1-shape: delegate-and-verify
l0-deps: mechanism-resolve, capability-validate, delegate, leaf-constraint, typed-output, marker, freshness-verify, loop-until
acpx-leg-required: false
```
