---
description: Extract high-level milestones/themes from a PRD document through Socratic questioning
argument-hint: "[prd-file]"
model: sonnet
context: fork
agent: roadmap-analyst
allowed-tools: AskUserQuestion, Read, Write, Edit, Grep, Bash
---

# Identify Themes - PRD to Roadmap Milestones

Extract high-level strategic milestones from a PRD document through collaborative Socratic exploration.

> For end-to-end roadmap generation with scope slicing (MVP, phases), use `/prd:plan` instead. This skill is the granular building block.

## Your Task

1. Read and analyze the PRD (default: `docs/product/prd.md`)
2. Through Socratic questioning, help the team identify 3-5 high-level milestones
3. Create `docs/product/roadmap.md` with traceability back to PRD requirement IDs

Read the shared specifications first:
- `${CLAUDE_SKILL_DIR}/../shared/prd-schema.md` — requirement IDs and hash rules
- `${CLAUDE_SKILL_DIR}/../shared/roadmap-table-schema.md` — status table format

**Caller contract**: when invoked from `/prd:plan`, the shared specs are already loaded (skip the read above), the milestones are the phases the caller chose (skip Steps 1-4 and start at Step 5), and the caller regenerates the status table once at the end (skip Step 7 — but still write the empty sentinel pair described in Step 6, so the caller has something to replace).

**Never overwrite an existing roadmap.** Step 6 creates `docs/product/roadmap.md` only when the file does not exist. When it does exist, insert the new milestones into the existing `## Milestones` section and leave every other milestone, feature, story, and checkbox untouched.

## Process

### Step 1: Read the PRD

Read the PRD file at `{{prd}}` (default `docs/product/prd.md` when no argument is given) to understand:
- Product vision and goals
- Key requirements and features described
- Success criteria and metrics
- Any timeline or priority hints

### Step 2: Summarize Your Understanding

Present a brief summary of what you found in the PRD, then validate:

**Question**: "Does this summary capture the core product vision?"
- **Options**: Yes / Needs adjustment / Missing key aspects

### Step 3: Identify Candidate Milestones

Based on the PRD, propose 3-5 candidate milestones and explore each through questions:

**For each potential milestone, ask:**

1. **Strategic Alignment**
   - "What business outcome does this milestone enable?"
   - Options based on PRD goals (revenue, user acquisition, retention, etc.)

2. **Scope Definition**
   - "What should be IN scope for this milestone?"
   - Options: specific capability clusters from the PRD

3. **Priority & Sequencing**
   - "Where does this milestone fit in the delivery sequence?"
   - Options: Foundation (must come first) / Core (main value) / Enhancement (nice-to-have)

4. **Target Timeline**
   - "What's the target timeframe for this milestone?"
   - Options: Q1 / Q2 / Q3 / Q4 / Next Year / TBD

5. **Success Criteria**
   - "How will we know this milestone is complete?"
   - Help define measurable criteria

### Step 4: Validate Milestone Set

After exploring individual milestones:

**Question**: "Looking at these milestones together, does this roadmap capture the full product vision?"
- **Options**:
  - Yes, this covers the vision
  - Missing a critical milestone
  - Too many milestones, need to consolidate
  - Dependencies between milestones need clarification

### Step 5: Trace each milestone to the PRD

For every milestone, identify the PRD requirement IDs it satisfies (SCP, CAP, PER, ...). Compute the hashes per the rules in `prd-schema.md` — use its batch recipe to hash all requirements in one invocation.

A milestone with no trace is a warning sign — ask the user which requirement drives it, or whether the PRD is missing a requirement.

### Step 6: Generate roadmap.md

Create the roadmap at `docs/product/roadmap.md` (only when it does not exist — see the caller contract above). The file MUST start with the status-table sentinel pair, followed by the body. Write the sentinel pair now, even when Step 7 is skipped, so the table has a place to land:

```markdown
<!-- ROADMAP-STATUS-TABLE:START -->
<!-- ROADMAP-STATUS-TABLE:END -->

# [Product Name] Roadmap

> Generated from: docs/product/prd.md
> Last updated: [current date]

## Overview

[2-3 sentence summary of the roadmap vision]

## Milestones

### M1: [Milestone Name]
- **Target**: [Timeline]
- **Strategic Goal**: [Business outcome]
- **Success Criteria**:
  - [ ] [Criterion 1]
  - [ ] [Criterion 2]
- **Trace**: SCP-1 @a1b2c3, CAP-2 @9f8e7d

#### Features
<!-- To be populated by /prd:features-identify -->

---

### M2: [Milestone Name]
...
```

Placeholder milestones created by `/prd:plan` for phases not yet broken down use status `Not Planned` and contain only the name, the one-line goal, and the Trace line.

### Step 7: Generate Status Table

> **Implementation Note:** The full calculation and regeneration rules are defined in `roadmap-table-schema.md`. Reference that file for the complete algorithm. The steps below are a summary.

After creating the roadmap body, generate the status table at the top of the document:

1. Apply the table schema you read at the start
2. For each milestone identified, create a row with:
   - Sequential number
   - Group assignment (use `-` for sequential, letters for parallel milestones)
   - Milestone ID and name (e.g., `M1: Foundation`)
   - Type: `Milestone`
   - Status: `Not Started` (or `Not Planned` for placeholders)
   - Progress: `░░░░░░░░░░ 0%`
   - Deps: based on sequencing decisions made during exploration
   - Trace: the requirement IDs from the milestone's Trace line (IDs only, hashes stay in the body)
3. Write the table between the `<!-- ROADMAP-STATUS-TABLE:START -->` and `<!-- ROADMAP-STATUS-TABLE:END -->` sentinels written in Step 6 — they sit at the very top of the file, before the `# [Product Name] Roadmap` heading

## Exploration Patterns

### For Milestone Discovery

Ask questions that reveal:
- **Value clusters** - What groups of features deliver value together?
- **Dependencies** - What must be built before other things can work?
- **Risk areas** - What's technically challenging or uncertain?
- **Quick wins** - What can deliver value with minimal effort?

### Challenge Questions

- "Is this milestone too large? Could it be split?"
- "What's the minimum scope that still delivers value?"
- "What happens if this milestone is delayed?"
- "Are there external dependencies or constraints?"

## Completion

When roadmap.md is created:

**Recommend**: "The roadmap with [N] milestones is ready. Next, run `/prd:features-identify <roadmap> M1` to break down the first milestone into features."
