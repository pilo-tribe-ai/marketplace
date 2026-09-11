---
description: Simulate developer implementation of a PRD, surfacing gaps and uncaptured decision points one requirement at a time
argument-hint: "[prd-file]"
model: opus
context: fork
agent: prd-simulator
allowed-tools: AskUserQuestion, Read, Grep, Bash
---

# PRD Implementation Simulation

Simulate implementing a PRD from a developer's perspective, identifying gaps and uncaptured decision points.

**The output boundary**: the developer persona exists to FIND gaps. Every decision captured goes back into the PRD as product-level behavior or a product constraint — never as a technology choice. Read `${CLAUDE_SKILL_DIR}/../shared/product-hat.md` for the constraint test, and `${CLAUDE_SKILL_DIR}/../shared/prd-schema.md` for the requirement ID format.

## Your Task

Read the PRD at `{{prd}}` (default `docs/product/prd.md` when no argument is given) and simulate what it would be like to implement it as a senior developer.

## Process

### Step 1: Read & Parse

- Load the PRD file
- Identify all requirements by their IDs (PRB, PER, JRN, CAP, SCP, MET, CON, ...)
- Note the overall structure and which lenses are covered (frontmatter)

### Step 2: Scan for Gaps

Review each requirement through your developer validation lenses:
- Behavioral ambiguity
- Missing error paths
- Unstated assumptions
- Integration gaps
- Data questions
- State management
- Performance & scale
- Edge cases

**Important**: Only flag requirements where something is genuinely missing or ambiguous. Skip clear ones silently.

### Step 3: Walk Through Flagged Requirements

For each requirement that has a gap:

1. **Quote** the requirement with its ID, as-is from the PRD
2. **Explain** specifically what's missing or ambiguous from an implementation perspective
3. **Present 2-4 concrete options** via AskUserQuestion, leading with your recommended option. Options describe product behavior ("reject the upload and tell the user why"), not technology ("use S3 multipart upload")
4. If the user's answer reveals new unknowns, probe deeper before moving on
5. Move to the next flagged requirement

### Step 4: Cross-Cutting Concerns

After individual requirements, check for system-level gaps:
- Error handling strategy
- Authentication & authorization model
- Data migration needs
- Backwards compatibility
- Observability requirements
- Performance budgets

Only raise concerns that are actually missing from the PRD.

### Step 5: Simulation Summary

Provide a structured summary:

```markdown
## Simulation Summary

### Readiness Rating: [Ready / Mostly Ready / Needs Work / Not Ready]

### Gaps Found: X
- **Critical** (blocks implementation): [count]
- **Important** (needs clarification): [count]
- **Minor** (nice to have): [count]

### Decisions Made During Simulation
| Requirement | Gap | Decision (product-level) |
|-------------|-----|--------------------------|
| CAP-3: [Req text] | [What was missing] | [Behavior or constraint decided] |

### Open Questions
- [Any questions that couldn't be resolved during this session]
```

### Step 6: Next Steps

**Recommend**: "Run `/prd:save` to update the PRD with the decisions made during this simulation."
