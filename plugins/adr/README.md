# ADR

Scaffolds an architecture-decision-record (ADR) corpus into any repository, captures a decision
the moment it is made, and answers questions about past decisions from it. An ADR corpus here is a
flat directory of frontmatter files plus a generated register, kept structurally consistent by a
standard-library-only vendored toolchain and a pytest suite.

## The bar

**Record a decision when it would be expensive to undo.** Cheap to change your mind, no ADR.
This one test governs capture, recall, grooming, and review alike.

| Earns an ADR | Does not |
|---|---|
| Chose Postgres over DynamoDB | Picked a retry count of 3 |
| Put auth at the gateway, not per service | Named a helper function |
| An event shape other services now consume | Chose a lodash utility |

## Commands and skills

Seven skills, seven commands. Capture and recall fire on their own, mid-session; the rest are
invoked by a human.

- **`/adr:setup`** — bootstrap. Detects any prior corpus, offers greenfield, adopt, or migrate,
  confirms once, then writes the corpus, `.claude/adr.json`, the vendored tooling, and both
  CLAUDE.md rule blocks. Ends only when the register indexes clean and the lint reports zero
  errors. Backed by the `scaffolding-adr-corpora` skill, which owns setup's six-step flow, and
  `scripts/scaffold.py`, the deterministic write step both the skill and this plugin's own test
  suite use.
- **`/adr:new`** — capture. Writes one ADR with `status: proposed` for a decision that is
  expensive to undo. Backed by the `authoring-adrs` skill, which also fires on its own during a
  session, mid-flow, without stopping to ask. Applies the distillation standard from
  `skills/authoring-adrs/distillation.md`.
- **`/adr:ask`** — recall. Answers a question from the corpus with `path:line` citations. Backed
  by the `consulting-decisions` skill, which is read-only by construction — its tool list holds
  only `Read, Grep, Glob` — and reads the register before opening any single ADR.
- **`/adr:index`** — regenerate the register and lint the corpus. Backed by the `indexing-adrs`
  skill, which never reports success on a red lint and never hand-edits between the generated
  markers.
- `amending-adrs` — no command of its own. Fires on its own, or from `authoring-adrs`, when a
  recorded decision changes: rewrites in place, deprecates, or supersedes with both back-links set.
- **`/adr:migrate`** — convert a legacy bold-key corpus to frontmatter with `adr_migrate.py`.
  `--frontmatter` (the default) folds bold keys and touches no filename; `--rename` also
  normalises `ADR-002-slug.md` to `0002-slug.md` and carries the register's hand-authored summary
  to the new key, because renaming changes every link that points at the file. A reference the
  converter cannot resolve to a real file is left for the lint to report, never guessed. Backed by
  `scaffolding-adr-corpora`'s migrate path, which adopts first, then converts, and stages every
  change for review — it commits nothing.
- **`/adr:check`** — the gate's model tier. Reads the diff between the current branch and its
  default branch, reports whether it contradicts an accepted ADR or ships a hard-to-reverse change
  with no ADR, and **always exits 0** — findings are advisory, and the deterministic tier is what
  the gate blocks on. Backed by the read-only `reviewing-adr-adherence` skill.
- **`/adr:groom`** — merge overlapping ADRs, retire what reality outgrew, compress prose in place,
  or archive the dead. **Always proposes a plan and shows a diff first; never rewrites silently.**
  Archiving sets `archive_dir` in `.claude/adr.json` and repairs every inbound link, including the
  register's own keys, before the next regeneration. Backed by the `grooming-adrs` skill, invoked
  by a human — it rewrites a corpus, so it does not fire on its own.

**Commands carry `disable-model-invocation: true`. Skills do not.** Commands are what a human
types. Skills are what a session reaches for on its own — this split is the mechanism that makes
the plugin engage without being asked.

## The optional gate

`templates/gate/adr-gate.yml` is a GitHub Actions workflow, offered at `/adr:setup` and written by
`scaffold.py` only when asked for (`--gate-deterministic`, `--gate-model`). Two tiers:

- **Deterministic** — `adr_lint.py` and `adr_index.py --check`. Plain `python3`, standard library
  only, no install step, runs in any CI with no key. Scopes the "still `proposed`" check to the
  files the pull request actually changed, via `--changed`, so capturing a new decision never fails
  every PR on its own.
- **Model** — `claude -p "/adr:check"`, run only when `secrets.ANTHROPIC_API_KEY` is present, with
  `continue-on-error: true` so a finding never fails the check.

## Format

```
docs/adr/0007-order-state-machine.md
```

```yaml
---
type: adr
status: proposed          # proposed | accepted | deprecated | superseded
date: 2026-08-13
title: Order state machine
area: orders               # optional, groups the register
supersedes: null
superseded_by: null
related: []
---
```

Required: `type`, `status`, `date`, `title`. **The filename is the identity — there is no `id`
field.** Cross-references (`supersedes`, `superseded_by`, `related`) hold filenames.

The parser is read-tolerant: it also reads legacy bold-key metadata (`**Status:** Accepted`) so an
existing corpus adopts unmodified and lints clean on day one, flagged only as a warning. Writers
emit frontmatter only.

## Config — `.claude/adr.json`

```json
{
  "version": 1,
  "dir": "docs/adr",
  "register": "docs/adr/README.md",
  "id_scheme": "sequential",
  "gate": {
    "deterministic": false,
    "model": false,
    "proposed_verdict": "error"
  },
  "archive_dir": null
}
```

`id_scheme` accepts `sequential` (four-digit zero-padded prefixes) or `date`
(`YYYY-MM-DD-slug.md`, for corpora like `app-platform`'s that already use it).

## What `/adr:setup` writes

The vendored tooling lands beside the corpus directory, never inside it, at three container-sibling
paths, so the corpus's own non-recursive `*.md` glob never has to exclude them:

| Destination | Origin |
|---|---|
| `scripts/adr/adr_lib.py`, `adr_new.py`, `adr_index.py`, `adr_lint.py`, `adr_migrate.py` | copied |
| `scripts/adr/requirements.txt` | copied (dev-only — `pytest`, never installed at runtime) |
| `schemas/adr/adr.schema.json` | copied |
| `tests/adr/conftest.py`, `test_adr_lib.py`, `test_adr_new.py`, `test_adr_index.py`, `test_adr_lint.py`, `test_adr_migrate.py` | copied |
| `<dir>/CLAUDE.md` | rendered (the corpus rule file) |
| `<dir>/README.md` | rendered (the register seed, empty markers) |
| `.claude/adr.json` | generated |
| `CLAUDE.md` (repo-root) | appended, never overwritten |

Re-running `/adr:setup` with `--refresh` is idempotent: it refreshes the vendored tree and the
corpus `CLAUDE.md` in place, skips the root `CLAUDE.md` append when its marker is already present,
and touches no existing ADR.

## Testing

Plugin-side and vendored tests are two separate suites, run with two separate commands, because
both trees ship a `conftest.py` with the same basename — running pytest across both roots in one
invocation raises `ImportError` on the second `conftest.py` collected. Run them separately:

```bash
python3 -m pytest plugins/adr/tests -q
cd plugins/adr && python3 -m pytest templates/verbatim/tests -q
```

The vendored suite also runs, unmodified, inside a repo after `/adr:setup`:

```bash
pip install -r scripts/adr/requirements.txt && python3 -m pytest tests/adr
```

## Invariants

1. The bar is the cost of undoing the decision. Every skill applies the same test.
2. **The filename is an ADR's identity.** No `id` field is ever written.
3. Writers emit YAML frontmatter only. Readers accept legacy bold-key as well.
4. **Vendored scripts import only the standard library.** PyYAML is optional, and its absence is a
   warning, never an error.
5. **Hand-authored register summaries survive every regeneration.** The row key is the link href.
6. **Nothing moves on disk unless `/adr:groom` is invoked.** On-disk layout is flat by default.
7. **Autonomous capture writes `status: proposed` and never interrupts.** Asking mid-session was
   rejected: it breaks flow, and in an unattended session nobody is there to answer.
8. `consulting-decisions` is read-only and reads the register before any ADR.
9. **Commands set `disable-model-invocation: true`. Skills never do.** Commands are user-typed;
   skills are what a session reaches for on its own.
10. Setup never rewrites an existing ADR unless migration was chosen explicitly. `/adr:setup`
    writes nothing if any manifest target already exists, with four idempotent exceptions: the
    repo `CLAUDE.md` append, `<dir>/CLAUDE.md`, the vendored tree, and the register.
