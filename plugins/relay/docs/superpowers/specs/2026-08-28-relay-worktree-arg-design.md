# `--worktree` pre-answers the Step 0.5 gate

Date: 2026-08-28
Status: approved for implementation
Target version: relay 4.45.0
Closes: #112

## The problem

Step 0.5 of the four source-modifying L3 commands (`implement`, `refine`, `execute`,
`drive`) asks one question: where does this run work? The gate classifies the checkout
into `worktree`, `main` or `stray`, asks one `AskUserQuestion`, and offers three answers:
create a fresh worktree, proceed in place, or cancel.

Three callers cannot answer that question:

1. **A user who already knows the target.** The gate makes them click through the same
   confirmation on every run.
2. **A headless run** (`claude -p`). The command skips the confirmation and proceeds in
   place, in whatever directory the session holds. There is no way to say "run there".
3. **The `apk` adapter** (`implementing-spec`, issue #112). The adapter states that its
   caller owns the worktree and then takes no input for which one. The sub-agent that
   invokes it inherits the session directory, which for `apk` is the primary checkout.

Two facts in the code shape the fix:

- `worktree-preflight.sh --classify` calls a checkout `worktree` only when its toplevel is
  under `.claude/worktrees/`. Every other linked worktree classifies as `stray`
  (`scripts/worktree-preflight.sh:93-101`).
- `WORKTREE` is the env var every dispatcher already reads for its cwd
  (`skills/dispatching-acpx-agents/acpx-dispatch.sh` passes `--cwd "${WORKTREE:-$REPO_ROOT}"`;
  the in-session wrapper feeds it into `WORKTREE_PATH` and `EXPECTED_HEAD`). [inferred] No
  command sets it. The in-session wrapper records this hole itself, marked `[inferred]`
  (`skills/dispatching-in-session-agents/SKILL.md:103-105`).
- Relay state never crosses a Bash call as an environment variable. The seam rule is stated in
  `skills/ensuring-worktree-isolation/SKILL.md:27-30`: "State crosses the boundary as printed
  stdout, never env vars (env does not persist across Bash calls)". Every `WORKTREE` hand-off
  in this design therefore travels as printed text that the reading step substitutes into the
  next tool call, never as `export WORKTREE=…` in one Bash block read by a later one.
  [inferred]

## The design

### One model: the flag is a pre-answered gate

`--worktree <value>` supplies the answer to the Step 0.5 question before the gate asks
it. When the flag is present, the gate asks nothing and does one deterministic thing.
When the flag is absent, the gate runs exactly as today. "Work in the current directory"
is one more answer to the same question, not a second flag.

### 1. Value grammar

```
--worktree current          # the cwd, as it is
--worktree <path>           # an existing linked worktree of this repository
--worktree <branch>         # the linked worktree that has <branch> checked out
```

`current` is a reserved word. Any other value is tried first as a path and then as a
branch:

- A value that names a directory that is a linked worktree of this repository is a path.
  [inferred]
- Otherwise the value is tried as a branch name. [inferred]
- A value that names a directory that exists but is not a linked worktree of this repository
  is still tried as a branch name, and resolves to `missing` when no worktree has that branch
  checked out. Existence alone does not make a value a path. [inferred]

This rule is stated once, in `ensuring-worktree-isolation/SKILL.md`, and tested once.

### 2. The resolver: `worktree-preflight.sh --resolve <value>`

A third mode of the existing script, next to `--classify` and `--create`. Read-only. It
prints a `KEY=value` block to stdout, same seam as the other two modes:

```
RELAY_WT_RESOLVED=<current|path|branch|missing>
RELAY_WT_TARGET=<absolute toplevel, or the raw value when missing>
RELAY_WT_TARGET_BRANCH=<branch checked out at the target, or empty when missing>
```

`RELAY_WT_TARGET_BRANCH` comes from the `branch refs/heads/<b>` line that
`git worktree list --porcelain` prints in the same block as the matched `worktree` line. On
the `branch` row the resolver already matched that line and reads the pair at once. On the
`path` row it matched only the `worktree` line, so it reads the block's following
`branch`/`detached` line as one added parse — of the same porcelain output, with no second
`git` call. A `detached` line prints `DETACHED`. [inferred]

`RELAY_WT_TARGET_BRANCH` has one consumer: the gate skill puts it in the line it prints when
it proceeds on a `path` or `branch` result — `[relay] worktree: <target> (branch
<RELAY_WT_TARGET_BRANCH>)`. It is never a branch condition. When the target is detached the
key is `DETACHED`, the same word `--classify` already prints for `RELAY_WT_BRANCH`.
[inferred]

Resolution, in order:

| `<value>` | Check | `RELAY_WT_RESOLVED` |
|---|---|---|
| `current` | none | `current`; `RELAY_WT_TARGET` = `git rev-parse --show-toplevel` |
| an existing directory | `cd <value> && pwd -P` equals a `worktree` line in `git worktree list --porcelain` | `path` |
| anything else | a `branch refs/heads/<value>` line in `git worktree list --porcelain` | `branch`; `RELAY_WT_TARGET` = the paired `worktree` line |
| no match | — | `missing`; `RELAY_WT_TARGET` = `<value>` verbatim |

Every path is canonical (`cd && pwd -P`) before comparison. On macOS, `/tmp` and
`/private/tmp` name the same directory; a string compare on the raw path gives a false
mismatch. The `worktree` lines from `git worktree list` are also canonicalized the same
way.

A directory that exists but is not in `git worktree list` — a plain folder, or a
worktree of a different repository — is not a path. The resolver then tries the same value as
a branch name, and prints `missing` when that also does not match. The script does not guess.
[inferred]

`not-git` returns non-zero, as `--classify` does.

### 3. The gate, with the flag present

`relay:ensuring-worktree-isolation` gains one section that runs before the state
machine.

**How the value reaches the skill.** The skill takes no tool-call arguments today, and env
vars do not survive a Bash call, so the flag travels the same way `--classify` state travels:
as printed stdout that MAIN reads and substitutes. The command's Step 0 block prints one more
line beside the axis echo — `RELAY_WT_ARG=<value>` when the flag was given, and nothing at all
when it was not. Step 0.5 gains one new call: when `RELAY_WT_ARG` was printed, it runs
`worktree-preflight.sh --resolve "<value>"` beside the existing `--classify` source line, and
passes both printed blocks to the skill. When `RELAY_WT_ARG` is absent, Step 0.5 runs
`--classify` only and the skill runs today's state machine unchanged. [inferred]

**How the skill knows the session is headless.** The same way relay already knows: the model
decides, Bash does not. No shell test tells a script whether the parent harness will honour
`AskUserQuestion`, and `CLAUDE_CODE_SESSION_ID` is set in both interactive and `claude -p`
runs, so it cannot separate them. The rule stays the prose test the four commands already
carry — `implement.md:72-74` and `implement.md:123-125`: "If this session cannot present an
interactive question (headless/programmatic run, e.g. `claude -p`)…". The pre-answered section
of the gate skill repeats that one sentence for the `missing` row and takes the abort branch
under it. This design adds **no** new detection site and **no** `RELAY_WT_HEADLESS` key.
[inferred]

The pre-answered section branches on `RELAY_WT_RESOLVED`:

| Resolved | Action | Question asked |
|---|---|---|
| `current` | Proceed in place. | none |
| `path`, `branch` | If `RELAY_WT_TARGET` equals the current toplevel: proceed. Else `EnterWorktree({path: RELAY_WT_TARGET})` once. | none |
| `missing`, interactive | Today's Create question, unchanged in shape (Create / Proceed in place / Cancel), with today's `<base>` rule (`origin/<default>` from `main`, `HEAD` from `stray`). The flag pre-commits the destination: Create → `--create <base> --at <value>`, then `EnterWorktree` once. Proceed in place → proceed, no create, no enter. Cancel → abort. Create treats `<value>` as a path even when the user meant a branch name: a bare name makes a worktree at `./<value>` on branch `relay/<value>`. Users who want a named directory should pass an absolute path. | one |
| `missing`, headless | Abort: `worktree-missing: <value> is not a worktree or a checked-out branch of this repository`. | none |

The enter-exactly-once invariant is unchanged. The gate runs once per run and calls
`EnterWorktree` at most once, flag or no flag. The invariant is per run, and nothing in git
state or in the skill tells it whether some earlier command in the same session already
entered a worktree; that session-level hazard is pre-existing and out of scope (see
Not doing). [inferred]

`--create` gains an optional `--at <path>` argument so the `missing` + interactive branch
can create the worktree where the user named it, not under `.claude/worktrees/`. Without
`--at`, `--create` behaves as today, positional `[slug]` and all.

**The `--at` call shape.** The new signature is `--create <base-ref> [--at <path>] [slug]`,
and the parser rules are: `<base-ref>` stays the first positional and must come first; `--at`
and `--at=<path>` are both accepted, anywhere after `<base-ref>`; `--at` with no value is a
usage error (exit 2); a trailing positional `[slug]` passed together with `--at` is accepted
and ignored. With `--at` the slug is always `basename(<path>)`, so the
branch the user gets — `relay/<basename>` — matches the directory the user named. The `-N`
collision suffix of `_wt_create` (`scripts/worktree-preflight.sh:146-153`) is **not** applied
on this path: a user who named an exact destination must get that destination or a refusal,
never a silently different one. `--create --at <path>` therefore aborts non-zero with
`[relay] error: worktree-exists: <path> or branch relay/<basename> already exists` when either
the path or `refs/heads/relay/<basename>` is already taken. The usage string at
`scripts/worktree-preflight.sh:193` gains the new form. [inferred]

Without the flag, headless runs still proceed in place, as today. The flag adds a way to be
explicit. It does not change the default.

### 4. Classifier widening

`--classify` today:

```
linked worktree  AND  toplevel under /.claude/worktrees/   →  worktree
```

After this change:

```
linked worktree  (git-common-dir != git-dir)               →  worktree
```

`RELAY_WT_WORKTREE_ROOT` is set for every linked worktree, including `apk`'s
`.worktrees/apk/<scope>` and any worktree the user made by hand.

This is the one behaviour change that reaches runs **without** the flag. A user who sits in
a hand-made linked worktree gets the `worktree` confirmation ("correct workspace for
<task>?") instead of the `stray` Create offer. That is the correct reading: the checkout
is already isolated.

### 5. `WORKTREE` reaches every dispatch after the gate settles

After the gate settles — flag or no flag, any answer — one line is printed:

```
RELAY_WT_ACTIVE=<absolute toplevel of the directory the run works in>
```

**Who prints it.** The command prints it, not the skill, and it prints it in a new **Step
0.55** Bash block that runs after `relay:ensuring-worktree-isolation` returns. The name is
`0.55`, not `0.6`: `implement.md:127` already owns `Step 0.6 — Branch guard`, and Step 0.55
runs before it. The block is one line — [inferred]
`printf 'RELAY_WT_ACTIVE=%s\n' "$(git rev-parse --show-toplevel)"` — and it is correct for
every branch of the gate, because MAIN's cwd is already the final workspace by the time the
skill returns: the Create and `path`/`branch` branches each call `EnterWorktree` before
returning, and every other branch leaves the cwd alone. The skill stays input-free of this
concern. [inferred]

**How the value reaches a dispatch.** Not as a shell export — env does not survive a Bash
call. The Workflow-generation step reads the printed `RELAY_WT_ACTIVE` line and writes its
value as a **literal absolute path** into the generated dispatch, at the site that mechanism
actually uses. Each row names a different script; they are not interchangeable: [inferred]

| Dispatch mechanism | Site the literal path is written to |
|---|---|
| `acpx` | `WORKTREE=<literal> bash skills/dispatching-acpx-agents/acpx-dispatch.sh …` — one process invocation, not a cross-call export. |
| `bg-sessions` | `WORKTREE=<literal> bash skills/dispatching-bg-agents/bg-dispatch.sh …`. That script already requires `WORKTREE` (`bg-dispatch.sh:67`) and `cd`s into it before it calls the launcher (`bg-dispatch.sh:210`). It does **not** go through `acpx-dispatch.sh`. |
| `session-tree` | `skills/orchestrating-session-trees` calls `scripts/bg-launch.sh` directly, and that script has no cwd flag (its parser at `bg-launch.sh:145-162` takes only `--name`, `--model`, `--permission-mode`, `--prompt-file`, `--fork-from`, `--check-name`). The orchestrator therefore wraps the call: `(cd <literal> && bash scripts/bg-launch.sh …)`. No flag is added to `bg-launch.sh` in this change. |
| `in-session`, writer roles | The generated `agent()` prompt carries the literal in its `WORKTREE_PATH` slot, and `EXPECTED_HEAD` is captured with `git -C <literal> rev-parse HEAD`. The slot substitution pass of `docs/dispatch-contract.md:163-171` already reads both. MAIN pre-fills the two placeholders at generation time, so the coordinator's own `${WORKTREE:-$REPO_ROOT}` fill at dispatch time finds nothing left to substitute and is a no-op for a run that reached Step 0.55. It stays the fallback for a caller that supplies nothing. |
| `in-session`, non-writer roles | Nothing. `WORKTREE_PATH` / `EXPECTED_HEAD` are Writer-Role Landing Contract slots (`docs/dispatch-contract.md:153`); a reader role has no slot to fill and reads no path. Widening the slot set to reader roles is out of scope. |

The generator therefore never emits the string `${WORKTREE:-$REPO_ROOT}`; it emits the
resolved path. The `${WORKTREE:-…}` fallback in the dispatch scripts stays as the safety net
for a caller that supplies nothing. [inferred]

The `[inferred]` note in `skills/dispatching-in-session-agents/SKILL.md:103-105` — "As of
v4.1.0 no entry-point command exports `WORKTREE`, so the fallback resolves to `REPO_ROOT` in
practice and the landing-verify still detects Variant B through it. [inferred]" — is replaced
by this exact sentence, untagged because it is no longer inferred: [inferred]

> As of v4.45.0 every source-modifying L3 command sets `WORKTREE` in its Step 0.55 block after
> the worktree gate settles, so the path reflects the run's active worktree; the `REPO_ROOT`
> fallback still covers a caller that sets nothing.

`docs/dispatch-contract.md` carries no `[inferred]` note at all. Its lines 167-171 already
describe `WORKTREE` as "the env var set by the entry-point command (fallback: `REPO_ROOT`)",
which this change makes true rather than false. Do not edit that file. [inferred]

What this does and does not do on each engine:

| Engine | `WORKTREE` effect |
|---|---|
| `acpx`, `bg-sessions` | `--cwd` for the child process. The work relocates. |
| `in-session` | `WORKTREE_PATH` / `EXPECTED_HEAD` slots. Git operations target the right tree; relative `Read`/`Write`/`Edit` still resolve against the session cwd. MAIN's cwd is the worktree after `EnterWorktree`, so in practice the two agree for the L3 commands. |

The in-session limit applies only when MAIN did **not** enter the worktree — that is the
`implementing-spec` case, and section 6 handles it with a guard, not a relocation.

### 6. `implementing-spec` gets the same channel (#112)

The adapter gains a fourth optional input line:

```
spec_path: docs/superpowers/specs/2026-08-22-example-design.md
branch_hint: feature/S1.1.1-example
closes_issue: 42
worktree: /abs/path/to/repo/.worktrees/apk/billing
```

New Step 1.5, before the spec gate:

- Line absent → behave as today.
- Line present → run `worktree-preflight.sh --resolve <value>`. Compare
  `RELAY_WT_TARGET` to the skill's own `git rev-parse --show-toplevel`, both canonical.
  - Equal → continue, and hand the target to the spine the same way section 5 does: the
    adapter prints `RELAY_WT_ACTIVE=<target>` and passes that literal absolute path in a new
    `worktree` key of the `inputs` block it gives `relay:running-implement-spine`. It does not
    run `export WORKTREE=…`; that would not survive the next tool call. The spine writes the
    literal into each dispatch it generates, per the section 5 table. [inferred]

`worktree` is an **eleventh, optional input** to `relay:running-implement-spine`, added to the
ten its Inputs section lists today (`skills/running-implement-spine/SKILL.md:17-33`). Absent →
the spine generates dispatches exactly as it does now. `/relay:implement` fills it from its own
Step 0.55 line at the Step 3 call site (`commands/implement.md:188-194`, "Pass all ten inputs",
which becomes eleven). `refine.md`, `execute.md` and `drive.md` do the same from their own
Workflow-generation steps. [inferred]
  - Not equal, or `missing` → return and stop:

    ```
    status: blocked
    reason: worktree-mismatch
      caller declared: /repo/.worktrees/apk/billing
      skill running in: /repo
    ```

The adapter still never creates, enters or switches. The key name is `worktree`, the same
word as the flag. This is what `apk` asked for in #112 section 5.

This does not let `apk`'s `build` complete when the sub-agent starts in the wrong
directory. It turns a silent wrong-directory implementation into a named refusal. Letting
it complete is a relocation question on the `in-session` engine, out of scope here.

### 7. Flag parsing in the four commands

Each command's Step 0 block parses the flag the same way the others are parsed:

```bash
_worktree="$(printf '%s' "$_relay_args" | sed -nE "s/.*--worktree[ =]+[\"']?([^\"' ]+).*/\1/p")"
case "$_worktree" in --*) _worktree="" ;; esac
if printf '%s' "$_relay_args" | grep -qw -- '--worktree' && [ -z "$_worktree" ]; then
  echo "[relay] error: --worktree takes a value: current, a path, or a branch name" >&2
  exit 1
fi
```

The capture regex prints an empty string both when the flag is absent and when the flag is
present with no value, so the `grep -qw` presence check is what tells the two apart. It is not
optional. [inferred]

The `case` line is also not optional. Unlike `--engine`/`--agent`, whose `[A-Za-z-]+` class
can never match a `--flag` token, the value class here matches anything that is not a space or
a quote — so `--worktree --engine claude <task>` would otherwise capture `--engine` as the
worktree value, pass the presence check, and corrupt both flags in silence. Discarding a
captured value that starts with `--` turns that into the same loud "takes a value" error.
[inferred]

The value character class is `[^\"' ]+`: a value that contains whitespace is not supported,
quoted or not. A path with a space in it must be passed as a branch name, or the run must be
started from that directory with `--worktree current`. The `argument-hint` of each command
states the constraint: `[--worktree current|<path-without-spaces>|<branch>]`. [inferred]

The value is stripped from the task text before `relay:classifying-task-kind` reads it,
the same way each command already strips its own dispatch and retro flags. Three of the four
commands (`implement.md:157`, `refine.md:107`, `execute.md:93`) strip in prose and need one
more named flag in that sentence. `drive.md` strips in prose too, and also with a real `sed`
at lines 23-25 that derives `_oracle` from the leftover token, so it needs a real new stanza —
`s/--worktree[ =]+[\"']?[^\"' ]+[\"']?//g` — added to that `sed -E` list. Without it the path
survives and becomes, or corrupts, the oracle. [inferred]

Cross-arg rules:

- `--retro` with a target ignores `--worktree` (retro is read-only and never enters a
  worktree). The notice prints from the Step 0 flag-parse block, beside the existing
  `[relay] retro:` echo, and reads `[relay] --worktree ignored: retro is read-only`. Retro-only
  mode is handled by Step 0.2 and stops there, so Step 0.5 and Step 0.55 never see the flag.
  [inferred]
- `--verify` with `--worktree current` on the default branch still fails at Step 0.6. The
  branch guard reads the state after the gate settles, as today.

### 8. Error text

One prefix, everywhere: `[relay] error:`, the prefix the commands and the preflight script
already use. No message names the calling command, because the gate skill emits four of these
rows and is not told which command called it. [inferred]

| Condition | Emitted by | Message |
|---|---|---|
| `--worktree` with no value, or a value starting with `--` | command, Step 0 | `[relay] error: --worktree takes a value: current, a path, or a branch name` |
| `missing`, headless | gate skill | `[relay] error: worktree-missing: <value> is not a worktree or a checked-out branch of this repository` |
| `missing`, interactive, user picked Cancel | gate skill | `[relay] error: cancelled at the --worktree <value> create prompt` [inferred] |
| `--resolve` outside git | script | `RELAY_WT_STATE=not-git` on stderr, non-zero |
| `--create --at <path>` where the path or `relay/<basename>` exists | script | `[relay] error: worktree-exists: <path> or branch relay/<basename> already exists`, non-zero [inferred] |
| `--retro <target>` with `--worktree` | command, Step 0 | `[relay] --worktree ignored: retro is read-only` — a notice on stdout, not an error; the run continues [inferred] |
| adapter mismatch | `implementing-spec` | the `blocked` block in section 6 |

## Files

| File | Change |
|---|---|
| `scripts/worktree-preflight.sh` | `--resolve <value>`; widen `--classify`; `--create … --at <path>`; update the SOURCED/EXECUTED synopsis at lines 6-7, the `RELAY_WT_WORKTREE_ROOT` description at line 14, the `worktree` state rule at line 17, and the usage string at line 193 |
| `skills/ensuring-worktree-isolation/SKILL.md` | pre-answered section; the path-then-branch rule; read `RELAY_WT_ARG` and the `--resolve` block from the printed Step 0 / Step 0.5 output; update the `RELAY_WT_WORKTREE_ROOT` description at line 44 to "path if in a linked worktree, else empty" |
| `commands/implement.md`, `refine.md`, `execute.md`, `drive.md` | parse `--worktree` with the presence check and the leading-`--` guard; print `RELAY_WT_ARG`; strip from task text; Step 0.5 also runs `--resolve` when `RELAY_WT_ARG` is set; new Step 0.55 printing `RELAY_WT_ACTIVE`; forward `worktree` to the Workflow-generation step; `argument-hint` |
| `commands/drive.md` (extra) | add the `--worktree` stanza to the `_oracle` `sed -E` list at lines 23-25 |
| `skills/running-implement-spine/SKILL.md` | add optional eleventh input `worktree` to the Inputs list; write the literal path into each generated dispatch, per the section 5 table |
| `skills/orchestrating-session-trees/SKILL.md` | wrap the `bg-launch.sh` call sites in `(cd <literal> && …)` when `worktree` is set |
| The Workflow-generation steps of `refine.md` and `drive.md` | same literal-path injection, per the section 5 table |
| `commands/execute.md` Step 2 | one sentence, because this command composes its leaves freely: "For each `agent()` node whose role file declares `role-class: writer`, put the literal `RELAY_WT_ACTIVE` value in the `WORKTREE_PATH` slot and capture `EXPECTED_HEAD` with `git -C <literal> rev-parse HEAD`. Composed nodes that are not writer roles get nothing." |
| `skills/implementing-spec/SKILL.md` | `worktree:` line; Step 1.5 guard; pass the target in the spine `inputs` block; change "three inputs" at line 16 to "four inputs" |
| `skills/dispatching-in-session-agents/SKILL.md` | replace the `[inferred]` "no entry-point command exports `WORKTREE`" sentence at lines 103-105 with one naming Step 0.55. `docs/dispatch-contract.md` has no such note and is not changed |
| `.claude-plugin/plugin.json`, `CHANGELOG.md` | 4.45.0 |

## Tests

New file `tests/unit/skill-structure/test_worktree_arg.py`. Each test builds a real
repository under `tmp_path` and runs the script; none asserts on prose alone.

Resolver:

- `current` prints the toplevel.
- an existing linked worktree by absolute path → `path`.
- the same worktree by relative path → `path`, same target.
- the same worktree by symlinked path → `path`, same target (macOS `/tmp`).
- a branch with a worktree → `branch`, target is that worktree.
- a branch with no worktree → `missing`.
- a plain directory → `missing`.
- a directory that is a worktree of another repository → `missing`.
- a directory that is a linked worktree of this repository AND is also a branch name → `path`
  (the ambiguity rule: the worktree wins). [inferred]
- a plain directory whose name is also a branch that has a worktree → `branch`, target is that
  worktree (existence alone does not make a value a path). [inferred]
- outside git → non-zero.
- `RELAY_WT_TARGET_BRANCH` is the branch at the target on `path` and `branch`, `DETACHED` on a
  detached target, and empty on `missing`. [inferred]

Classifier:

- a linked worktree outside `.claude/worktrees/` → `worktree`, root set.
- `.claude/worktrees/<x>` still → `worktree` (no regression).
- primary checkout on a feature branch still → `stray`.

`--create --at`:

- `--create <base> --at <path>` creates at the named path on `relay/<basename>`; prints
  `RELAY_WT_CREATED_PATH`. [inferred]
- `--at` at a path that already exists → non-zero, `worktree-exists`, and no `-N` suffix
  anywhere in the output. [inferred]
- `--at` where `refs/heads/relay/<basename>` already exists → non-zero, `worktree-exists`.
  [inferred]
- without `--at` still creates under `.claude/worktrees/`, and the `-N` collision suffix still
  works there. [inferred]

Executable command-block gates. Each of these extracts the Step 0 / Step 0.55 bash block from
the command file and runs it in a fixture repository, so it asserts on behaviour, not on
prose: [inferred]

- `--worktree /some/path <task>` → the block prints `RELAY_WT_ARG=/some/path`. [inferred]
- `--worktree` with no value → non-zero, and stderr names `--worktree takes a value`.
  [inferred]
- `--worktree --engine claude <task>` → non-zero, same message; `--engine` is not swallowed.
  [inferred]
- no `--worktree` → the block prints no `RELAY_WT_ARG` line at all. [inferred]
- the Step 0.55 block prints `RELAY_WT_ACTIVE=` followed by the fixture toplevel. [inferred]
- `drive.md`'s `_oracle` stanza, run with `--worktree /a/b <oracle>`, yields `<oracle>` with no
  path fragment left in it. [inferred]

Static gates (`test_plugin.py` style) — structural only, on things that have no runtime:

- all four commands list `--worktree` in `argument-hint`.
- all four name `--worktree` in the sentence that strips flags before the classifier line.
- `ensuring-worktree-isolation` names `current`, `missing`, `worktree-missing`,
  and `RELAY_WT_ARG`, and its `RELAY_WT_WORKTREE_ROOT` line no longer says
  `.claude/worktrees`. [inferred]
- `running-implement-spine` lists `worktree` in its Inputs section. [inferred]
- no command, skill, or script touched by this change contains the string `RELAY_WT_HEADLESS`: headless stays a model-layer
  prose test, and a key would invite a Bash detection that cannot work. [inferred]
- `implementing-spec` names `worktree`, `worktree-mismatch`; `test_implementing_spec.py`
  parametrizes four keys.
- the `[inferred]` "no entry-point command exports `WORKTREE`" sentence is gone from
  `skills/dispatching-in-session-agents/SKILL.md`. No gate is written against
  `docs/dispatch-contract.md`: that file never carried the sentence, so a gate there would
  pass without proving anything. [inferred]

## Not doing

- A `new` reserved word. Today's Create answer already covers it; the flag selects.
- A branch name that has no worktree creating one. That needs a base ref and a path; the
  `missing` + interactive branch already asks for the path.
- Relocating `in-session` leaves' relative file operations. That is a spine-wide change
  (absolute paths in every leaf prompt) and its own decision.
- Any change to `EnterWorktree` semantics or to the enter-once invariant.
- Guarding a session that already entered a worktree under an earlier relay command. The gate
  cannot see that from git state and relay keeps no session marker, so a cross-command second
  `EnterWorktree` stays the pre-existing hazard it is today. This flag does not make it worse:
  the gate still enters at most once per run. [inferred]
- Moving `apk`'s tree under `.claude/worktrees/`. Section 4 removes the reason it would
  need to. This presumes `apk` builds `.worktrees/apk/<scope>` with `git worktree add`, so
  that its git-dir differs from the common git-dir. A tree made another way — a second clone,
  or a submodule — does not classify as `worktree` under the widened rule, and section 6's
  guard is what catches it. [inferred]

## Refinement Status

Refinement: CONVERGED round 4 (relay:refining-specs, spec adapter, acpx/claude). [inferred]

Round 1: 2 critical, 6 important, 8 minor. Round 2: 2 critical, 6 important, 7 minor.
Round 3: 0 critical, 3 important, 6 minor. Round 4: 0 critical, 0 important, 3 minor —
converged. The three round-4 minors were applied after the converging round as additive
clarifications; they changed no decision. Every addition made during refinement carries an
`[inferred]` tag. [inferred]
