---
title: LLM Wiki for {{REPO}}, conformant with OKF v0.2
status: draft
owner: {{HUMAN_ACTOR}}
last_updated: {{TODAY}}
---

# LLM Wiki for `{{REPO}}`, conformant with OKF v0.2

This spec adapts Karpathy's "LLM Wiki" pattern to {{REPO}}, a repository whose subject is {{SUBJECT}}. It fixes every open design point the pattern leaves abstract, so the result is buildable without further judgment calls. Every markdown file the implementation produces MUST conform to Open Knowledge Format (OKF) v0.2, section 11.

Points marked `[inferred]` are judgment calls the spec author made because OKF and the pattern leave them open. They are not weaker decisions -- they are still binding -- but a reviewer should look at them first if something needs to change.

This spec does not vendor a copy of OKF v0.2 or Karpathy's "LLM Wiki" pattern doc, and cites no URL for either; every "per OKF section N" reference below is a paraphrase, not a quote. Until a copy or link is added to the repo, this spec's own text -- not the external standard -- is the thing to check downstream work against. `[inferred]`

All paths below are relative to `{{CONTAINER}}`, the directory this document sits in, which holds the whole wiki subsystem. The exceptions are written out in full and start with the repository root or `.claude/`. Commands are the other exception: they are written to be run from the repository root.

## 1. Layer 1: raw sources

**Location:** `raw/`

`raw/` holds the curated, immutable collection of source documents -- the pattern's "raw sources" layer. Files here are never edited after they land; a correction or update arrives as a new file, never an in-place change. `raw/` sits outside the OKF bundle (see section 2), so OKF's frontmatter rules do not apply to it -- it can hold `.md`, `.pdf`, `.html`, `.txt`, or any other format.

**Naming convention:** `raw/<YYYY-MM-DD>-<kebab-slug>.<ext>`, where the date is the source's own publication/generation date (not the date it was added to the repo) and the slug is derived from its title. Example: `raw/{{TODAY}}-example-source-report.md`.

**What counts as a raw source:** any document an Ingest pass processes as a unit -- a fetched article, a research report, a PDF, a transcript, a dataset export. A raw source does not need to have been fetched from the web; a locally authored report qualifies too.

## 2. Layer 2: the wiki (OKF bundle)

**Location:** `bundle/` -- this directory tree IS the OKF v0.2 bundle. Bundle root = `bundle/`, not the repo root. `okf_version` (see OKF section 12) is declared once, in `bundle/index.md`'s frontmatter.

Directory layout:

```
bundle/
  index.md                          # bundle-root index (OKF 8), carries okf_version
  log.md                            # bundle-root log (OKF 9), ONLY log.md in the bundle
  sources/
    index.md
    <same-basename-as-raw-file>.md  # one Source concept page per raw/ file
  entities/
    index.md
    <slug>.md
  concepts/
    index.md
    <slug>.md
  synthesis/
    index.md
    <slug>.md
  open-questions/
    index.md
    <slug>.md
```

**Decision -- single log, per-directory indexes.** OKF permits `log.md` "at any level" and `index.md` "in any directory." This spec uses exactly one `log.md`, at bundle root, covering the whole bundle's history. Every subdirectory (`sources/`, `entities/`, `concepts/`, `synthesis/`, `open-questions/`) gets its own `index.md` for progressive disclosure, plus the bundle-root `index.md` links out to each subdirectory. Rationale: one log avoids the bookkeeping burden of keeping N logs in sync; per-directory indexes keep the pattern's "index.md organized by category" requirement concrete. `[inferred]`

**Decision -- filenames are lowercase kebab-case,** derived from `title`, ASCII only, no filename extensions beyond `.md`. Source pages are the one exception: a Source page's filename exactly mirrors its corresponding `raw/` file's basename (same date prefix, same slug), so the 1:1 relationship between a raw file and its Source page is visible from the filename alone: `raw/{{TODAY}}-example-source-report.md` <-> `bundle/sources/{{TODAY}}-example-source-report.md`.

## 3. Concept types

This bundle uses exactly five `type` values. An LLM agent maintaining the wiki MUST NOT invent a sixth without updating this spec first.

| `type` | Directory | Meaning |
|---|---|---|
| `Source` | `bundle/sources/` | A wiki page *about* one raw source document (not the raw file itself). Summarizes what the source says, what it's for, and what wiki pages it fed. One per `raw/` file. |
| `Entity` | `bundle/entities/` | A named organization, publication, framework-originating body, or named individual that recurs across sources. Tracks what has been claimed about it and by which sources. |
| `Concept` | `bundle/concepts/` | An abstract idea, metric, formula, or framework relevant to {{SUBJECT}}. The bulk of the wiki's accumulated knowledge lives here. |
| `Synthesis` | `bundle/synthesis/` | A cross-cutting page that weaves multiple Concept/Entity pages into a coherent narrative or answer -- the wiki's own "state of X" pages, and the destination for good Query answers filed back into the wiki. |
| `OpenQuestion` | `bundle/open-questions/` | A tracked, unresolved question the wiki does not yet have a confident answer to. Gives the pattern's "data gaps" a durable home instead of letting them evaporate at the end of a research pass. |

**Decision -- refuted claims do not get their own pages.** A claim that failed verification is recorded as a body subsection ("## Refuted or unverified claims") on the Concept or Entity page it would otherwise have supported, footnoted to its Source, so it stays visible and cannot be silently reintroduced by a later Ingest. It is never promoted to a standalone concept document. `[inferred]`

## 4. Frontmatter per type

All fields below conform to OKF 4.1 (`type`, `title`, `description`, `resource`, `tags`) and 5 (`sources`, `generated`, `verified`, `status`, `stale_after`). Fields not defined by OKF are marked `[ext]` (producer-defined extension, per 4.1's "Extensions" clause) and `[inferred]`.

**Actor strings used throughout (OKF 7):** the wiki-maintaining agent identifies as `{{AGENT_ACTOR}}`. A verification event carried over from a raw source's own automated verification process identifies as `process:<name>` (e.g. `process:adversarial-verifier`). A human reviewer identifies as `{{HUMAN_ACTOR}}`.

### 4.1 `Source`

```yaml
---
type: Source
title: "Example Source Report"
description: >-
  One-paragraph summary of what this source covers and why it matters to
  {{SUBJECT}}.
resource: raw/{{TODAY}}-example-source-report.md
tags: [example, report]
source_published: "{{TODAY}}"        # [ext][inferred] the raw source's own date
source_kind: research-report         # [ext][inferred] report | article | paper | survey | dataset | transcript
generated: { by: "{{AGENT_ACTOR}}", at: "{{TODAY}}T18:00:00Z" }
status: stable
---
```

`resource` on a `Source` page points at the file in `raw/`, expressed as a **path relative to `{{CONTAINER}}`, with no leading slash** (`raw/...`), or, when no local copy exists, the original external URL. This is deliberately different from the bundle-relative `/...` convention OKF 6.1 defines for links *between concepts* -- `resource` here points *outside* the bundle, to `raw/`, so the bundle-relative form doesn't apply. `[inferred]`

Under this spec's own Ingest procedure (section 6), the external-URL branch should not actually occur: AGENTS.md's Ingest step 1 always saves an incoming URL or pasted text into `raw/` before any `Source` page is created, so a `Source` page's `resource` is normally always a `raw/...` path. The external-URL form exists only for a `Source` page created outside that procedure (e.g. hand-authored, or migrated from elsewhere); in that case the filename-mirroring rule in section 2 does not apply, since there is no `raw/` file to mirror. `[inferred]`

### 4.2 `Entity`

```yaml
---
type: Entity
title: "Example Organization"
description: One-sentence description of what this organization is and why it recurs across sources.
entity_kind: organization           # [ext][inferred] organization | person | publication | framework-body
aliases: []                          # [ext][inferred]
tags: [example]
sources:
  - id: example-source
    resource: /sources/{{TODAY}}-example-source-report.md
    title: "Example Source Report"
    last_modified: "{{TODAY}}"
generated: { by: "{{AGENT_ACTOR}}", at: "{{TODAY}}T18:00:00Z" }
verified:
  - { by: "process:adversarial-verifier", at: "{{TODAY}}T00:00:00Z" }
status: stable
---
```

### 4.3 `Concept`

```yaml
---
type: Concept
title: Example Concept
description: >-
  One-paragraph description of the metric, formula, or framework this page
  covers.
tags: [example, concept]
sources:
  - id: example-source
    resource: /sources/{{TODAY}}-example-source-report.md
    title: "Example Source Report"
    last_modified: "{{TODAY}}"
generated: { by: "{{AGENT_ACTOR}}", at: "{{TODAY}}T18:00:00Z" }
verified:
  - { by: "process:adversarial-verifier", at: "{{TODAY}}T00:00:00Z" }
status: stable
# stale_after: omitted -- a stable definition doesn't go stale.
---
```

For a Concept page describing time-sensitive data (a survey stat, an adoption rate), add `stale_after` roughly 12 months out from `source_published`. `[inferred]` policy, not an OKF requirement:

```yaml
stale_after: "{{TODAY}}"  # example only: set this to roughly one year out
```

### 4.4 `Synthesis`

```yaml
---
type: Synthesis
title: Example Synthesis Page
description: >-
  Cross-cutting synthesis of a narrative that spans several Entity/Concept
  pages, written after 3 or more of them share a coherent story.
tags: [example, overview]
sources:
  - id: example-source
    resource: /sources/{{TODAY}}-example-source-report.md
    title: "Example Source Report"
    last_modified: "{{TODAY}}"
generated: { by: "{{AGENT_ACTOR}}", at: "{{TODAY}}T18:00:00Z" }
status: draft   # Synthesis pages start as draft until a human reviews them.
---
```

### 4.5 `OpenQuestion`

```yaml
---
type: OpenQuestion
title: Example unresolved question
description: >-
  One-sentence statement of what remains unanswered and why it matters.
tags: [example, open-question]
sources:
  - id: example-source
    resource: /sources/{{TODAY}}-example-source-report.md
    title: "Example Source Report"
    last_modified: "{{TODAY}}"
generated: { by: "{{AGENT_ACTOR}}", at: "{{TODAY}}T18:00:00Z" }
status: draft   # draft = open, stable = resolved, deprecated = no longer relevant
---
```

`status` is overloaded deliberately for `OpenQuestion` (reusing OKF's `draft | stable | deprecated` enum instead of inventing an extension field): `draft` = still open, `stable` = resolved/answered, `deprecated` = no longer a relevant question.

## 5. Cross-linking and provenance

- Links between wiki pages are written **relative to the file that holds them**: `[Example Entity](../entities/example-entity.md)` from a page in `concepts/`, `[Example Concept](example-concept.md)` between two pages in `concepts/`, `[Entities](entities/index.md)` from `bundle/index.md` -- name `index.md` explicitly rather than linking a bare directory, so a click lands on the curated index page instead of a raw file listing. This is a deliberate departure from OKF 6.1's bundle-relative absolute form (`/entities/example-entity.md`). OKF's form is stable under a move within the same subdirectory, but GitHub, VS Code, and every ordinary markdown viewer resolve a leading slash against the *repository* root, not the bundle root, so a link written that way 404s for a human reader -- and a bundle nested a few levels deep (e.g. `docs/wiki/bundle/`) makes the gap wider. Navigability in a real viewer wins; the cost is that a link must be recomputed when a page changes directory. `scripts/check_links.py` errors on a leading-slash link and resolves every relative link against the referring file's own directory; `scripts/regen_indexes.py` emits the relative form. `[inferred]`
- Per-claim attribution uses markdown footnotes keyed to a `sources[].id`, per OKF 4.2 -- never a body "References" list:

  ```markdown
  This is a claim the source supports.[^example-source]

  [^example-source]: Example Source Report
  ```

- `sources[].resource` on Entity/Concept/Synthesis/OpenQuestion pages points at the corresponding `Source` page *inside the bundle* (bundle-relative `/sources/....md`), not directly at `raw/` or the original URL. This keeps a single, walkable provenance chain: `Concept -> footnote -> Source page -> resource -> raw/ file or external URL`. `[inferred]` This value is frontmatter, not a rendered link -- no viewer makes it clickable -- so it deliberately keeps OKF 6.1's bundle-relative `/sources/....md` form. The relative-link rule above governs body links only.
- A link asserts nothing on its own; the surrounding prose says whether it's an "is-a", "contradicts", "supersedes", or "see-also" relationship, per OKF 6.1.

## 6. `AGENTS.md` -- the agent procedure

**Location:** `{{CONTAINER}}AGENTS.md`, beside this document. `CLAUDE.md` at the repository root is a short pointer to it, because Claude Code loads `CLAUDE.md` automatically; `AGENTS.md` is the tool-agnostic canonical copy other agents and tools read.

`AGENTS.md` defines four operations -- Initialization, Ingest, Query and Lint -- and states the trigger for each. It is the procedure; this document is the schema the procedure writes against.

## 7. Deterministic OKF conformance checker

**Location:** `scripts/check_okf.py`. Pure Python 3 standard library + `PyYAML` (the only external dependency; the script exits 2 immediately with a clear message if it isn't installed).

**Scope, precisely mapped to OKF section 11's three conformance rules:**

1. Every non-reserved `.md` file under `bundle/` has a parseable YAML frontmatter block.
2. Every such frontmatter block has a non-empty `type` field.
3. Every `index.md` and `log.md` under `bundle/` follows OKF 8/9 structure when present.

Everything beyond that (OKF 5's SHOULDs, this spec's own conventions like "only one `log.md`") is reported as a WARNING, never an ERROR -- warnings don't fail conformance, matching OKF 11's "Consumers MUST NOT reject a bundle because of..." list. `--strict` promotes warnings to errors for CI use if desired.

**Invocation:**

```
$ python3 {{CONTAINER}}scripts/check_okf.py [--bundle PATH] [--format text|json] [--strict] [--quiet]
```

- `--bundle PATH` -- bundle root to check. Defaults to `bundle/` beside the script, resolved from the script's own location, so the command works from any directory.
- `--format text|json` -- default `text`.
- `--strict` -- warnings also cause exit 1.
- `--quiet` -- suppress per-issue output; only print the summary line and use the exit code.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Conformant. Zero errors (warnings allowed unless `--strict`). |
| 1 | Non-conformant. One or more errors (or, with `--strict`, one or more warnings). |
| 2 | Usage/internal error: bundle path doesn't exist, `PyYAML` missing, bad CLI args, unexpected crash while walking the tree. |

**Output (text format):** one line per issue, `LEVEL: path[:line] [rule] message`, then a summary line, e.g.:

```
ERROR: bundle/entities/example-entity.md [missing-type] frontmatter has no non-empty 'type' field
WARN: bundle/concepts/example-concept.md [sources-missing-resource] sources[0] has no 'resource'
2 errors, 1 warning across 19 files
```

**Output (`--format json`):**

```json
{
  "bundle": "wiki",
  "files_checked": 19,
  "errors": 2,
  "warnings": 1,
  "issues": [
    {"file": "bundle/entities/example-entity.md", "line": 1, "level": "ERROR",
     "rule": "missing-type", "message": "frontmatter has no non-empty 'type' field"}
  ]
}
```

Out of scope, by design: no `--fix` mode. This tool only checks; `AGENTS.md`'s Lint procedure is what fixes things, because fixes here require judgment (an LLM), not pattern-matching.

### 7.1 Implementation

Read the live file at `scripts/check_okf.py`; this spec does not reproduce its source. Two companion scripts are documented in `AGENTS.md`: `scripts/check_links.py` resolves every internal link against the file that holds it, rejects a link that starts with `/`, and reports orphan pages and non-ASCII text, and `scripts/regen_indexes.py` generates every subdirectory `index.md` and each Source page's fed-pages list from frontmatter.

## 8. `index.md` conventions

Per OKF section 8: no frontmatter except `bundle/index.md` (bundle root), which MAY carry `okf_version`. Body is one or more `#`-headed sections, each a bullet list of `[Title](link) - description`, `description` copied verbatim from the linked page's frontmatter `description`.

`bundle/index.md` (bundle root) template:

```markdown
---
okf_version: "0.2"
---

# Wiki Index

* [Entities](entities/index.md) - organizations, publications, and named individuals referenced across sources.
* [Concepts](concepts/index.md) - metrics, formulas, and frameworks the wiki tracks.
* [Synthesis](synthesis/index.md) - cross-cutting write-ups tying multiple pages together.
* [Open Questions](open-questions/index.md) - unresolved questions the wiki is tracking.
* [Sources](sources/index.md) - one page per raw source ingested.
```

Each subdirectory `index.md` (no frontmatter) lists just that directory's pages, grouped by a heading if a natural sub-grouping exists (otherwise one flat section is fine). Example, `bundle/concepts/index.md`:

```markdown
# Concepts

* [Example Concept One](example-concept-one.md) - one-line description, copied verbatim from its frontmatter.
* [Example Concept Two](example-concept-two.md) - one-line description, copied verbatim from its frontmatter.
```

Regeneration: `bundle/index.md` and any touched subdirectory `index.md` are updated as step 7 of every Ingest (section 6 above) -- never left to drift.

## 9. `log.md` conventions

Per OKF section 9: flat list of `## YYYY-MM-DD` date headings, newest first, with prose bullet entries below each. This spec's reconciliation of the pattern's suggested per-entry heading (`## [YYYY-MM-DD] ingest | Title`) with OKF's per-*date* heading requirement: **the date is the heading; the operation is the bullet's bold lead word**, which keeps both OKF-conformant structure and the pattern's greppability (`grep '\*\*Ingest\*\*' bundle/log.md`). `[inferred]`

`bundle/log.md` template:

```markdown
# Wiki Update Log

## {{TODAY}}
* **Initialization**: Established the wiki bundle structure (`sources/`, `entities/`, `concepts/`, `synthesis/`, `open-questions/`).
* **Ingest**: Added [Example Source Report](sources/{{TODAY}}-example-source-report.md) -- created 2 entity pages, 3 concept pages, 1 synthesis page, 2 open questions.
```

The `**Initialization**` bullet above illustrates the one-time bootstrap event (AGENTS.md's Initialization operation, section 6); it only appears on a bundle's very first day, immediately before that day's first Ingest, and sits above that first Ingest's bullet because bullets under one date heading follow chronological append order, oldest on top. `[inferred]`

Only one `log.md` exists in this bundle, at `bundle/log.md` (see section 2's decision). `scripts/check_okf.py` WARNs (does not error) if a `log.md` appears elsewhere, since OKF itself permits it -- this spec just doesn't use that permission.

## 10. Worked example: what `/wiki:setup` leaves behind

Running `/wiki:setup` produces a scaffolded, zero-page bundle, not a populated one. It creates:

- `{{CONTAINER}}` holding `AGENTS.md`, `schema.md`, `scripts/` (3 checkers), `tests/` (the vendored suite), `requirements.txt`, and `raw/` (empty, with a `.gitkeep`).
- `bundle/index.md` (bundle root, hand-written, carrying `okf_version`) and `bundle/log.md` with exactly one `**Initialization**` entry under today's date.
- Five empty-but-structured subdirectories -- `sources/`, `entities/`, `concepts/`, `synthesis/`, `open-questions/` -- each with a stub `index.md` holding only its section heading.
- `.claude/wiki.json` recording the container path, the OKF version, and the plugin version that scaffolded it.
- One append to the repository's `CLAUDE.md` pointing at `AGENTS.md`.

That is 22 files in the container plus `.claude/wiki.json` and the `CLAUDE.md` append -- and zero pages. All four gates (section 7's checker plus its two companion scripts, and the test suite) pass on this bundle exactly as scaffolded: `check_okf.py --strict` reports 0 errors and 0 warnings, `check_links.py --strict` reports 0 errors and 0 warnings (there is nothing yet to link or orphan), `regen_indexes.py --check` reports no drift across the five stub indexes, and the test suite passes with the empty-bundle cases explicitly skipped, each with a stated reason.

Run `/wiki:ingest` next to bring in the first raw source; that pass is what creates the first Source, Entity, Concept, Synthesis, and OpenQuestion pages and turns the skipped tests into real assertions.

## 11. Non-goals

Out of scope for this document:

- CI wiring for the three scripts (e.g. a GitHub Actions job running them on every pull request that touches `{{CONTAINER}}`).
- Vector search / embeddings for Query -- Query is grep-and-read per section 6, matching the pattern's own "no RAG" framing.
- Access control / multi-user conflict resolution for concurrent Ingests.
