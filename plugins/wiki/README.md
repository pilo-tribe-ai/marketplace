# Wiki

Scaffolds a persistent, OKF v0.2-conformant knowledge wiki into any repository, ingests sources
into it, then answers questions from it. A knowledge wiki here is a fixed five-type bundle
(`Source`, `Entity`, `Concept`, `Synthesis`, `OpenQuestion`) built from raw sources dropped into
`raw/`, kept structurally consistent by three deterministic scripts and a vendored pytest suite.

## Three commands, one interface

- **`/wiki:setup`** — bootstrap. Detects any prior wiki, infers the subject, the repo name, the
  human and agent actor strings, and the container path, confirms once, then writes the container
  skeleton and an empty five-type bundle. Ends only when all four gates pass on that empty bundle.
  It never ingests.
- **`/wiki:ingest`** — the executor. Reads `.claude/wiki.json` to find the container, then runs
  the Ingest operation `AGENTS.md` defines end to end: save the raw source, extract entities and
  concepts, write or update pages, regenerate indexes, append the log, run all four gates.
- **`/wiki:ask`** — the reader. Reads `.claude/wiki.json` to find the container, then runs the
  Query operation `AGENTS.md` defines: read the index, rank and read candidate pages, cite every
  claim, and offer to file a durable answer back as a draft Synthesis page. It answers from wiki
  pages only. It never answers from outside the wiki.

Backed by two skills: `wiki:scaffolding-okf-wikis`, which owns setup's six-step flow, and
`wiki:answering-from-okf-wikis`, which owns the Query operation behind `/wiki:ask`. Setup also
calls `scripts/scaffold.py`, the deterministic write step both the skill and this plugin's own
test suite use.

The three commands meet at a single interface: **`.claude/wiki.json`** in the target repo,
written by setup and read by `/wiki:ingest` and `/wiki:ask`. It holds `{container, okf_version,
plugin_version}`.

## What `/wiki:setup` writes

23 files plus one append — 22 inside the container, `.claude/wiki.json` outside it, and one
appended block in the target repo's `CLAUDE.md`.

| Path (container-relative unless noted) | Origin |
|---|---|
| `scripts/check_okf.py`, `scripts/check_links.py`, `scripts/regen_indexes.py` | copied |
| `requirements.txt` | copied |
| `tests/conftest.py`, `tests/test_check_okf.py`, `tests/test_check_links.py`, `tests/test_regen_indexes.py`, `tests/test_wiki_init.py`, `tests/test_indexes_and_log.py`, `tests/test_ingest_source.py` | copied |
| `tests/test_agents_md.py` | rendered |
| `AGENTS.md`, `schema.md` | rendered |
| `bundle/index.md` | copied (subject-generic, holds no token) |
| `bundle/log.md` | rendered |
| `bundle/sources/index.md`, `bundle/entities/index.md`, `bundle/concepts/index.md`, `bundle/synthesis/index.md`, `bundle/open-questions/index.md` | generated (stub, matches what `regen_indexes.py` would produce for zero pages) |
| `raw/.gitkeep` | generated (empty) |
| `.claude/wiki.json` (repo-root, not container) | generated |
| `CLAUDE.md` (repo-root) | appended, never overwritten |

That is **8 test modules**: `conftest.py` plus 7 `test_*.py` files. `conftest.py` is the file
every other module imports from, so it ships with the suite.

## The six tokens

`{{CONTAINER}}`, `{{SUBJECT}}`, `{{REPO}}`, `{{HUMAN_ACTOR}}`, `{{AGENT_ACTOR}}`, `{{TODAY}}` —
substituted only in `templates/rendered/*` and `templates/claude-md-block.md`. Every file under
`templates/verbatim/*` is copied with `shutil.copyfile`, byte-for-byte, and must never contain a
token.

`{{CONTAINER}}` is always repo-root-relative and always ends with `/`, never starts with `./`, so
`{{CONTAINER}}AGENTS.md` renders `docs/wiki/AGENTS.md`.

## Two invariants

1. **Empty-bundle green.** All four gates pass on a bundle with zero pages — this is the
   acceptance test for the whole plugin (`plugins/wiki/tests/test_scaffold_empty_bundle.py`),
   parametrized over both a two-deep container (`docs/wiki/`) and a one-deep one (`wiki/`), since
   the one-deep case is what proves `conftest.py`'s walk-up-to-`.git` portability fix.
2. **The container is not the bundle root.** `check_okf.py` demands `type:` frontmatter on every
   `.md` under the bundle root, so `schema.md`, `raw/`, `scripts/`, and `tests/` sit in the
   container *beside* `bundle/`, never inside it. `scaffold.py` refuses `--container bundle/` for
   exactly this reason.

## The four gates

Run from the repository root, container-relative paths resolved from `.claude/wiki.json`:

```bash
python3 <container>scripts/check_okf.py --strict
python3 <container>scripts/check_links.py --strict
python3 <container>scripts/regen_indexes.py --check
python3 -m pytest -q <container>tests
```

## What the suite deliberately leaves to you

The plugin ships no content tests. A content test asserts a claim about one wiki's own subject,
so it is true for that wiki alone. A freshly scaffolded repo has no content to assert against.
Write these tests in your own repo as ingest fills the bundle.

The 8 shipped modules test the structure — the three scripts, the frontmatter rules, the indexes,
and the log. They stay true whatever the subject is.

## Non-goals

- No initial ingest — `/wiki:setup` ends green and empty; run `/wiki:ingest` next.
- No `/wiki:upgrade`.
- No CI wiring for the three scripts.
- No configurable type set — the five OKF types (`Source`, `Entity`, `Concept`, `Synthesis`,
  `OpenQuestion`) are fixed.
- No `/wiki:lint` command — Operation: Lint stays a hand-driven operation for now.

## Why the suite is portable

The shipped tests run in any repo, at any container depth, on a bundle with zero pages. Five
files carry the property that makes this true:

| File | Property |
|---|---|
| `tests/conftest.py` | Walks up to `.git` to find the repo root. Does not assume a two-deep container. |
| `tests/test_wiki_init.py` | Matches any date heading. Does not assume one fixed date. |
| `tests/test_indexes_and_log.py` | Reads the pages from disk. Skips on an empty bundle. |
| `tests/test_ingest_source.py` | Reads the pages from disk. Skips on an empty bundle. |
| `tests/test_agents_md.py` | Reads the six tokens, so it renders per repo. |
