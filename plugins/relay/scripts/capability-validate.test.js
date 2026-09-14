const { test } = require("node:test");
const assert = require("node:assert");
const {
  validate,
  validateRoleAgainstTools,
  CAPABILITY_TOOLS,
} = require("./capability-validate.js");

// --- generic primitive -----------------------------------------------------

test("validate: match → ok:true, empty missing", () => {
  const r = validate(["a", "b"], ["a", "b", "c"]);
  assert.strictEqual(r.ok, true);
  assert.deepStrictEqual(r.missing, []);
});

test("validate: miss → ok:false, lists only the absent caps in order", () => {
  const r = validate(["a", "x", "y"], ["a", "b"]);
  assert.strictEqual(r.ok, false);
  assert.deepStrictEqual(r.missing, ["x", "y"]);
});

test("validate: empty requires → ok:true (nothing to satisfy)", () => {
  assert.deepStrictEqual(validate([], ["a"]), { ok: true, missing: [] });
});

// --- the role-dispatch gate ------------------------------------------------
//
// These use the REAL namespaces. The pre-4.20.0 tests asserted set-difference over
// abstract "a"/"b" strings, which is why pairing `requires` against `provides` — two
// disjoint namespaces — passed unnoticed.

const WORKER_TOOLS = ["Read", "Write", "Edit", "Bash", "Grep", "Glob"];
const READER_TOOLS = ["Read", "Grep", "Glob", "Bash"];

test("writer leaf satisfies every declared capability", () => {
  const r = validateRoleAgainstTools(
    ["read_files", "run_bash", "write_files"],
    WORKER_TOOLS,
  );
  assert.deepStrictEqual(r, { ok: true, missing: [], unknown: [] });
});

test("reader leaf satisfies read_files and run_bash", () => {
  const r = validateRoleAgainstTools(["read_files", "run_bash"], READER_TOOLS);
  assert.strictEqual(r.ok, true);
});

test("write_files on a reader leaf is the mismatch this gate exists for", () => {
  const r = validateRoleAgainstTools(["read_files", "write_files"], READER_TOOLS);
  assert.strictEqual(r.ok, false);
  assert.deepStrictEqual(r.missing, ["write_files"]);
});

test("write_files needs BOTH Write and Edit — Write alone is not enough", () => {
  const r = validateRoleAgainstTools(["write_files"], ["Read", "Write", "Bash"]);
  assert.strictEqual(r.ok, false);
  assert.deepStrictEqual(r.missing, ["write_files"]);
});

test("an unmapped capability fails rather than passing silently", () => {
  const r = validateRoleAgainstTools(["read_files", "wrte_files"], WORKER_TOOLS);
  assert.strictEqual(r.ok, false, "a typo in requires: must not satisfy the gate");
  assert.deepStrictEqual(r.unknown, ["wrte_files"]);
  assert.deepStrictEqual(r.missing, []);
});

test("regression: requires vs provides is a namespace error, not a capability check", () => {
  // The documented-but-never-executed pairing. Every capability reads as missing
  // because envelope tokens live in a different namespace entirely — which is what
  // would have rejected 100% of dispatches had anything run it.
  const provides = ["ROLE_DONE", "FILES_TOUCHED"];
  const r = validate(["read_files", "run_bash", "write_files"], provides);
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.missing.length, 3);
});

test("capability map covers exactly the namespaces roles declare", () => {
  assert.deepStrictEqual(
    Object.keys(CAPABILITY_TOOLS).sort(),
    ["read_files", "run_bash", "write_files"],
  );
});
