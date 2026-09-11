---
description: Write explored findings into the living PRD at docs/product/prd.md — updates the lens section, assigns requirement IDs, maintains coverage frontmatter, and flags drifted roadmap items
argument-hint: "[lens]"
model: opus
agent: prd-analyst
allowed-tools: Write, Read, Edit, Grep, Glob, Bash, AskUserQuestion
---

# Save — Update the Living PRD

Synthesize the findings of this session into `docs/product/prd.md`. The PRD is one living document; you update the sections the session touched and leave the rest alone.

## Before anything

Read both shared specifications:

1. `${CLAUDE_SKILL_DIR}/../shared/prd-schema.md` — file layout, frontmatter, ID and hash rules, migration
2. `${CLAUDE_SKILL_DIR}/../shared/product-hat.md` — the product-level guardrail

## Step 1: Locate the PRD

1. Read `docs/product/prd.md`.
2. **If it does not exist**: check for legacy `docs/prd/*.md` files and run the legacy migration procedure from `prd-schema.md` (offer merge / start fresh). Create `docs/product/` if needed.
3. Parse the frontmatter. If it is missing or broken, apply the repair rule from the schema.

## Step 2: Determine what to save

- If `{{lens}}` was given, save that lens.
- Otherwise, identify which lens (or lenses) this session explored. If nothing was explored in this session, ask the user which section to work on.

## Step 3: Apply the product-hat filter

Review the findings before writing. Anything that fails the constraint test in `product-hat.md`:

- If a product constraint hides inside it, extract the constraint and record it as a `CON-n` entry in `## Product Constraints`.
- Otherwise drop it and tell the user what was dropped and why.

The PRD never contains architecture, technology, or implementation content.

## Step 4: Update the section

1. Find the lens's `## <Section>` heading (create it in catalog order if absent).
2. Rewrite the section to incorporate the new findings. Preserve existing requirement IDs — editing a requirement keeps its ID.
3. Structure within a section:
   - A short narrative (2-5 sentences) framing the findings
   - Requirement bullets: `- **PER-1**: [statement]` with optional indented detail bullets
   - Every statement the roadmap could trace to gets an ID: personas, journey outcomes, capabilities, scope boundaries, metrics, constraints
4. Assign new IDs per the schema: highest existing number per prefix + 1. Never renumber, never reuse.
5. Append new decisions to `## Decisions Log` and unresolved items to `## Open Questions`.

### Writing quality

- Specific, measurable language — no bare "fast", "easy", "better"
- Each requirement is testable from the user's point of view
- Trade-offs and rationale live in the Decisions Log, not inline

## Step 5: Update the frontmatter

- Set the lens status: `in-progress` while gaps remain, `complete` when the lens's "done when" is satisfied. When unsure, ask the user.
- Set the lens `updated` date and the top-level `updated` date to today.

## Step 6: Drift check against the roadmap

If `docs/product/roadmap.md` exists, run the drift check procedure from `prd-schema.md` with scope *changed-IDs* (the requirements you edited or removed in this save) and mode *automatic*. Report every flagged item.

## Step 7: Validate and report

Before finishing, offer one review pass (AskUserQuestion): adjust the section / adjust decisions / looks complete.

Then report:
- Which sections changed and which IDs were added
- The lens coverage state (which spine lenses remain)
- Flagged roadmap items, if any

**Recommend next steps**:
- Spine incomplete → "Run `/prd:explore` to continue with [next lens]."
- Spine complete, no roadmap → "Run `/prd:simulate` to stress-test the PRD, or `/prd:plan` to build the roadmap."
- Roadmap items flagged → "Run `/prd:roadmap-sync` to review the flagged items."
