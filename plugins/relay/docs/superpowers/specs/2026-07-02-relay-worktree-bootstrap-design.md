# Relay v4.7.0 — Per-Worktree Bootstrap

Status: design (pending written-spec review)
Date: 2026-07-02
Plugin: `plugins/relay` — version bump 4.6.0 → 4.7.0

## 1. Problem & goals

A freshly-created `git worktree` in a pnpm/npm workspace has **no `node_modules`**
(workspace symlinks like `@scope/pkg` are absent) and **no compiled `dist/`**. So any
role that must verify its own work — `implementer`, `test-writer`, `fix-coder`,
`plan-writer` (all `isolation: worktree` in `bindings/presets.yaml`) — cannot run
`pnpm test` / `pnpm lint` / `tsc`: vitest can't resolve workspace packages and the run
fails or silently no-ops.

**Goal:** relay must bootstrap each freshly-created worktree (install deps + build) right
after it is created, driven by a **per-project** command, **before** any role runs its
verification. The motivating case is the avonrisk-sdlc pnpm monorepo, whose worktrees
need `pnpm install && pnpm build:ts`.

**Non-goals:**
- No package-manager auto-detection or hard-coded `pnpm`/`npm` — relay runs the author's
  exact command string, verbatim.
- No caching/skip layer (§6).
- No per-invocation flag — the bootstrap command is a per-project constant, declared in
  the repo (§4).
- Building the missing per-**role** worktree create/export-`WORKTREE` seam is **out of
  scope** (§7) — deferred to its own spec.

## 2. Current-state facts (recon, do not re-derive)

1. The **only** code that runs `git worktree add` is `scripts/worktree-preflight.sh`
   `_wt_create()` (~L88–140). It goes straight from `git worktree add` to printing
   `RELAY_WT_CREATED_PATH` and returning — **no post-creation setup**. This is the single
   lowest-risk seam.
2. `_wt_create()` is invoked (via `--create <base-ref> [slug]`) only by the Step 0.5 gate
   skill `skills/ensuring-worktree-isolation/SKILL.md`, in its two **Create** branches
   (`main` state → base `origin/<default>`; `stray` state → base `HEAD`). That skill
   already owns the create → enter state machine and enters via `EnterWorktree({path})`
   **exactly once**.
3. That skill already has a **failure contract** this design reuses verbatim: *"if
   `--create` returns non-zero **or** prints no `RELAY_WT_CREATED_PATH` line → abort the
   command, surface stderr, **never** call `EnterWorktree`."*
4. Per-**role** worktree isolation is currently **vestigial**: `presets.yaml` marks 4 roles
   `isolation: worktree`, but nothing creates a per-role worktree or exports `WORKTREE`;
   `acpx-dispatch.sh` (~L238) only *validates* that `WORKTREE` is already set, and
   `${WORKTREE:-$REPO_ROOT}` always resolves to `REPO_ROOT` in practice. After the Step 0.5
   gate enters the driver worktree, `REPO_ROOT` (git toplevel) **is** that worktree, so the
   `isolation: worktree` roles run their `verify_artifact: {{REPO_ROOT}}` verification
   against the driver worktree. **Therefore bootstrapping the one driver worktree fully
   covers today's behavior** — see §7.
5. There is **no** per-repo relay config file today; `presets.yaml` is plugin-global and
   per-role (wrong home for a per-project command).
6. Conventions: relay runtime tooling is bash (`.sh`) with pytest tests under
   `tests/unit/skill-structure/` that build throwaway git repos via `subprocess`
   (`test_worktree_preflight.py`). State crosses the Bash→Claude boundary as **printed
   stdout** (`KEY=value`), never env vars. Status is signaled with `[relay] note:` /
   `[relay] error:` on **stderr**. Mirror this style; do **not** use the `flows/`
   TypeScript sub-project style.

## 3. Architecture overview

Bootstrap is a **single new step inside `_wt_create()`**, between `git worktree add` and
printing `RELAY_WT_CREATED_PATH`. It runs a **repo-declared command** in the newly-created
worktree directory. Because it lives inside `_wt_create()`, it is reached **only** on the
`--create` path — i.e. only when relay creates a fresh worktree. The "proceed in place"
branches of the Step 0.5 gate (`main`/`stray` → stay in the primary checkout) never call
`--create`, and the primary checkout already has its own `node_modules`, so they correctly
get **no** bootstrap.

```
_wt_create(base_ref, slug):
  0. resolve $toplevel, $default                        (existing)
  0a. cmd = read bootstrap command from                 ← NEW (fail-fast)
        $toplevel/.claude/relay.json
      - file ABSENT → check existence first (`[ -f ... ]`) and skip jq entirely; cmd=""
        and execution continues to step 1 exactly as today — absence must never reach
        jq, since jq itself errors non-zero on a missing path indistinguishably from a
        parse failure. [inferred]
      - file present but INVALID JSON (only checked once existence is confirmed) →
        [relay] error: + return non-zero (no worktree made)
  1. git fetch origin <default>                          (existing, soft-degrades offline)
  2–4. compute slug/collision + git worktree add         (existing)
  5. if cmd non-empty:                                   ← NEW (bootstrap)
        ( cd "$candidate" && bash -c "$cmd" ) >&2
        - non-zero → [relay] error: bootstrap failed + return non-zero,
          and DO NOT print RELAY_WT_CREATED_PATH
  6. print RELAY_WT_CREATED_PATH=<abs>                   (existing)
     print RELAY_WT_BOOTSTRAP=<ran|skipped>              ← NEW (observability)
```

No other file's control flow changes. The Step 0.5 gate skill needs only a documentation
note — its existing failure contract (fact §2.3) already handles a non-zero `--create`
that prints no path.

## 4. Config surface — `.claude/relay.json`, key `bootstrap`

A per-repo JSON file at the repository root:

```json
{
  "bootstrap": "pnpm install --frozen-lockfile && pnpm build:ts"
}
```

- **Location read:** `$toplevel/.claude/relay.json`, where `$toplevel` is the **primary
  checkout** from which `--create` is invoked (`git rev-parse --show-toplevel`). Reading
  from the primary checkout — **not** the freshly-created worktree — makes the config
  robust even when a repo **gitignores `.claude/`** (a common pattern): the file exists in
  the developer's working checkout regardless of whether it is committed, and does not
  depend on being checked out into the new branch.
- **Parse:** check file existence with `[ -f "$toplevel/.claude/relay.json" ]` **before**
  invoking `jq`; a missing file never reaches `jq` and always yields `cmd=""` — only when
  the file exists does `jq -r '.bootstrap // ""'` run, and only then does a non-zero `jq`
  exit mean invalid JSON. [inferred] The value is a **string** (a shell command line);
  `&&`, `;`, pipes, etc. are the author's to use. (Array form is a possible future
  extension; **string only** for v1 — YAGNI.)
- **Opt-in / clean no-op:** if the file is **absent**, or the `bootstrap` key is **absent
  or empty**, `_wt_create()` behaves **exactly as it does today** (`RELAY_WT_BOOTSTRAP=skipped`,
  no other change). This is the common case and keeps every existing test green.
- **Trust model:** the command runs with the user's privileges in their own repo — the
  same trust already extended to any `package.json` `postinstall` script or `pnpm build`.
  No sandboxing beyond what the author's own tooling does.

### Why this home (vs. the alternatives considered)

- **vs. executable hook `.claude/relay/bootstrap`:** the hook is more flexible (arbitrary
  logic, zero quoting) but less declarative/greppable and adds an executable-bit + shebang
  convention. For "run install + build", a declarative string in a config file that can
  also host future relay per-repo settings is the better fit, and `jq` is already a relay
  dependency (`check-deps.sh`).
- **vs. lockfile autodetect (`pnpm|npm|yarn install`):** rejected as the default — auto-running
  install for **every** repo with a lockfile violates the **opt-in** requirement, cannot
  guess the un-guessable build step (`pnpm build:ts`), and adds a package-manager-detection
  surface with its own tests.

## 5. Execution semantics

- **Working directory:** the command runs with cwd = **the new worktree** (`$candidate`),
  via a subshell `( cd "$candidate" && bash -c "$cmd" )` so `_wt_create`'s own cwd is
  unchanged. It runs **before** `EnterWorktree`, which is correct: bootstrap is a
  filesystem operation on the worktree directory and does not need the session cwd to be
  there. After the gate later enters that path, `node_modules`/`dist` are already present.
- **Output routing:** `( … ) >&2` — **all** bootstrap stdout+stderr is routed to
  **stderr**, so the parseable `KEY=value` block on **stdout** stays clean (the test
  harness and the gate skill parse stdout). The user still sees install/build progress and
  errors on stderr, consistent with the `[relay] note:`/`[relay] error:` convention.
- **Environment / cross-platform:** the command inherits the same shell environment
  `worktree-preflight.sh` already runs in (`bash`). relay's worktree path already requires
  bash (the script is bash; Windows users run it under Git Bash/WSL), so bootstrap adds
  **no new platform assumption**. Because no package manager is hard-coded, the
  pnpm/corepack/Windows path is entirely whatever the repo already uses. (Research: pnpm
  officially supports git-worktrees; the documented corepack/Windows symlink caveats are
  general, not worktree- or relay-specific.)

## 6. Idempotency / caching — none in relay

`_wt_create()` runs **once per worktree creation**, and a fresh worktree never has
`node_modules` (gitignored, absent on checkout), so there is nothing to cache against and
no double-run within relay. relay adds **no** skip/caching logic. Two supporting facts:

- pnpm's content-addressable global store + hardlinks make a warm-store `pnpm install` in
  a new worktree **cheap** (no re-download; reconstructs the local virtual store via
  hardlinks/symlinks). Concurrent installs across worktrees are safe (pnpm coordinates
  store access; each worktree has its own isolated `node_modules`). Workspace symlinks
  resolve normally inside a worktree.
- The author's command should be idempotent if they care (`pnpm install` is). If they want
  CI-strict reproducibility, `pnpm install --frozen-lockfile` is the recommended flag
  (fails fast on lockfile drift, never mutates the lockfile).

## 7. Scope decision — driver worktree only

This spec bootstraps **only** the single worktree created by `_wt_create()` at the Step
0.5 gate. Per fact §2.4, that is where the `isolation: worktree` roles actually run today
(`${WORKTREE:-$REPO_ROOT}` → the entered driver worktree), so it **fully solves** the
avonrisk acceptance case.

Building the missing **per-role** create-and-export-`WORKTREE` seam (so each
`isolation: worktree` role gets its own worktree) is a **separate, larger feature** that
touches Workflow generation, `acpx-dispatch.sh`, and the bindings — deferred to its own
spec. When that lands, it can reuse this same `_wt_create()` bootstrap step per role
worktree unchanged.

## 8. Error handling — hard-fail, reusing the existing contract

| Condition | Behavior |
|---|---|
| No `.claude/relay.json`, or `bootstrap` absent/empty | Clean no-op. `RELAY_WT_BOOTSTRAP=skipped`. Worktree created as today. |
| `.claude/relay.json` present but **invalid JSON** | `[relay] error: .claude/relay.json is not valid JSON` on stderr; **return non-zero before creating any worktree**. (A present-but-broken config is an author error worth surfacing crisply, not silently ignoring — otherwise the exact symptom we are fixing reappears downstream as confusing test failures.) |
| Bootstrap command exits **non-zero** | `[relay] error: bootstrap failed (exit N)` on stderr; **return non-zero and do NOT print `RELAY_WT_CREATED_PATH`.** The gate skill's existing contract (§2.3) then aborts the command and never calls `EnterWorktree`. |
| Bootstrap command exits **zero** | Print `RELAY_WT_CREATED_PATH` + `RELAY_WT_BOOTSTRAP=ran`. |

**Why hard-fail (not soft-degrade) on bootstrap error:** this mirrors the script's own risk
logic. `git fetch` soft-degrades because failure is recoverable (create off the local
base). A failed bootstrap is **not** recoverable — a worktree with missing deps or a broken
build makes **every** downstream role's verification meaningless (false failures or silent
no-ops), which is worse than a crisp early abort. On failure the half-created worktree dir
is left on disk (not auto-removed — the user may want to inspect it); the existing `-N`
collision-suffix logic (`_wt_create` guards both the dir and the `relay/<slug>` branch)
handles a subsequent retry cleanly.

## 9. Tests (`tests/unit/skill-structure/test_worktree_preflight.py`, `TestCreate`)

Mirror the existing throwaway-repo style (`_origin_repo`, `_run`, `_parse`). Add:

1. **No config → no-op regression:** existing `test_create_*` cases already prove
   `--create` works with no `.claude/relay.json`; add an explicit assertion that
   `RELAY_WT_BOOTSTRAP=skipped` and the worktree is created.
2. **Bootstrap runs in the worktree:** write `.claude/relay.json` with
   `{"bootstrap": "touch BOOTSTRAP_RAN"}` in the clone; assert the created worktree
   contains `BOOTSTRAP_RAN`, `RELAY_WT_CREATED_PATH` is printed, and
   `RELAY_WT_BOOTSTRAP=ran`.
3. **Bootstrap runs in the NEW worktree, not the primary checkout:** assert
   `BOOTSTRAP_RAN` exists under `RELAY_WT_CREATED_PATH` and does **not** exist in the
   primary clone root.
4. **Failing bootstrap hard-fails:** `{"bootstrap": "exit 3"}` → `--create` returns
   non-zero, prints **no** `RELAY_WT_CREATED_PATH`, and stderr contains `[relay] error`.
5. **Empty bootstrap key → no-op:** `{"bootstrap": ""}` → worktree created,
   `RELAY_WT_BOOTSTRAP=skipped`.
6. **Invalid JSON → hard-fail before creation:** `.claude/relay.json` = `{not json` →
   non-zero, `[relay] error`, and **no** new worktree registered in `git worktree list`.
7. **stdout stays clean:** with a chatty bootstrap (`{"bootstrap": "echo noise"}`), assert
   the parsed stdout block contains only `RELAY_WT_*` keys (no `noise` leaking into the
   `KEY=value` stream) — proves the `>&2` routing.

## 10. Files touched

| File | Change |
|---|---|
| `scripts/worktree-preflight.sh` | Add config read (fail-fast on invalid JSON) + bootstrap step inside `_wt_create()`; emit `RELAY_WT_BOOTSTRAP`; update the header comment documenting the new `--create` step. |
| `skills/ensuring-worktree-isolation/SKILL.md` | Short note: `--create` now also runs the per-repo bootstrap; its failure is already covered by the existing "no `RELAY_WT_CREATED_PATH` → abort" contract; mention `RELAY_WT_BOOTSTRAP` in the printed block. |
| `tests/unit/skill-structure/test_worktree_preflight.py` | New `TestCreate` cases (§9). |
| `docs/superpowers/references/relay-repo-config.md` (new) | Document the `.claude/relay.json` `bootstrap` key for repo authors, with the avonrisk `pnpm install --frozen-lockfile && pnpm build:ts` example, plus a one-line pointer from `skills/using-relay/SKILL.md`. |
| `CHANGELOG.md` | New `## 4.7.0 — 2026-07-02` entry. |
| `.claude-plugin/plugin.json` | Version `4.6.0` → `4.7.0`. |

## 11. Risks

- **R1 — Slow bootstrap blocks the gate.** `pnpm install && pnpm build` can take minutes;
  the Step 0.5 gate runs in MAIN, so the session waits. Accepted: this is inherent to
  "bootstrap before verification", output streams to stderr so the user sees progress, and
  a warm pnpm store keeps it cheap. No timeout in v1 (a partial-timeout would leave a
  broken tree — worse than waiting). This is relay's own choice not to impose an
  *internal* timeout; it does not override whatever external ceiling the calling
  harness's own command-execution tool already imposes on a single invocation (commonly
  on the order of minutes). The skill that invokes `--create` should request the longest
  timeout that tool allows, and repo authors should keep a cold-cache (no warm pnpm
  store) bootstrap command's expected runtime comfortably under that external ceiling.
  [inferred]
- **R2 — Author command has side effects outside the worktree.** The command is arbitrary
  and trusted (author's own repo); relay does not sandbox it. Documented as author
  responsibility.
- **R3 — `.claude/` gitignored so the worktree lacks the config.** Mitigated by design: the
  config is read from the **primary checkout** `$toplevel`, not the worktree (§4).

## Refinement Status

**Refinement: CONVERGED round 2**

Round 2: convergence check found no critical/important findings. Three minor observations
remain unaddressed by design choice (non-string `bootstrap` value behavior left undefined
for v1; whitespace-only bootstrap strings are inert but harmless; the §11 R1 timeout
recommendation isn't separately itemized in the §10 files-touched row for
`skills/ensuring-worktree-isolation/SKILL.md` — a plan-writer reading the full spec will
still catch it).

Round 1 changes: closed two important gaps found by spec-simulation. (1) §3 step 0a / §4
Parse — the pseudocode named only the "file present but invalid JSON" branch and never
stated that file-**absence** must be checked (`[ -f ... ]`) *before* invoking `jq`; a naive
implementation running `jq` unconditionally would hard-fail the common no-config case
(`jq` errors non-zero on a missing path exactly like a parse failure), contradicting §8 row
1 and §9 test 1. Added explicit existence-check-first ordering to both §3 and §4. [inferred]
(2) §11 R1 — the risk discussion only addressed relay's own choice not to add an *internal*
bootstrap timeout, without acknowledging that the calling harness's own command-execution
tool already imposes an *external* hard timeout ceiling on a single invocation, independent
of relay's choice. Added a sentence recommending the invoking skill request the longest
timeout that tool allows, and that repo authors keep cold-cache bootstrap runtime
comfortably under that ceiling. [inferred]
