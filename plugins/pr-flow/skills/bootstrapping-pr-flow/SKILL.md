---
name: bootstrapping-pr-flow
description: Generates a repo-specific PR-review system for the repository it is invoked in. Mines the repo's PR review history, docs, and codebase shape to infer the review concerns that matter here, confirms them with the user, then writes .claude/pr-flow/contract.md (The Bar + deterministic gates + repo invariants + lens registry) and scaffolds one .claude/skills/reviewing-* lens skill per confirmed concern. Idempotent. Use for "/pr-flow:setup", "bootstrap pr-flow", "set up PR review for this repo", or "generate review lenses".
argument-hint: "[concerns to emphasise]"
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, AskUserQuestion
---

# bootstrapping-pr-flow

Stand up a tailored PR-review system inside the repository you are invoked in. Two things land in
the **target repo** (never in the plugin):

- `.claude/pr-flow/contract.md` — the single source of truth (four sections).
- `.claude/skills/reviewing-<concern>/SKILL.md` — one generated lens per confirmed concern.

The executor half (`pr-flow:reviewing-prs` and the lifecycle skills) reads that contract at review
time. Do the analysis quietly; surface only the draft checklist and the questionnaire.

Read both templates before generating: `${CLAUDE_PLUGIN_ROOT}/templates/the-bar.md` is the contract
archetype, `${CLAUDE_PLUGIN_ROOT}/templates/lens-shape.md` the single lens shape. The plugin ships
**no domain lens catalog** — every lens's content comes from THIS repo's mined evidence and the
user's confirmed answers; the shape template only fixes the structure.

The plugin ships one process lens, `pr-flow:reviewing-goal-achievement`. That lens compares the
PR's stated goal with the diff. It reads the goal from the PR title and body, from every issue
the PR closes, from any plan or spec the diff changes, and from the commit bodies. It is built
in, it runs on every review, and this skill never generates it.

## Step 0 — Resolve the target repo

```bash
git rev-parse --show-toplevel                      # abort if this fails: not a repo
gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null \
  || git remote get-url origin 2>/dev/null          # may be empty — that's fine
```

Unlike the executor skills, this one runs fine with no GitHub remote at all — it just loses Source
1. Everything you write goes under `<repo-root>/.claude/`. Never write into the plugin dir.

## Step 1 — Detect prior state (idempotent)

```bash
ls .claude/pr-flow/contract.md 2>/dev/null
ls -d .claude/skills/reviewing-* 2>/dev/null
```

Nothing exists → fresh install; continue. Something exists → ask the user (AskUserQuestion, single
question) to choose:

- **Update (fold in)** — keep the existing contract as the base, mine again, merge new signal in.
  **Fold-in rule:** dedup by concern name (registry `name` = `reviewing-<concern>` basename); where
  a concern already exists, the human-edited row/lens is authoritative and you only propose
  *additions*. Preserve hand-edited repo invariants and gate commands verbatim — surface proposed
  changes for confirmation rather than overwriting.
  **One exception, and it is not optional:** the contract's fixed policy text is replaced with the
  current template's wording, even in Update mode. It is plugin policy, not repo content, so an
  old copy is stale rather than hand-edited. That text is the **Bar** — the report-or-drop rule,
  the **"Report important findings only"** paragraph, the whole **Three severities: MUST FIX,
  SHOULD FIX, NOTE** subsection (its heading through its **use-the-lower-label** rule), plus
  **Voice — ASD-STE100**. Replace only that block; the contract's impact categories follow the
  normal fold-in rule.

  A lens carries no policy text. Its body is the `flag:` / `do not flag:` list and the fixed body
  paragraph that says to read the diff against the list. A lens generated before this version is an
  essay: a `## Step 1` block, a `**The rule**` section, and `**Flag if:**` / `**Do not flag:**`
  bullet lists. Rewrite it into the new shape — the fixed body paragraph, then one `- flag:` line
  per Flag-if bullet and one `- do not flag:` line per Do-not-flag bullet — and delete the `## Step
  1` block, the rule prose, and every heading below the title. Do this in Update mode too, because
  the executor's dispatch prompt now owns every rule the essay stated. Say in the receipt which
  files you refreshed. Without this, "run `/pr-flow:setup` to refresh the Bar" is advice that
  changes nothing.
- **Fresh (regenerate)** — rebuild from scratch. Warn that this replaces the contract and the
  generated `reviewing-*` lenses.

The chosen mode changes Step 5's write behaviour only.

## Step 2 — Mine four sources

Gather evidence quietly and **concurrently**, so the network `gh` call (Source 1) does not block the
three local sources. Each source is best-effort: a missing one degrades gracefully and is noted in
the receipt, never fatal.

### Source 1 — GitHub PR review history (richest; graceful-skip)

The strongest "what humans actually flag here" signal. Probe `gh` per
[references/github-access.md](../../references/github-access.md) § *Probe access* — in particular,
retry a failed `gh auth status` as `env -u GH_TOKEN gh auth status`, since a stale `GH_TOKEN` in the
environment is the usual reason this source skips when it shouldn't. If `gh` is still
unauthenticated, absent, or there is no GitHub remote, note "PR history: skipped (no
gh/auth/remote)" and move on.

```bash
gh pr list --state merged --limit 40 --json number -q '.[].number'   # tune limit to repo volume
for n in $PR_NUMBERS; do
  gh api "repos/OWNER/REPO/pulls/$n/comments" --jq '.[].body'
  gh api "repos/OWNER/REPO/pulls/$n/reviews"  --jq '.[] | select(.state=="CHANGES_REQUESTED" or .body!="") | .body'
done
```

Cluster the collected bodies into recurring themes (naming, tests, security, PHI/data-handling,
module boundaries, GraphQL/API contracts, infra, ADRs, UI, …) and count how often each recurs —
frequency is the evidence.

### Source 2 — Repo docs & conventions (local)

Read where stated rules live: `CLAUDE.md`, `CONTRIBUTING.md`, `README`,
`.github/PULL_REQUEST_TEMPLATE*`, `CODEOWNERS`, `docs/adr/**` or `docs/decisions/**`, and any
`STYLE`/`CONVENTIONS` docs.

```bash
ls CLAUDE.md CONTRIBUTING.md .github/PULL_REQUEST_TEMPLATE* 2>/dev/null
git ls-files 'docs/adr/*' 'docs/decisions/*' 'CODEOWNERS' '.github/CODEOWNERS' 2>/dev/null
```

Explicit stated rules become **repo invariants** in the contract.

### Source 3 — Git history & codebase shape (local)

Infer likely risk areas from structure and tooling: languages and package managers
(`package.json`, `go.mod`, `pyproject.toml`, `Cargo.toml`); a GraphQL schema (`*.graphql`, `*.sdl`),
IaC (`*.tf`, `k8s/**`, `helm/**`), UI packages (`apps/**`, `packages/**/ui*`, `*.tsx`); test setup
and CI config; monorepo/service boundaries.

```bash
git ls-files | sed 's#/.*##' | sort -u          # top-level shape
ls .github/workflows/ 2>/dev/null                # CI = likely gate source
```

CI workflow steps and `package.json`/`Makefile` scripts are the primary source of the
**deterministic gates** you confirm in Step 4.

### Source 4 — Existing review artifacts (local)

Fold in any prior `.claude/skills/reviewing-*/SKILL.md`, prior `.claude/pr-flow/contract.md`, and
saved review reports. In update mode these seed the baseline registry and invariants.

## Step 3 — Reason → draft a checklist of concerns

Synthesise the four sources into candidate concerns, each with its evidence, a proposed
`reviewing-<concern>` name, and a **draft list of `flag:` lines** — two to eight per concern, each
a condition a reviewer can count or match in a diff, in the shape Step 5b defines. `flag: a function
with more than 20 lines` is a flag line. `flag: functions that are too long` is not. That draft
list is what Step 5 writes into the lens body. Present it:

```
Proposed review concerns for OWNER/REPO:
- reviewing-graphql-contract  evidence: schema present (api/schema.graphql) + 3 merged PRs flagged breaking changes
    flag: a field, type, or argument removed from `api/schema.graphql`
    flag: a field type changed from nullable to non-null in `api/schema.graphql`
- reviewing-security          evidence: auth/ + gateway/ dirs; 2 PRs requested changes on token handling
    flag: a token, secret, or password value written to a log call under `auth/**` or `gateway/**`
    flag: a new route under `gateway/**` with no call to `requireAuth`
- reviewing-tests             evidence: CONTRIBUTING requires tests for new routes
    flag: a new file under `api/routes/**` with no new or changed file under `api/routes/**/__tests__/**`
    flag: a changed handler under `api/routes/**` with no changed file under `api/routes/**/__tests__/**`
- reviewing-naming            evidence: CLAUDE.md "canonical component naming" section
    flag: a component name in `**/*.tsx` that is not in the repo's component inventory doc
    flag: a file under `src/components/**` whose basename does not equal its default export name
Deterministic gates detected (candidates to exclude): pnpm build, pnpm lint, pnpm typecheck, pnpm test
```

Propose only concerns with real evidence — no padding with generic bug-finding, which is the
`code-review` plugin's job. Name any skipped source here.

## Step 4 — Interrogate the user (AskUserQuestion)

Three batched questions, defaults pre-filled from the mining. Everything confirmed here is written
verbatim into the contract.

1. **Confirm / drop concerns** — multi-select over the proposed set, plus an "add another" path for
   a concern the mining missed (capture its name and at least two `flag:` lines, each with a threshold).
2. **Repo invariants, each marked `[blocking]` or `[advisory]`** — confirm the mined ones and let
   the user add repo-specific rules the review must enforce (e.g. "gateway-only persistence", "no
   secrets in fixtures", "public API changes need an ADR"). Ask, per invariant, which marker it
   gets. `[blocking]` means a break can hold up approval — it is damage class 6 in the Bar.
   `[advisory]` means a break is reported but never holds up approval. **Default to `[advisory]`**
   and make the user choose `[blocking]` on purpose. A process rule (commit-message style,
   changelog wording) is `[advisory]`. Mark `[blocking]` only where a break causes one of the
   Bar's other five damage classes.
3. **Deterministic gates (the exclusion set)** — the **exact commands** the repo's CI already runs
   (build, lint, typecheck, test, format-check, secret-scan), so lenses never re-flag what a gate
   owns. Pre-fill from Source 3 and ask the user to correct the exact invocation (e.g.
   `pnpm turbo run build lint typecheck test`, `go vet ./... && go test ./...`, `make ci`). Record
   the wrong commands here and the lenses will re-flag lint and type errors, drowning the real
   findings — this is the single most important thing to get exactly right.

## Step 5 — Generate

Write the target-repo files, creating parent dirs as needed (`mkdir -p .claude/pr-flow
.claude/skills`).

### 5a — The contract (`.claude/pr-flow/contract.md`)

Fill the four-section archetype from `${CLAUDE_PLUGIN_ROOT}/templates/the-bar.md`:

1. **The Bar** — keep the archetype's generic definition (a finding must be *real* AND *impactful*)
   but tailor its impact categories to THIS repo's concerns and invariants; drop the template's
   healthcare example rows rather than copying them.

   **Copy these things verbatim:** the "report or drop" paragraph, the "report important findings
   only" paragraph, and the whole **Three severities: MUST FIX, SHOULD FIX, NOTE** subsection —
   its heading through its use-the-lower-label rule — plus the **Voice — ASD-STE100** subsection.
   The first two sit above the `### Three severities` heading;
   take them by name, not by position. These are plugin policy, not repo content. A repo that
   re-tiers them gets an executor that withholds approval for small things. A repo that drops the
   caps gets a review that nobody reads.

   **The six damage classes are a closed list. Do not add a class, do not remove one, and do not
   re-word one.**

   The impact categories in test 2 are the **only** part of §1 you tailor. Tailoring them changes
   what is reportable. It never changes the must-fix test, which is the closed list above.
2. **Deterministic gates (never re-flag)** — the exact commands from Step 4, one per line, **each
   followed by a short scope note naming what it owns**: `` `npm run lint` — formatting, style,
   unused vars, import order `` / `` `npm run typecheck` — type errors, missing/incompatible
   signatures ``. The command alone is not enough — at review time the executor must decide whether
   a candidate finding is gate-owned, and it cannot infer that from an invocation string. Where a
   gate's coverage is unusual (a lint config that also enforces doc comments or naming), say so;
   that is exactly the boundary a lens would otherwise double-flag.
3. **Repo invariants** — the confirmed invariants from Step 4, each written with its `[blocking]`
   or `[advisory]` marker first, as `templates/the-bar.md` §3 shows. An invariant with no marker
   reads as `[advisory]`, so write the marker on every bullet.
4. **Lens registry** — one row per confirmed concern, as the **Markdown table** defined in
   `${CLAUDE_PLUGIN_ROOT}/templates/the-bar.md` §4. The registry lists this repo's lenses only.
   One plugin lens, `pr-flow:reviewing-goal-achievement`, runs on every review, and it needs no
   row. Do not write a row for it. The executor parses what you write here, so the
   table is the interface; do not invent a different shape. Columns are `| name | when | skill path |`,
   where **`name` = the basename of the skill path = `reviewing-<concern>` = the lens's frontmatter
   `name` = the exact token the orchestrator passes to the Skill tool** — keep all four identical or
   triage breaks. The `when` column holds **file globs** (`**/*.ts`, `api/**`) and/or **change-type
   keywords** (`touches-data-model`, `renames-component`, `changes-public-api`); non-glob
   change-types are always-considered by the orchestrator and the lens self-filters.

   ```
   ## 4. Lens registry

   | name | when | skill path |
   |------|------|------------|
   | reviewing-naming | `**/*.ts`, `docs/**`, `renames-component` | `.claude/skills/reviewing-naming` |
   | reviewing-security | `auth/**`, `gateway/**` | `.claude/skills/reviewing-security` |
   | reviewing-graphql-contract | `**/*.graphql`, `changes-public-api` | `.claude/skills/reviewing-graphql-contract` |
   ```

In **update** mode apply the Step 1 fold-in rule: merge new rows, dedup by `name`, preserve
human-edited rows, invariants, and gate commands.

### 5b — The lens skills (`.claude/skills/reviewing-<concern>/SKILL.md`)

Instantiate `${CLAUDE_PLUGIN_ROOT}/templates/lens-shape.md` per confirmed concern, filling every
`<placeholder>`:

- Frontmatter `name:` **must equal** the directory basename `reviewing-<concern>`. Write a
  repo-specific one-line `description`.
- **Write no policy text into a lens.** The Bar, the three labels, the note cap, the voice rule,
  the `ATTEMPTED-BUT-HELD` list, and the "say nothing about the checks" rule all live in the
  contract and in the `reviewing-prs` dispatch prompt. A lens that restates them drifts from them.
  Keep the shape's body paragraph as written. Do NOT introduce a `${CLAUDE_PLUGIN_ROOT}`
  path or a `pr-flow:`-namespaced reference; generated lenses are bare-name repo skills.
- Fill **the `flag:` / `do not flag:` list** entirely from THIS repo's evidence. The body of a lens
  is that list and nothing else: no source citation, no "read first" pointer, no rule essay, no
  quoted paragraphs, no history. Where a line needs a file to judge it, name the file inside the
  line (`… against `ls plugins/relay/roles/*.md``). The Step 3 draft is the input; the confirmed
  Step 4 answers may add or drop lines.
  - Each `flag:` line is one condition a reviewer can count or match in a diff. Put the threshold
    in the line wherever one exists — a number (`more than 20 lines`, `5 or more identical
    lines in 2 or more files`), a path pattern (`src/api/**`), a key (`"version"`), a command, an
    identifier. A line with no measurable part is allowed only when the evidence gives none; then
    name the observable that two reviewers would agree on.
  - Each `do not flag:` line names one adjacent change the list does not govern, or one thing a
    command in the contract's Deterministic-gates section owns — name that command, or the other
    lens that owns it.
  - Two to eight `flag:` lines per lens. A lens that needs more than eight is two concerns.

  The plugin carries no domain content to copy — if you cannot write the lines from the repo's
  evidence plus the Step 4 answers, the concern was not confirmed well enough; go back rather than
  inventing a generic list. Delete the shape's worked-example comment block.
- In update mode, do not overwrite a hand-edited lens unless the user chose fresh.
- Do not generate a lens that compares the PR body with the diff, and do not generate one that
  checks the diff against a closed issue. `pr-flow:reviewing-goal-achievement` already does both.
  Two goal lenses give two verdicts on one pull request.

**Proofread each generated lens before writing the next.** These files are prompts the executor
follows literally, so a typo in a structural marker degrades review silently — a mangled
`do not flag:` prefix means the lens loses its exclusion list and starts reporting gate-owned
noise. Re-read each file and confirm: frontmatter parses, `name:` matches the directory, every
list item starts with `- flag: ` or `- do not flag: `, at least two `- flag: ` items and one
`- do not flag: ` item exist, the body holds no heading below the title and no paragraph other
than the fixed body paragraph, and no `<placeholder>` or worked-example block survives.

### 5c — Receipt

```
pr-flow setup complete for OWNER/REPO (mode: fresh|update)

Contract:  .claude/pr-flow/contract.md
  Gates:      pnpm build, pnpm lint, pnpm typecheck, pnpm test
  Invariants: 3
  Lenses:     4

Generated lenses:
  .claude/skills/reviewing-naming/SKILL.md
  .claude/skills/reviewing-security/SKILL.md
  .claude/skills/reviewing-tests/SKILL.md
  .claude/skills/reviewing-graphql-contract/SKILL.md

Built-in lens (always runs, never generated):
  pr-flow:reviewing-goal-achievement

Sources: PR history (28 PRs), docs (CLAUDE.md, CONTRIBUTING.md), codebase shape, prior artifacts (none)
Next: run pr-flow:reviewing-prs on a branch to review a PR against this contract.
```

Name any skipped source (e.g. "PR history: skipped — gh not authenticated") so the user knows the
contract rests on local signal only and can re-run after `gh auth login`.
