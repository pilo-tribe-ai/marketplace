# Relay v4.5.0 — Worktree Isolation Gate + Session Rename

Status: design (approved in substance, pending written-spec review)
Date: 2026-06-24
Plugin: `plugins/relay` — version bump 4.4.0 → 4.5.0

## 1. Problem & goals

Two cross-cutting guarantees are missing from relay's L3 commands:

1. **Worktree isolation.** Commands that modify the local source tree (`implement`,
   `refine`, `drive`, `execute`) currently run wherever the user happens to be —
   including a dirty `main` checkout. The user wants every source-modifying command to
   **guarantee an isolated, up-to-date workspace** before any Workflow runs: the user
   must be on `main` or already inside a worktree, the worktree must be **confirmed
   correct**, `main` must be **pulled to latest** when a fresh worktree is created, and
   the switch must use the native **`EnterWorktree`** tool.

2. **Session naming.** **Every** relay command (all 6) should rename the current
   session to a meaningful, minimal, short **camelCase** slug derived from the task, so
   parallel/background relay sessions are identifiable at a glance.

Non-goals: changing orchestration logic, adding flags/config knobs, touching the
Workflow spines, or modifying `diagnose`/`setup` beyond the session rename.

## 2. Scope

| Command | Session rename (§4) | Worktree gate (§5) |
|---|---|---|
| `implement` | ✅ | ✅ |
| `refine` | ✅ | ✅ |
| `execute` | ✅ | ✅ |
| `drive` | ✅ | ✅ (verify-only on `--resume`) |
| `diagnose` | ✅ | ❌ (read-only) |
| `setup` | ✅ | ❌ (provisioning) |

## 3. Architecture overview

Both features are **MAIN-thread preflight steps** that run before the command generates
its Workflow. They follow relay's established command-body convention: a sourced bash
helper *prints* parseable state to stdout, and Claude *reads* that output and makes the
**tool** calls bash cannot (`SlashCommand`, `AskUserQuestion`, `EnterWorktree`).
Env vars are NOT relied on across Bash invocations (they don't persist) — state crosses
the boundary as printed stdout, exactly like `check-deps.sh` / `parse-engine-agent.sh`.

New step ordering inside each command:

```
Step 0.0 — Session rename        (all 6 commands)        ← NEW
Step 0   — Dependency / arg gate (existing, where present)
Step 0.5 — Worktree isolation    (4 modifying commands)  ← NEW
Step 1+  — existing classification + Workflow generation
```

Rename runs first so the session is named even if a later gate aborts; it is also
**best-effort** (degrades to a silent no-op, §4) so it never blocks the steps after it.

**Diagram is not uniform across commands — two caveats the implementer must honor:**

- **Not every command has a pre-existing Step 0.** The diagram assumes each modifying
  command already has a "Step 0 Dependency gate", but `execute.md` does **not**: it does
  not source `check-deps`, is 100%-soft (classifier-only), and has **no Step 0 today**.
  For `execute`, the new Step 0.0 (rename) and Step 0.5 (worktree gate) run with **no
  preceding Step 0**. The implementer must add a **fresh Bash-touching preflight** to
  `execute.md` from scratch — a new `Bash` fence plus the sourcing scaffolding for
  `session-slug.sh` and `worktree-preflight.sh` — where none existed (this is also why
  `execute.md` gains `Bash`, §5.4). §5 likewise reflects that `execute` gains a brand-new
  preflight rather than extending an existing gate.
- **Rename-source ordering for `refine`/`drive`.** Because Step 0.0 runs before Step 0,
  `refine` and `drive` use a static fallback slug at rename time (their salient source is
  only produced inside Step 0); see §4.2.

### New artifacts

- `scripts/session-slug.sh` — normalizes a free-text phrase to a valid camelCase slug.
- `scripts/worktree-preflight.sh` — classifies git state (`--classify`) and creates a
  worktree (`--create <base-ref>`).
- `skills/ensuring-worktree-isolation/SKILL.md` — `relay:ensuring-worktree-isolation`,
  the skill that drives the confirm/create/enter tool calls.

The session rename is small enough to live inline in each command body (a 2-line
instruction + the `session-slug.sh` call); it does **not** get its own skill.

## 4. Feature A — Session rename (Step 0.0)

> **DECISION — rename is BEST-EFFORT (non-fatal, degrades to a silent no-op).**
> Rationale: §1 frames naming purely as a convenience ("identifiable at a glance"), not
> a correctness property. A relay command must **never** abort because cosmetic session
> naming is unavailable. There are two distinct gates and they must not be conflated:
>
> - **Build-time design-validation gate (plan task 1, runs once on the build harness):**
>   confirm the `SlashCommand` tool *can* invoke the **built-in** `/rename`. This is the
>   STOP-and-report gate below — it validates the design is implementable as intended
>   before the remaining 5 commands are wired. It is **not** a runtime gate.
> - **Runtime behavior (every shipped command, on every user harness):** attempt the
>   rename best-effort. A user's harness may scope the `SlashCommand` tool to
>   custom/project commands only even though it worked on the build harness, so each
>   command body must instruct: *attempt `SlashCommand` `/rename <slug>`; if it errors or
>   is unavailable, continue silently (degrade to a no-op).* The implementer must **not**
>   wire a fatal runtime abort for rename.

### Mechanism
`/rename <slug>` invoked **best-effort** via the **`SlashCommand`** tool. This is the
only documented, supported way to rename a live session; directly editing the session
`.jsonl` is unsupported and explicitly avoided. The rename step is **non-fatal at
runtime**: each command body attempts `SlashCommand` `/rename <slug>`, and if the tool
errors or the built-in `/rename` is unavailable on the running harness, the command
**continues silently** — naming simply does not happen this run. There is no
"STOP / abort the command" path for rename at runtime.

> **Plan task 1 (BUILD-TIME design-validation gate, scoped to plan task 1 only):**
> confirm the `SlashCommand` tool can invoke the **built-in** `/rename` on the build
> harness (some harnesses scope the SlashCommand tool to custom/project commands only).
> This gate validates the rename mechanism is feasible as designed; if it cannot be made
> to work at all, the mechanism is redesigned before wiring the remaining 5 commands.
> This STOP-and-report applies to **build/design validation only** — at runtime the
> rename always degrades to a silent no-op (see DECISION above), never aborts the
> command. **Implementation note:** the mechanism must still be verified to actually
> rename the session during build (do not assume it works; prove it on the running build
> harness before relying on it).

### Slug derivation
1. The command body instructs Claude to choose **2-3 salient words** describing the
   task from its arguments (Claude's judgment supplies "meaningful"; e.g.
   `add a dark mode toggle` → `dark mode toggle`).
2. `scripts/session-slug.sh "<phrase>" --fallback <commandSlug>` normalizes that to a
   valid camelCase slug. See **§4.2** for the exact signature, transform ordering, and
   degenerate-input rule.
3. Claude attempts `SlashCommand` `/rename <slug>` **best-effort** (continue silently on
   error / unavailability — see Mechanism above).

Per-command salient source: `implement`/`execute`/`diagnose` → the task text;
`refine` → target + subject (e.g. `refine --target pr` on auth → `refinePrAuth`);
`drive` → oracle file basename (e.g. `migrateApiDrive`); `setup` → `relaySetup`.

**Salient-source availability and static fallback slug (ordering with Step 0).** §3
shows Step 0.0 (rename) ahead of Step 0 (arg/dependency gate) so the session is named
even if a later gate aborts. But two commands derive their salient source **from inside
the existing Step 0 bash block**, not from the raw `$ARGUMENTS`:

- `refine` — the salient source is the parsed `--target` plus subject, produced by the
  existing Step 0 arg-parse.
- `drive` — the salient source is the parsed oracle basename (`RELAY_DRIVE_ORACLE`),
  produced by the existing Step 0 bash block.

For these two, the salient phrase is **not yet available** when Step 0.0 runs first.
**Resolution (chosen): use a static fallback slug at Step 0.0** rather than reordering
the steps. At Step 0.0, `refine` renames to the static `--fallback` slug `refineRefine`
and `drive` to `relayDrive` (the command-name fallback), keeping rename strictly first
and dependency-free. The richer task-derived slug (`refinePrAuth`, `migrateApiDrive`) is
a non-goal for v4.5.0 for these two commands; deriving it would require moving rename
after arg-parse, which the "rename runs first" ordering forbids. `implement` /
`execute` / `diagnose` / `setup` keep their salient source from the raw arguments (or a
constant for `setup`) and rename with the meaningful slug at Step 0.0 as described.

### 4.2 `session-slug.sh` calling contract

**Signature:** `scripts/session-slug.sh "<phrase>" --fallback <commandSlug>`. The script
normalizes a free-text phrase but **cannot infer the command name**, so the caller must
pass the per-command fallback explicitly (e.g. `--fallback relayDiagnose`,
`--fallback refineRefine`, `--fallback relayDrive`, `--fallback relaySetup`,
`--fallback relayImplement`, `--fallback relayExecute`). The script prints exactly one
line: the final slug, to stdout.

**Transform order (pinned, deterministic — applied in this exact sequence so conflicting
cases resolve identically every run):**
1. lowercase the phrase.
2. strip punctuation (replace with word boundaries) and drop stopwords.
3. take the first ≤3 remaining words.
4. strip leading digits from the joined token (a leading-digit-only segment is removed
   first, so a token cannot begin with a digit).
5. camelCase the surviving words (first word lowercase, subsequent words capitalized).
6. cap the result at ≈24 characters (truncate on a word boundary where possible).

The leading-digit strip is applied **before** camelCase and **before** the length cap so
the cap never re-exposes a leading digit and camelCasing never reintroduces one.

**Degenerate-input rule → emit fallback.** If, after steps 1–4, **no** usable token
remains (input was empty, all-stopwords, punctuation-only, or all-digits such that
nothing survives the leading-digit strip), the script emits the `--fallback
<commandSlug>` value verbatim instead. This is the only path that produces the fallback;
a non-empty normalized slug is never overridden by the fallback.

This signature, pinned transform order, and degenerate rule are what make §7 test 1
deterministic and testable.

### allowed-tools
Add `SlashCommand` to all 6 commands' frontmatter (scoped to `SlashCommand(/rename:*)`
if the harness supports scoping; plain `SlashCommand` otherwise — to be confirmed in
plan task 1).

**`Bash` for `session-slug.sh`.** §4 requires sourcing `scripts/session-slug.sh` (a
`Bash` call) in **all 6** commands. Most already allow `Bash`, but `diagnose.md`
currently has `allowed-tools: AskUserQuestion(*), Workflow, Skill` — **no `Bash`**.
Therefore `diagnose.md` **must gain `Bash`** in its allowed-tools as part of this change
set, in addition to the `Bash` add for `execute.md` called out in §5.4. (`setup.md`
already has `Bash`.) Full allowed-tools change set for `Bash`: `diagnose.md += Bash`,
`execute.md += Bash`; the other four already permit it. When `Bash` is added to
`setup.md`'s neighbors, do **not** drop existing entries — see §7 for the
`test_setup_command.py` constraint (setup must retain `Bash`+`Skill`).

## 5. Feature B — Worktree isolation gate (Step 0.5)

Runs on the 4 modifying commands after the dependency gate, before Workflow generation.
The command body sources `worktree-preflight.sh --classify`, then invokes
`relay:ensuring-worktree-isolation`, which branches on the printed state.

### 5.1 `scripts/worktree-preflight.sh`

Two modes, both read git via plumbing and print a parseable `KEY=value` block.

**`--classify` (read-only).** Emits:
```
RELAY_WT_STATE=<worktree|main|stray|not-git>
RELAY_WT_BRANCH=<current branch or DETACHED>
RELAY_WT_DEFAULT=<default branch, e.g. main>
RELAY_WT_REPO_ROOT=<toplevel>
RELAY_WT_WORKTREE_ROOT=<path if in a .claude/worktrees worktree, else empty>
```
State rules:
- `not-git` — `git rev-parse` fails → script returns **non-zero** (command aborts).
- `worktree` — git-common-dir ≠ git-dir AND toplevel is under `.claude/worktrees/`.
- `main` — on the default branch in the primary checkout.
- `stray` — any other case in the primary checkout (non-default branch **or** detached
  HEAD).

Default branch resolution: `git symbolic-ref refs/remotes/origin/HEAD` →
fallback `origin/main` → `main`.

**`--create <base-ref>` (mutating; only called post-confirmation).** Steps:
1. `git fetch origin <default>` (this is the "pull latest from main" requirement; only
   reached when creating a worktree, never mutating the user's checked-out branch).
2. Resolve base: caller passes `origin/<default>` (main state) or `HEAD` (stray state).
3. Generate a slug-based worktree name under `.claude/worktrees/` (reuse the
   session slug; suffix `-N` on collision).
4. `git worktree add .claude/worktrees/<name> -b relay/<slug> <base-ref>`.
5. Print `RELAY_WT_CREATED_PATH=<absolute path>`.

Creation deliberately uses `git worktree add` (deterministic base ref) rather than
`EnterWorktree({name})` (whose base is governed by the global `worktree.baseRef`
setting and can't be chosen per-call). The session then enters via the path form.

### 5.2 `relay:ensuring-worktree-isolation` skill — state machine

| State | Confirmation (`AskUserQuestion`) | On accept |
|---|---|---|
| `worktree` | "In worktree `<branch>` at `<path>` — correct workspace for **<task>**?" → Yes / No | **Yes:** proceed (already isolated). **No:** abort with guidance ("switch to the right worktree or to `main`, then re-run"). |
| `main` | "On `main`. Create a fresh isolated worktree off `origin/<default>`? (recommended) / Proceed on main in place / Cancel" | **Create:** `--create origin/<default>` → `EnterWorktree({path: RELAY_WT_CREATED_PATH})` → proceed. **Proceed:** continue on main in place. **Cancel:** abort. |
| `stray` | "On branch `<branch>` (not main, not a worktree). Create a worktree **from current HEAD** (preserves your work)? (recommended) / Proceed here in place / Cancel" | **Create:** `--create HEAD` → `EnterWorktree({path})` → proceed. **Proceed:** continue in place. **Cancel:** abort. |
| `not-git` | (none — script already returned non-zero) | command aborted |

After a successful `EnterWorktree`, the session cwd is the new worktree, and the
Step 1+ Workflow generates and runs there.

### 5.3 Drive autonomy (`confirm-at-launch-then-headless`)
No special loop logic is needed: the gate is a MAIN Step 0.5 that runs **before** the
Workflow, so the human is present for the one confirmation and the headless loop never
re-prompts. The single addition: on `/relay:drive --resume`, the gate runs
**verify-only** — it asserts the cwd matches the **workspace mode the original run
recorded** and proceeds **without prompting or creating**.

**Reconciliation with §5.2 "proceed in place" (resolves the contradiction).** §5.2 lets
a `drive` run legitimately run **not** in a worktree (the `main` "Proceed on main in
place" and `stray` "Proceed here in place" options). A verify-only resume that hard-
required a `worktree` state would break resume of any such in-place run. **Resolution
(chosen): `loop-state.md` records the chosen workspace mode**, and verify-only resume
accepts whatever mode the original run used:

- The Step 0.5 gate, on the **initial** `drive` run, writes the resolved workspace mode
  into `loop-state.md` — `RELAY_DRIVE_WORKSPACE=worktree` (path recorded) or
  `RELAY_DRIVE_WORKSPACE=in-place` (with the recorded branch/checkout).
- On `--resume`, verify-only reads `RELAY_DRIVE_WORKSPACE` and asserts the **current cwd
  matches that recorded mode**: for `worktree`, the cwd must be that worktree; for
  `in-place`, the cwd must be the recorded branch/checkout. It proceeds without prompting
  or creating in either case.
- Only a genuine **mismatch** (cwd does not match the recorded mode — e.g. the worktree
  is gone, or the user resumed from a different place) prints a clear error and aborts.

This keeps the "proceed in place" option available for `drive` and makes resume mode-
agnostic, rather than disallowing in-place drive runs.

### 5.4 allowed-tools
The 4 modifying commands add `EnterWorktree` and `AskUserQuestion`; `execute.md`
additionally adds `Bash` (currently `Workflow, Skill` only). Because `execute.md` has no
pre-existing Step 0 (see §3), the implementer adds a **fresh Bash-touching preflight**
to it from scratch (new `Bash` fence + sourcing scaffolding for `session-slug.sh` and
`worktree-preflight.sh`) rather than extending an existing dependency gate. Note also
that `diagnose.md` gains `Bash` for `session-slug.sh` (§4 allowed-tools), even though it
is read-only and has no worktree gate.

## 6. Self-containment

`relay:ensuring-worktree-isolation` owns the full state machine and confirmation logic;
it does **not** delegate to `superpowers:using-git-worktrees` (that skill lacks the
confirm-existing / pull-latest / EnterWorktree-path flow). Prose may reference it.

## 7. Tests

Added under `plugins/relay/tests/unit/`:

1. `session-slug.sh` unit — phrase → camelCase slug across cases (multiword,
   punctuation, stopwords, length cap, empty → fallback, leading-digit strip).
2. `worktree-preflight.sh` classification unit — temp git repos exercising
   `main` / `stray` / detached / `worktree` (created under `.claude/worktrees/`) /
   `not-git`, asserting the printed `RELAY_WT_STATE`.
3. `worktree-preflight.sh --create` unit — asserts `git fetch` invoked, base ref
   honored (origin/default vs HEAD), worktree created under `.claude/worktrees/`,
   `RELAY_WT_CREATED_PATH` printed.
4. Command-structure test — all 6 command bodies invoke Step 0.0 rename and have
   `SlashCommand` in `allowed-tools`; the 4 modifying commands invoke
   `relay:ensuring-worktree-isolation` and have `EnterWorktree` + `AskUserQuestion`
   (and `execute.md` has `Bash`).
5. Skill-structure test — `ensuring-worktree-isolation/SKILL.md` has valid frontmatter
   (name, description) and is discoverable.

### 7.1 Required edits to the EXISTING validator allowlists (keep the suite green)

These are **edits**, not new tests, and are mandatory — the existing suite fails without
them:

- **`validate_l3_command.py` `_KNOWN` allowlist.** The baseline `test_l3_command.py`
  (26 passing) reads each command body and runs `vl3.check_command`, which flags **any**
  `relay:<token>` not in `_KNOWN`. The new worktree skill is invoked as
  `relay:ensuring-worktree-isolation`, so the token `ensuring-worktree-isolation` **must
  be added to `validate_l3_command.py` `_KNOWN`**, otherwise every modifying command body
  fails with `unknown relay vocabulary token: ensuring-worktree-isolation`.
- **L2 vocab allowlist.** Correspondingly add `ensuring-worktree-isolation` to
  `validate_l2_vocab` `L2_NAMES` (or the `EXPECTED_SKILLS` allowlist, whichever that
  validator consults) so the skill is recognized as known relay vocabulary.
- **`test_setup_command.py` invariant.** It asserts `setup.md` allowed-tools contains
  `Bash`+`Skill`. Adding `SlashCommand` to `setup.md` must **not** drop `Bash` or
  `Skill` — append, do not replace.

### 7.2 Runtime-unknown hard gates (carried from §9, must be PROVEN on the live harness)

The three runtime unknowns below are **plan hard-gates**, not assumptions, and all must
be proven on the running harness before the remaining commands are wired (they are what
block a clean single PR):

1. `SlashCommand` can invoke the **built-in** `/rename` on the running build harness
   (§9 risk-1 / §4 plan task 1).
2. `EnterWorktree({path})` accepts a just-created `git worktree add` worktree under
   `.claude/worktrees/` of the same repo (§9 risk-2).
3. `worktree.baseRef` independence — no existing relay test pins a `baseRef` (§9 risk-3).

## 8. Versioning & docs

- `plugins/relay/.claude-plugin/plugin.json` → `4.5.0` (same PR; version is the cache
  key per project CLAUDE.md).
- `CHANGELOG.md` entry.
- `skills/using-relay/SKILL.md` — document Step 0.0 rename + Step 0.5 worktree gate in
  the command descriptions / pipelines section.

## 9. Risks & open items

The first three are the **runtime unknowns that block a clean single PR** and are carried
as **plan hard-gates** (proven on the live build harness), not assumptions — see §7.2.

1. **`SlashCommand` → built-in `/rename` (rename is best-effort).** At **runtime** the
   rename is **non-fatal**: each command attempts `SlashCommand` `/rename <slug>` and, if
   the tool errors or the built-in `/rename` is unavailable on the user's harness,
   **degrades to a silent no-op** and the command continues (§4 DECISION + Mechanism). A
   user harness scoping `SlashCommand` to custom/project commands only must not abort a
   relay command, because naming is a convenience, not a correctness property (§1). The
   **STOP-and-report** framing is scoped to the **build-time** design-validation gate
   (plan task 1) only: prove on the build harness that the mechanism *can* rename a live
   session before wiring the remaining 5 commands; if it cannot be made to work at all,
   redesign the mechanism — but never wire a fatal **runtime** abort for rename.
2. **EnterWorktree path-entry constraints (hard gate).** The tool requires the target be
   a registered worktree under `.claude/worktrees/` of the same repo — satisfied by §5.1
   step 4. Prove on the running harness that `EnterWorktree({path})` accepts the
   just-created `git worktree add` worktree. **Tool-note caveat (load-bearing):**
   `ExitWorktree` will **not** remove a worktree entered via `path`, and previously
   visited worktrees become **non-writable after a further switch**. Therefore the gate
   must call `EnterWorktree` **exactly once** per run and **never re-switch** afterward
   (the Step 1+ Workflow runs in that single entered worktree; do not enter a second
   worktree later in the same session).
3. **`worktree.baseRef` independence (hard gate).** By creating via `git worktree add` we
   avoid coupling to the user's global setting; confirm **no existing relay test pins a
   `baseRef`** on the running harness before relying on this.
4. **Dirty primary checkout on `stray`/`main` "proceed in place".** The gate offers an
   isolated path but does not force it; "proceed in place" is the user's explicit choice
   and is left as-is (YAGNI — no auto-stash). For `drive`, this choice is **recorded in
   `loop-state.md`** so verify-only `--resume` accepts the same mode (§5.3).
