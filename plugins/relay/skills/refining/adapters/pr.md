# Adapter: pr

Subject I/O for `relay:refining` when the subject is a **pull request (git branch + base
ref)**. Unlike the spec/plan adapters (which patch a markdown file in place), this adapter
operates on a git working tree and persists via checkpoint commits. The generic loop in
`skills/refining/SKILL.md` calls the verbs below.

## Interface

### `load()`
Resolve the PR's **git branch + base ref**. The subject snapshot is the diff of branch HEAD
against the base ref (changed files + their contents).

### `snapshot(subject)`
Return the **base SHA** (and current HEAD SHA) as the opaque pre-state — what the loop diffs
against and what `revert-on-fail` restores to.

### `diff(snapshot, current)`
Return the structured git diff between the snapshot's SHA and the current HEAD, for the round
report.

### `post_fix(action)`
The PR post-fix action is **`verify-tests + revert-on-fail`**: after `pr-fixer` patches the
working tree, run the project's test command (`verify-tests`). If tests pass, keep the change;
if they fail, **`revert-on-fail`** — reset to the last good SHA and record the failure as a
finding for the next round.

### `persist(round, findings, marker)`
Write resume state as **git checkpoint commits**: after a passing fixing round, create a
checkpoint commit `refine(cycle-N): ...` so progress is in git history and a crashed loop can
resume from the last checkpoint.

### `recover()`
Read the **last checkpoint commit** (`refine(cycle-N): ...`) from git log and return its cycle
number `N` as the last completed round so the loop can resume rather than restart.

## Landing Contract Integration

`snapshot()`'s base SHA (the value captured at `load()` time and returned from `snapshot()`)
is the `EXPECTED_HEAD` value injected into the fixer prompt for the pre-flight base pin.
The loop body captures this SHA immediately before dispatching the fixer.

`persist()` gains a **destination clause**: checkpoint commits (`refine(cycle-N): ...`) must
have the snapshot SHA as an ancestor (i.e., must be on the PR branch, not a detached worktree).
`persist()` verifies this with `git merge-base --is-ancestor <snapshot_sha> HEAD` before
committing; on failure it surfaces `BLOCKED: persist-ancestor-check-failed`.

`persist()` also performs a **clean-tree skip**: it runs `git status --short` before
attempting its own checkpoint commit. If the tree is already clean (the landing-verify step
already committed with `refine(cycle-N): landing-verify`), `persist()` skips the commit
entirely. This prevents duplicate commits per round. The skip is a pure no-op — the round's
findings are written by the loop's own findings accumulator, not by `persist()`.

## PR-Target Agent Mapping

The `pr-reviewer` / `pr-validator` / `pr-runner` / `pr-fixer` slugs in the `refining-prs` config
are abstract **role archetypes** — the ported relay roster ships NO dedicated `pr-*.md` agents. A
reader or runtime consulting the `pr` adapter resolves each archetype to a real ported agent via
the mapping below, so no undefined `relay:pr-*` slug is ever dispatched (this mirrors the
`skills/refining-prs/SKILL.md` shim — the two never diverge):

Role resolution order and agentType derivation: `skills/refining/SKILL.md` (Critics).

| Archetype     | Role/Agent file                  | Leaf agentType          | Notes                                              |
|---------------|----------------------------------|-------------------------|----------------------------------------------------|
| `pr-reviewer` | `agents/code-reviewer`           | `relay:code-reviewer`   | Reviews the diff for correctness (kept registered) |
| `pr-validator`| `agents/code-reviewer`           | `relay:code-reviewer`   | Validator-stance prompt prefix — challenge the reviewer's findings |
| `pr-runner`   | `roles/server-runner.md`         | `relay:leaf-reader`     | Live-server only; the `verify-tests` post-fix action runs via `roles/fix-coder.md` |
| `pr-fixer`    | `roles/fix-coder.md`             | `relay:leaf-worker`     | Applies fixer patches                              |

Additionally, `roles/doc-reference-reviewer.md` (`relay:leaf-reader`) is wired as a PR critic
directly — no archetype mapping needed.

### v1 Degeneracy Caveat

In relay v1, `pr-reviewer` and `pr-validator` both resolve to the same `code-reviewer` agent (the
validator runs the same agent with a challenge-stance prompt prefix). This is intentional for the
current roster size — a genuine adversarial validator with a distinct role is deferred to v2. A v2
follow-up that ports dedicated `pr-*` agents removes this annotation.
