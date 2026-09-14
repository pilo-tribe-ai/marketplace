"use strict";
// Capability gate for role dispatch (DSL design §6.4, §10).
//
// A role declares `requires:` in a capability namespace — read_files, run_bash,
// write_files. What satisfies a capability is the TOOL SET of the agent the role is
// dispatched into: `role-class: writer` derives relay:leaf-worker (Read/Write/Edit/
// Bash/Grep/Glob), `role-class: reader` derives relay:leaf-reader (Read/Grep/Glob/
// Bash). A role requiring `write_files` bound to a reader is the mismatch worth
// catching — the leaf has no Write or Edit tool, so the dispatch cannot succeed.
//
// 4.20.0 — what this used to be, and why it never fired:
//
// delegate-leaf/SKILL.md documented `validate(roleRequires, bindingProvides)`,
// pairing `requires:` against the binding's `provides:`. Those are DISJOINT
// namespaces: `requires` holds capabilities (read_files), `provides` holds envelope
// tokens (ROLE_DONE, FILES_TOUCHED). Their set difference is therefore the whole of
// `requires` on every role, so a coordinator that actually ran the documented check
// would have rejected 100% of dispatches. It never fired because nothing called it —
// this file had no runtime caller anywhere in the tree, and acpx-dispatch.sh's own
// intersection is correctly gated off for role files, with a comment explaining this
// exact namespace distinction.
//
// The unit test hid it too: it asserted set-difference behaviour over abstract "a"/
// "b" strings, so it passed while saying nothing about whether the pairing was
// meaningful.
//
// The fix is to check the pairing that matters and to enforce it statically over
// every role at commit time (tests/unit/skill-structure/test_capability_gate.py),
// rather than as prose a dispatching coordinator may or may not act on.

/** Tools that must ALL be present for a capability to be satisfied. */
const CAPABILITY_TOOLS = {
  read_files: ["Read"],
  run_bash: ["Bash"],
  write_files: ["Write", "Edit"],
};

/**
 * Generic set-difference primitive. Correct in itself, and kept because callers
 * comparing two lists in the SAME namespace still want it — but note that
 * `requires` and `provides` are not the same namespace. Prefer
 * validateRoleAgainstTools for the role-dispatch gate.
 */
function validate(required, provided) {
  const have = new Set(provided || []);
  const missing = (required || []).filter((cap) => !have.has(cap));
  return { ok: missing.length === 0, missing };
}

/**
 * The role-dispatch gate. Returns { ok, missing, unknown } where `missing` lists
 * capabilities the tool set cannot satisfy, in roleRequires order, and `unknown`
 * lists declared capabilities with no mapping — treated as a failure rather than
 * silently satisfied, so a typo in `requires:` cannot pass the gate.
 */
function validateRoleAgainstTools(roleRequires, agentTools) {
  const tools = new Set(agentTools || []);
  const missing = [];
  const unknown = [];
  for (const cap of roleRequires || []) {
    const needed = CAPABILITY_TOOLS[cap];
    if (!needed) {
      unknown.push(cap);
      continue;
    }
    if (!needed.every((t) => tools.has(t))) missing.push(cap);
  }
  return { ok: missing.length === 0 && unknown.length === 0, missing, unknown };
}

module.exports = { validate, validateRoleAgainstTools, CAPABILITY_TOOLS };
