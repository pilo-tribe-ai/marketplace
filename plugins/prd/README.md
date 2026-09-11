# PRD Analysis Plugin

Product-level PRD creation and roadmap planning through lens-driven Socratic exploration, with full traceability between the PRD and the roadmap.

## Overview

The plugin maintains two living documents per repository:

| File | Path | What it holds |
|------|------|---------------|
| PRD | `docs/product/prd.md` | The product requirements, one section per explored lens, with permanent requirement IDs |
| Roadmap | `docs/product/roadmap.md` | Milestones, features, and stories, each traced back to the requirements it satisfies |

Two principles run through every skill:

1. **The product hat.** Exploration and planning stay at the product level — problems, people, journeys, capabilities, scope, metrics. Implementation asks (architecture, stack, APIs) are deflected: the product constraint behind them is captured, the technology choice is not. See `skills/shared/product-hat.md`.
2. **Traceability.** Every roadmap item records which requirements it satisfies (`Trace: CAP-3 @a1b2c3` — ID plus content hash). When a requirement changes, the affected items are flagged `Needs Review`.

## Quick Start

```bash
# Discover requirements, lens by lens (bootstraps docs/product/prd.md)
/prd:explore

# Persist each session's findings
/prd:save

# Stress-test the PRD from a developer's perspective
/prd:simulate

# Generate the roadmap for the scope you choose
/prd:plan
```

## The Lens System

`/prd:explore` guides discovery through an ordered **spine** — each lens builds on the ones before it:

```
Problem → Personas → Journeys → Capabilities → Scope → Success Metrics
```

Three **satellite** lenses unlock when their prerequisites are met: Business Model, Go-to-Market, Risks & Assumptions.

- `/prd:explore personas` jumps straight to a lens.
- `/prd:explore` with no argument asks what your goal is and offers the lenses that make sense now, recommending the next one in order.
- **Soft gate**: exploring a lens whose prerequisite is missing (journeys without personas) triggers a recommendation to do the prerequisite first — you can override, and the explorer captures a minimal bootstrap inline so the work attaches to something.

Coverage is tracked in the PRD's frontmatter (`not-started` / `in-progress` / `complete` per lens), so exploration resumes cleanly across sessions.

The full lens catalog, section headings, ID prefixes, and prerequisites live in `skills/shared/prd-schema.md`.

## Skills

### `/prd:explore [lens]`

Socratic exploration of one lens at a time: one question at a time, 2-4 meaningful options, each question building on the last. Question guides per lens are grounded in standard product practice — jobs-to-be-done, journey mapping, Kano, MoSCoW, North Star metrics, riskiest-assumption testing.

**Output**: validated insights, ready for `/prd:save`.

### `/prd:save [lens]`

Writes the session's findings into `docs/product/prd.md`:

- Updates the lens section, preserving everything else
- Assigns permanent requirement IDs (`PER-1`, `CAP-3`, `CON-2`, ...) — never renumbered, never reused
- Maintains the coverage frontmatter
- Runs a scoped drift check: if the roadmap traces a requirement you changed, the item is flagged `Needs Review`
- Detects legacy v2 files (`docs/prd/*.md`) and offers a one-time merge

### `/prd:simulate [prd-file]`

A senior-developer persona reads the PRD and reports where it would get stuck: ambiguity, missing error paths, unstated assumptions, edge cases. The persona is technical; the captured decisions are not — every decision lands as product behavior or a product constraint.

### `/prd:plan [scope]`

The roadmap generator. Asks three things:

1. **What are we planning?** MVP only / the next phase / full product in phases / one specific phase
2. **How do we slice?** Proposes strategies from the PRD content — walking skeleton (value-first), persona-first, journey-first, risk-first — with the concrete phases each would produce
3. **How deep?** Milestones / features / stories (default: stories)

Every phase becomes a milestone so the whole shape is visible; only the chosen slice is broken down — the rest stay as `Not Planned` placeholders. Run `/prd:plan` again to flesh out the next phase.

`/prd:plan` orchestrates the granular skills below, which remain available for incremental edits.

### `/prd:themes-identify [prd]` · `/prd:features-identify [roadmap] [M]` · `/prd:stories-identify [roadmap] [F]`

The granular building blocks: extract milestones, break a milestone into features, decompose a feature into INVEST-validated stories. Every item records its `Trace`.

### `/prd:stories-estimate [roadmap] [feature]`

T-shirt sizing (S=1 / M=3 / L=5), one story at a time, with the team present.

### `/prd:roadmap-sync [roadmap]`

Two sync sources in one run:

- **Progress**: parallel subagents scan GitHub issues/PRs for item IDs and verify code existence; statuses update with evidence
- **Drift**: every trace hash is recomputed against the PRD; changed or removed requirements flag their items `Needs Review ⚠`, and the skill walks you through resolving each one (still valid → re-link; needs rework → stays flagged)

## Traceability Model

```
docs/product/prd.md                    docs/product/roadmap.md
─────────────────────                  ───────────────────────
## Capabilities                        - [ ] F1.2: Scheduling
- **CAP-1**: Users can book a   ◄──────  **Trace**: CAP-1 @a1b2c3
  slot in under a minute.
```

- IDs are lens-prefixed (`PRB`, `PER`, `JRN`, `CAP`, `SCP`, `MET`, `BIZ`, `GTM`, `RSK`, `CON`) and permanent.
- `@a1b2c3` is the first 6 hex chars of the SHA-256 of the normalized requirement text at link time.
- A hash mismatch during save or sync = the requirement drifted = the item needs human review.

Full rules: `skills/shared/prd-schema.md` and `skills/shared/roadmap-table-schema.md`.

## Roadmap Status Table

Every roadmap starts with an auto-regenerated status table:

```markdown
<!-- ROADMAP-STATUS-TABLE:START -->
| # | Group | Item | Type | Status | Progress | Deps | Trace |
|---|-------|------|------|--------|----------|------|-------|
| 1 | - | M1: Foundation | Milestone | Needs Review | ██████░░░░ 55% | - | SCP-1 |
| 2 | A | F1.2: Scheduling | Feature | Needs Review | ██████████ 100% | - | CAP-1 ⚠ |
| 3 | - | M3: Insights | Milestone | Not Planned | ░░░░░░░░░░ 0% | M2 | SCP-3 |
<!-- ROADMAP-STATUS-TABLE:END -->
```

Statuses: `Not Planned`, `Not Started`, `In Progress`, `Completed`, `Needs Review`.

## Workflow

```
1. /prd:explore          → Guided lens-by-lens discovery (bootstraps the PRD)
   └─→ /prd:save         → Persist each session
2. /prd:simulate         → Developer-perspective stress test
   └─→ /prd:save         → Persist decisions
3. /prd:plan             → Slice scope, generate the roadmap with traces
4. /prd:stories-estimate → Size stories with the team
5. /prd:roadmap-sync     → Track progress and requirement drift
```

## File Structure

```
plugins/prd/
├── agents/
│   ├── prd-analyst.md             # Product-hat Socratic agent (Opus)
│   ├── prd-simulator.md           # Developer-perspective gap analysis (product-level output)
│   └── roadmap-analyst.md         # Roadmap planning agent (trace-aware)
├── skills/
│   ├── shared/
│   │   ├── prd-schema.md          # PRD format, lens catalog, IDs, hashes, migration
│   │   ├── product-hat.md         # Product-level guardrail + deflection procedure
│   │   └── roadmap-table-schema.md # Status table spec + drift rules
│   ├── explore/SKILL.md           # Lens-driven exploration
│   ├── save/SKILL.md              # Living-PRD writer
│   ├── simulate/SKILL.md          # Implementation simulation
│   ├── plan/SKILL.md              # Roadmap generator (orchestrates the skills below)
│   ├── themes-identify/SKILL.md   # Milestone extraction
│   ├── features-identify/SKILL.md # Feature decomposition
│   ├── stories-identify/SKILL.md  # Story creation
│   ├── stories-estimate/SKILL.md  # T-shirt sizing
│   └── roadmap-sync/
│       ├── SKILL.md               # Progress + drift sync
│       └── references/sync-sources.md
├── .claude-plugin/plugin.json     # Plugin metadata
├── SKILL.md                       # Plugin manifest
└── README.md                      # This file
```

## Breaking Changes in v3.0.0

- **Stable paths** — the PRD lives at `docs/product/prd.md`, the roadmap at `docs/product/roadmap.md`. The per-focus-area files of v2 (`docs/prd/[product]-[focus].md`) are replaced by one living PRD; `/prd:explore` and `/prd:save` detect legacy files and offer a one-time merge.
- **`/prd:context` removed** — `/prd:explore` bootstraps the PRD itself on first run.
- **Focus areas → lenses** — the Architecture and Configuration focus areas are gone; the product hat deflects implementation topics into product constraints.
- **Traceability required** — roadmap items carry `Trace` links; the status table gained a `Trace` column and the `Not Planned` / `Needs Review` statuses.
- **New command** — `/prd:plan` generates the roadmap end to end for a chosen scope.
- **Flat skill names** — the `commands/` wrapper layer is gone and nested skill paths are flattened: `/prd:themes:identify` → `/prd:themes-identify`, `/prd:features:identify` → `/prd:features-identify`, `/prd:stories:identify` → `/prd:stories-identify`, `/prd:stories:estimate` → `/prd:stories-estimate`, `/prd:roadmap-sync` unchanged in name but now a flat skill. The wrappers pointed at skill names that never resolved, so the skill bodies could not load; skills now register directly.

## License

MIT License - Free to use and modify.

---

**Ready to create your PRD?** Start with `/prd:explore`
