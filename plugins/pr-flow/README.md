# PR Flow

Repo-tailored PR review as an installable Claude Code plugin. Good PR review is
repo-specific — the concerns that matter in a healthcare monorepo (PHI, GraphQL contract
breaks, module boundaries) are not the concerns that matter in a small Go service or a
marketing site. `pr-flow` **bootstraps** a review system tailored to *your* repo, then
**executes** it.

The plugin ships two halves that meet at a single interface: **the contract file in the
target repo** (`.claude/pr-flow/contract.md`). Bootstrap writes it; the executor reads it.
Neither half hardcodes the other's concerns.

## Half 1 — Bootstrap: `/pr-flow:setup`

Interactive, idempotent command (backed by the `bootstrapping-pr-flow` skill) that inspects
your repo and generates a tailored review system into it:

1. **Detect prior state** — if a contract or generated lenses already exist, fold in new
   findings rather than clobbering human edits.
2. **Mine four sources** for candidate concerns:
   - GitHub PR review history via `gh` (past comments, requested changes, recurring
     objections) — the richest "what humans actually flag here" signal; gracefully skipped
     when `gh` is absent/unauthenticated or there is no GitHub remote.
   - Repo docs & conventions (CLAUDE.md, CONTRIBUTING.md, PR/issue templates, ADRs,
     CODEOWNERS, style guides).
   - Git history & codebase shape (languages, layout, tests, CI config, presence of GraphQL
     schema / IaC / UI packages).
   - Existing review artifacts (prior lenses, prior contract, saved reports).
3. **Reason → draft** a candidate concern checklist, each with its evidence.
4. **Interrogate you** — confirm / add / drop each concern, capture repo invariants, and
   record the repo's deterministic gate commands (the exclusion set).
5. **Generate** — write the contract and scaffold one lens skill per confirmed concern, then
   emit a receipt of what was written.

### What it writes into the target repo

```
.claude/pr-flow/contract.md          THE CONTRACT — single source of truth
.claude/skills/reviewing-<concern>/  one generated lens skill per confirmed concern
  └── SKILL.md
```

## The contract — `.claude/pr-flow/contract.md`

Markdown, human-editable, read by **all** executor skills. Four sections:

1. **The Bar** — what a finding must clear to be reported: *real* (concretely true in this
   diff, with evidence) **and** *impactful if left unattended*. Report or drop, and report the
   important findings only — silence is the default, and no lens is measured by how much it
   returns. A reported finding then gets one of three labels: **must-fix** (the only one that
   holds up approval), **should-fix**, or **note** — should-fix and note are written in two
   short sentences at most and never hold up approval. Must-fix needs all four parts of the
   Bar's must-fix test: a named wrong result, a trigger that exists today, a line in this diff,
   and one of six closed damage classes. When unsure, use the lower label. The Bar also carries
   the ASD-STE100 voice rule that every line of review text obeys.
2. **Deterministic gates (never re-flag)** — the repo's own lint/typecheck/CI/secret-scan
   commands, discovered at setup. A lens must never surface what a gate already owns; the
   lifecycle skills run these as the CI-equivalent gate.
3. **Repo invariants** — the mined, repo-specific rules.
4. **Lens registry** — the authoritative list of active lenses, as a Markdown table
   (`| name | when | skill path |`; see `templates/the-bar.md` §4 for the row grammar), where
   `name = basename(skill path)` (e.g. `reviewing-naming -> .claude/skills/reviewing-naming`). The
   orchestrator reads this to decide which lenses to fan out for a diff, and invokes each by
   its bare skill name (`reviewing-<concern>`) via the Skill tool. The registry lists this repo's
   lenses. The plugin's own `reviewing-goal-achievement` lens runs on every review and needs no
   row.

## Half 2 — Execute

Shipped skills that run the review against the generated contract:

- **`reviewing-prs`** — repo-agnostic orchestrator. Reads the contract's Bar and Lens
  registry, triages which lenses apply to the diff, fans them out adversarially via the
  Workflow tool, filters/verifies findings against the Bar, and emits a coverage-receipt
  report. With no contract it runs in goal-only mode: it tells you to run `/pr-flow:setup`, it
  runs the built-in goal lens only, and it never approves.
  **Local and read-only by default**; two flags opt into GitHub, and a third names the target:
  | Flag | Effect |
  |------|--------|
  | *(none)* | In-session report. No GitHub writes. |
  | `--comment` | Post the report to the PR as a comment. |
  | `--approve` | Post it **and** approve when the report has no must-fix finding — should-fix entries and notes are posted with the approval, not against it. A must-fix finding degrades it to a comment, and says why. It approves only when the goal verdict is `achieved` or `partially achieved`. |
  | `--pr <number>` | Names which PR the posting flags target, when the branch doesn't resolve to one. On its own it writes nothing. It reviews the working tree either way, and refuses to post if that tree isn't the PR's head. |

  These flags are also how `scheduling-pr-reviews` posts: the loop picks a posture and then calls
  this skill with it (`--comment` for *Comment-only*, `--comment --approve` for
  *Approve-when-clean*) rather than carrying its own posting code. So this is the **single** place
  pr-flow writes a verdict, and ad-hoc and scheduled runs agree on a PR by construction. A
  `head=<sha> lenses=<n> intent=<digest>` marker makes a re-run at an unchanged head and an
  unchanged PR title and body a no-op rather than a duplicate comment — and because both entry
  points post through here, that dedupe covers both. The `intent` digest is in the key because an
  edited title, body, or closed issue can change the goal verdict without moving the head.

- **`reviewing-goal-achievement`** — the one lens the plugin ships. It reads the PR title and
  body, **every issue the PR closes with a `fixes` or `closes` keyword**, every plan or spec the
  diff changes, and the commit messages. A body that only says `Fixes #7` therefore states its
  goal in issue 7, and the lens checks the diff against that issue. It returns one verdict:
  `achieved`, `partially achieved`, `not achieved`, or `undetermined`. Every review runs it, and
  every report carries a `**Goal check:**` line. A `not achieved` verdict and an `undetermined`
  verdict each withhold `--approve`. The verdict alone is never a must-fix finding.
- **`getting-prs-green`** — drives a single PR's checks to all-green: syncs the branch with its
  base first (a stale branch's checks don't describe what merge will produce), then fetches the
  failure logs, fixes, gates locally, and pushes — round after round until CI is green or a cap
  or escalation stops it. Never merges, never approves, never suppresses a finding.
- **`getting-prs-approved`** — drives a single PR to approval by answering every review comment,
  running the contract's discovered gates as the CI-equivalent.
- **`getting-prs-merged`** — drives an approved PR to merged.
- **`scheduling-pr-reviews`** — routine review of open PRs on a cron cadence. Owns *when* and
  *which*; delegates the review **and the post** to `pr-flow:reviewing-prs` with the chosen
  posture's flags. It never states the Bar, never enumerates lenses, and never writes to GitHub
  itself.

### Shared references

Behaviour common to several executor skills lives once, in `references/`, and each SKILL.md links
what it needs directly — one level deep, so nothing is reached only through another reference:

| File | Owned behaviour | Read by |
|------|-----------------|---------|
| `references/github-access.md` | Resolving `$REPO`/`$N`/`$HEAD_REF`/`$BASE_REF`, and the `gh`-vs-MCP probe | all five executor skills; `bootstrapping-pr-flow` for the `gh` probe |
| `references/loop-engine.md` | The shared control loop: pacing, the GitHub-thread ledger, worker liveness, the local gate, escalation | the three `getting-prs-*` skills |
| `references/base-sync.md` | `update-branch` vs. conflict rebase, worktree hygiene, `--force-with-lease` | `getting-prs-green`, `getting-prs-merged` |

Skill-specific detail stays next to its skill: `reviewing-prs/references/posting.md` (loaded only
when a posting flag is passed) and `getting-prs-approved/references/codeowners.md`.

## Flow

```
/pr-flow:setup  ─writes─▶  .claude/pr-flow/contract.md + .claude/skills/reviewing-*
                                     │
                                     ▼
        reviewing-prs (+ lifecycle skills) ─read the contract─▶ tailored review
```

## Templates (generator reference, not active skills)

`templates/the-bar.md` (the contract archetype) and `templates/lens-shape.md` (the single
generic lens structure) are what the bootstrap generator instantiates. The plugin ships one
process lens (`reviewing-goal-achievement`) and **no domain lens catalog** — the plugin models
the review *process*; a domain lens is only a list of `flag:` lines, each with a measurable
condition, plus `do not flag:` exclusions — generated from the target repo's own mined evidence
and the user's answers at setup time. All review policy lives in the contract and in the
`reviewing-prs` dispatch prompt, never in a lens. Lenses are pure
extension points.
