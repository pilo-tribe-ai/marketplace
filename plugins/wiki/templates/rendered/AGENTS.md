# AGENTS.md

This repo maintains a persistent knowledge wiki about {{SUBJECT}} at
`{{CONTAINER}}`, built from raw sources, conformant with Open Knowledge
Format (OKF) v0.2. This file tells you (the agent) how to maintain it.
Follow it exactly.

## Where this lives

The whole wiki subsystem is self-contained under `{{CONTAINER}}`. Every path
in the Layout section below is relative to that directory, and so is every
`resource:` value inside the bundle.

Commands are different. Write and run them from the repository root, because
that is where a session starts. Each script finds the bundle from its own
location, so `--bundle` is needed only to point at a different bundle.

## Layout

- `raw/<date>-<slug>.<ext>` -- immutable raw sources. Never edit these.
- `bundle/` -- the OKF bundle. You own this directory entirely: create pages,
  update them, maintain cross-references, keep everything consistent.
  - `bundle/index.md` -- catalog of everything, organized by type. Read this
    first, always.
  - `bundle/log.md` -- append-only chronological history. One entry per
    Initialization / Ingest / Query / Lint event.
  - `bundle/sources/`, `bundle/entities/`, `bundle/concepts/`,
    `bundle/synthesis/`, `bundle/open-questions/` -- one subdirectory per
    concept `type`, each with its own `index.md`.
- `scripts/check_okf.py` -- deterministic OKF conformance checker. Run it
  after every Ingest and every Lint pass. It must exit 0 before you consider
  the operation done. Needs PyYAML; run
  `pip install -r {{CONTAINER}}requirements.txt` once before first use.
- `scripts/check_links.py` -- resolves every internal link, reports pages no
  prose page links to, rejects non-ASCII text, and rejects leading-slash
  links (see the Conventions recap at the bottom of this file). `check_okf.py`
  checks that a link is present, not that it resolves; this script covers
  that gap.
- `scripts/regen_indexes.py` -- regenerates every subdirectory `index.md` and
  each Source page's "Pages this source fed" list from page frontmatter.
  These are derived data. Never hand-edit them; run this instead. `--check`
  reports drift without writing.

`/wiki:ingest` ships in the wiki plugin. It reads `.claude/wiki.json` to find
this container, then runs the Ingest operation below end to end. Use it
rather than driving these steps by hand. `/wiki:ask` ships in the same
plugin and runs the Query operation below. It answers from bundle pages
only.

Concept types, their meaning, and their exact frontmatter fields are defined
in `schema.md` sections 3-4. Do not invent a new `type` value or a new
top-level directory without updating that document first.

## Operation: Initialization

Triggered by: `bundle/` does not exist yet and you are about to run the first
Ingest. A one-time, bundle-level bootstrap, not repeated afterward.
`[inferred]`

1. Create the directory skeleton: `bundle/sources/`, `bundle/entities/`,
   `bundle/concepts/`, `bundle/synthesis/`, `bundle/open-questions/`. Also
   create `raw/` if it does not already exist -- `git mv` will not create a
   missing destination directory on its own, and Ingest step 1 needs `raw/`
   to exist before it can save anything into it. `[inferred]`
2. Create `bundle/index.md` (bundle-root, per schema section 8's template,
   carrying `okf_version`) and an empty-but-structured `index.md` in each
   subdirectory above: a single top-level heading naming the directory's
   type (`# Sources`, `# Entities`, `# Concepts`, `# Synthesis`, or
   `# Open Questions`) and no list items yet -- `scripts/check_okf.py`'s
   `index-no-headings` check requires at least one heading, even on an
   otherwise-empty index. `[inferred]`
3. Create `bundle/log.md` with just the `# Wiki Update Log` heading, no
   entries yet.
4. Append one `bundle/log.md` entry under today's date heading:
   `* **Initialization**: Established the wiki bundle structure (sources/,
   entities/, concepts/, synthesis/, open-questions/).` Since this entry is
   appended first, it is the top bullet under today's date heading; Ingest's
   own entry (step 8 below) is appended after it, as the next bullet down.
   `[inferred]` Then proceed straight to Ingest -- do not stop here.

## Operation: Ingest

Triggered by: a new file appears in `raw/`, or you are told to ingest a URL
or pasted document.

1. If given a URL or pasted text rather than an existing `raw/` file: save
   it verbatim into `raw/<YYYY-MM-DD>-<kebab-slug>.<ext>` first. Never skip
   this -- raw materials must exist before wiki pages cite them.
2. Read the raw file in full.
3. Check whether a `Source` page for it already exists at
   `bundle/sources/<same-basename>.md`. If yes, this is an update to an
   existing source, not a new one -- update that page's body and
   `generated.at`, don't create a duplicate.
4. If new, create `bundle/sources/<same-basename>.md` with `type: Source`
   (frontmatter per schema section 4.1). Its `resource` field is a path
   relative to `{{CONTAINER}}`, so it reads `raw/<same-basename>.<ext>`. Body:
   a short summary of what the source covers and a bullet list (filled in
   after step 6) of which wiki pages it fed.
5. Extract: named entities, concepts/metrics/formulas/frameworks, and any
   claims the source verifies or refutes. If the source documents its own
   verification process (vote counts, confidence labels, a refuted-claims
   table), carry that trust signal into `verified`
   (actor `process:<name>`) rather than treating everything as unverified.
6. For each extracted item:
   - If a page for it already exists (`bundle/entities/<slug>.md` etc.),
     update it: add the new `sources[]` entry (if not already present),
     add or revise footnoted claims in the body, note explicitly if the
     new source contradicts an existing claim (don't silently overwrite --
     say "X was previously reported as A; this source reports B" with both
     footnoted).
   - If no page exists, create one with the correct `type` and frontmatter
     per schema section 4.
   - Refuted/unverified claims never get their own page. Add them under a
     "## Refuted or unverified claims" section on the relevant Concept or
     Entity page, footnoted to the Source.
   - Unresolved questions the source raises (explicitly stated, or gaps you
     notice while writing) become `OpenQuestion` pages, or, if a matching
     one already exists, get an added `sources[]` entry and, if the new
     source resolves it, a `status: stable` flip plus an "## Resolution"
     section citing the answer.
   - If this Ingest created or updated 3 or more Entity/Concept pages that
     share a coherent narrative, also create (or update) a `Synthesis` page
     per schema section 4.4 weaving them together, `status: draft`. Below
     that threshold, skip Synthesis -- it's not required on every Ingest.
     `[inferred]`
7. Run `python3 {{CONTAINER}}scripts/regen_indexes.py`. It rewrites every
   subdirectory `index.md` and each Source page's "Pages this source fed"
   list from the frontmatter you just wrote. Do not hand-edit those files --
   a hand edit is drift the next run silently reverts. `bundle/index.md` at
   the bundle root is hand-written and is left alone; edit it yourself only
   when you add a whole new page type.
8. Append one entry to `bundle/log.md` under today's `## YYYY-MM-DD` heading
   (create the heading if today doesn't have one yet; newest date first).
   Bullets within one date heading are in chronological append order, oldest
   on top -- so if Initialization ran earlier today, its bullet stays above
   this one; just add this bullet below whatever is already there.
   `[inferred]` Format: `* **Ingest**: <what happened>, linking every page touched.`
   Example:
   `* **Ingest**: Added [Example Source Report](sources/<YYYY-MM-DD>-<slug>.md) -- created 5 entity pages, 6 concept pages, 1 synthesis page, 4 open questions.`
9. Run all four gates from the repository root. Every one must pass before
   Ingest is done. Fix what they report; never suppress or work around a
   failure.

   ```
   python3 {{CONTAINER}}scripts/check_okf.py --strict
   python3 {{CONTAINER}}scripts/check_links.py --strict
   python3 {{CONTAINER}}scripts/regen_indexes.py --check
   python3 -m pytest -q {{CONTAINER}}tests
   ```

   `check_links.py --strict` treats an orphan page as a failure. The usual
   cause is a real gap: a page you created that no prose page links to.
   Fix it by adding the missing cross-reference, not by dropping `--strict`.

## Operation: Query

Triggered by: a question about the wiki's subject matter.

`/wiki:ask` runs this operation end to end.

1. Read `bundle/index.md` first. Skim subdirectory indexes relevant to the
   question.
2. Grep `bundle/**/*.md` bodies and frontmatter (`title`, `description`,
   `tags`) for keyword matches. Rank candidate pages by relevance.
3. Read the full content of the top candidate pages (their footnotes tell
   you which Source pages back each claim -- follow those too if the
   question demands source-level detail).
4. Synthesize an answer. Cite wiki pages inline as markdown links written
   relative to the file the link lands in, the same way pages cite each
   other -- from a page in `bundle/synthesis/` that reads
   `[../concepts/<slug>.md](../concepts/<slug>.md)`.
5. If the answer is non-trivial and durably useful (not a one-off lookup),
   offer to file it back into the wiki as a new `Synthesis` page under
   `bundle/synthesis/`, `status: draft`. Only create it if the user agrees --
   Query itself is read-only by default.
6. If you did write a new page: run
   `python3 {{CONTAINER}}scripts/regen_indexes.py` to rebuild
   `bundle/synthesis/index.md` (leave the hand-written `bundle/index.md`
   alone -- it is edited by hand only when a whole new page type is added),
   append a `bundle/log.md` entry (`* **Query**: ...`), and run
   `python3 {{CONTAINER}}scripts/check_okf.py`.
7. If you did not write a new page, still append a one-line `bundle/log.md`
   entry recording the question was asked -- this keeps the log a true
   record of "what happened," per the pattern.

## Operation: Lint

Triggered by: explicit request, or periodically (e.g. after every 5th
Ingest).

1. Run the deterministic floor first, from the repository root, and fix
   every ERROR before doing anything else:
   `python3 {{CONTAINER}}scripts/check_okf.py --strict` (OKF conformance),
   `python3 {{CONTAINER}}scripts/check_links.py --strict` (link resolution,
   orphans, encoding), and
   `python3 {{CONTAINER}}scripts/regen_indexes.py --check` (index drift).
   Between them these cover the contradiction, orphan, and structure checks
   a parser can decide. Step 2 covers only what it cannot.
2. Then do the semantic checks OKF does not (and explicitly should not)
   enforce -- these require judgment, not a parser:
   - **Contradictions**: two pages making incompatible claims without
     cross-referencing each other. Add the missing cross-reference and a
     note explaining the discrepancy.
   - **Staleness**: pages with `stale_after` in the past, or market-data
     claims with no `stale_after` that plausibly should have one. Flag in
     the page body and in the Lint log entry; do not silently delete.
   - **Orphans**: `check_links.py` in step 1 already lists these. It ignores
     inbound links from an `index.md` or a Source page, since both link
     every page by construction. Either add a link from a relevant page, or
     note in the Lint log entry that it's intentionally standalone.
   - **Missing pages**: a concept or entity mentioned by name in 2+ pages
     but without its own page. Create one.
   - **Missing cross-references**: two pages clearly about related things
     that don't link to each other.
   - **Data gaps**: claims a page makes with no footnote/source, or
     `OpenQuestion` pages that have gone unresolved across 3+ Ingests
     without any new source touching them.
3. Append a `bundle/log.md` entry summarizing what Lint found and fixed:
   `* **Lint**: <N> issues found, <M> fixed, <K> left open (see notes).`
4. Run `python3 {{CONTAINER}}scripts/check_okf.py` once more if you made any
   edits in step 2, since fixing a semantic issue can accidentally break
   structure (e.g. a malformed link edit). Must exit 0 before Lint is done.

## Conventions recap

- Actor strings: `{{AGENT_ACTOR}}` (you), `process:adversarial-verifier`
  (an example of the `process:<name>` form -- carried-over automated
  verification from a raw source), `{{HUMAN_ACTOR}}` (human review).
- Dates: `YYYY-MM-DD` for `sources[].last_modified`, `stale_after`, and
  `bundle/log.md` headings. Full `ISO-8601` datetime for `generated.at` and
  `verified[].at`.
- Never edit a file in `raw/`. Never write frontmatter into `log.md`.
  Frontmatter in `index.md` is permitted ONLY in `bundle/index.md`
  (bundle root), and only the `okf_version` key.
- Links between pages are relative to the file that holds them
  (`../entities/<slug>.md`, `<slug>.md`, `entities/`), never
  `/entities/<slug>.md` -- a leading slash 404s in GitHub. Frontmatter
  `sources[].resource` is the one exception and keeps the `/sources/....md`
  form; see schema.md section 5.
