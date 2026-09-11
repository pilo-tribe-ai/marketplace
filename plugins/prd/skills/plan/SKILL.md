---
description: Generate a roadmap from the PRD — asks how to slice the scope (MVP, phase, full product), then drives milestone, feature, and story identification for the chosen slice
argument-hint: "[scope]"
model: sonnet
agent: roadmap-analyst
allowed-tools: AskUserQuestion, Read, Write, Edit, Grep, Glob, Bash
---

# Plan — PRD to Roadmap

Turn `docs/product/prd.md` into `docs/product/roadmap.md` for a scope the user chooses. This skill orchestrates the existing granular skills — it does not replace them. The granular commands (`/prd:themes-identify`, `/prd:features-identify`, `/prd:stories-identify`) remain available for incremental edits.

## Before anything

Read the shared specifications:

1. `${CLAUDE_SKILL_DIR}/../shared/prd-schema.md` — PRD format, requirement IDs, hash rules
2. `${CLAUDE_SKILL_DIR}/../shared/roadmap-table-schema.md` — status table format, Trace column, statuses
3. `${CLAUDE_SKILL_DIR}/../shared/product-hat.md` — the product-level guardrail (planning stays at the level of user value, not engineering design)

## Step 1: Read the PRD and check readiness

1. Read `docs/product/prd.md` and its frontmatter.
2. **Soft gate**: planning needs at least Capabilities and Scope (`in-progress` or better). If either is missing, recommend `/prd:explore capabilities` or `/prd:explore scope` first — but let the user override and plan from what exists.
3. If `docs/product/roadmap.md` already exists, read it. A later run of `/prd:plan` extends the existing roadmap (typically fleshing out the next `Not Planned` milestone) — it never starts over without asking.

## Step 2: Establish the planning scope

Ask, one question at a time (AskUserQuestion):

### 2a. What are we planning?

- **MVP only** — plan the first shippable slice, leave the rest as placeholders
- **The next phase** — the roadmap exists; flesh out the next `Not Planned` milestone
- **Full product, in phases** — name all phases, then flesh out the first
- **One specific phase** — the user names it (e.g., "phase zero"); flesh out just that one

If `{{scope}}` was given as an argument (e.g., `mvp`, `phase-0`), map it to one of these and confirm briefly instead of asking.

### 2b. How do we slice?

Propose 2-4 slicing strategies **derived from the PRD content** — name concrete phases using the actual capabilities (CAP), personas (PER), and scope entries (SCP). Standard strategies:

- **Walking skeleton / value-first** — thinnest end-to-end path through the core journey first, then widen (usually the recommended default)
- **Persona-first** — serve the primary persona completely, then the next persona
- **Journey-first** — one complete journey per phase
- **Risk-first** — the phases that test the riskiest assumptions (RSK) come first

Present each option with the concrete phase names it would produce. Recommend one and say why.

### 2c. How deep?

- **Milestones only** — the phase skeleton
- **Milestones + features**
- **Milestones + features + stories (Recommended)** — the default

Estimation is not part of planning — recommend `/prd:stories-estimate` afterward, when the team is present.

## Step 3: Build the full skeleton

Every phase becomes a milestone, so the whole shape is always visible:

- The **chosen slice** gets planned in full (per the depth choice).
- Every **other phase** becomes a placeholder milestone: name, one-line goal, `**Trace**` to its driving requirements, status `Not Planned`.

Follow the milestone-identification process in `${CLAUDE_SKILL_DIR}/../themes-identify/SKILL.md` (read it now) under its **caller contract**: the milestones are the phases chosen in Step 2, the shared specs are already loaded, and the status table is regenerated once — by you, in Step 6. Hash all traced requirements in one pass with the batch recipe from `prd-schema.md` and reuse the results throughout Steps 3-5.

## Step 4: Flesh out the chosen slice

For the chosen milestone(s), depth-first:

1. **Features**: follow the process in `${CLAUDE_SKILL_DIR}/../features-identify/SKILL.md` for the milestone, under its caller contract (specs loaded, table regenerated once in Step 6).
2. **Stories** (if depth includes them): follow the process in `${CLAUDE_SKILL_DIR}/../stories-identify/SKILL.md` for each feature, under its caller contract.

Keep the Socratic pace of those skills — this is still a collaborative session, not batch generation. Ask the user before descending into each feature's stories, so they can stop at any point.

## Step 5: Traceability check

Before finishing, verify:

- Every milestone and feature has a `**Trace**` line with at least one requirement ID and hash (stories only when they narrow the feature's trace). Raise untraced items with the user, as the granular skills do.
- Every trace ID exists in the PRD. A trace pointing at a nonexistent ID is an error — fix it now.
- Report requirements from the chosen scope that no roadmap item traces to — the user decides if that is a gap or intentional.

## Step 6: Regenerate the status table and report

1. Regenerate the status table per `roadmap-table-schema.md`, including the `Trace` column and `Not Planned` rows.
2. Report: phases created, items per level, traceability coverage.

**Recommend**: "Run `/prd:stories-estimate docs/product/roadmap.md <feature>` with the team to size the stories, and `/prd:roadmap-sync` periodically to track progress and requirement drift. Run `/prd:plan` again to flesh out the next phase."
