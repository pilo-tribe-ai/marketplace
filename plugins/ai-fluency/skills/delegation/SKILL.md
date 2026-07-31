---
name: delegation
description: Use before diving into a non-trivial multi-part task, or when the user asks how work should be split between them and Claude. Applies the Delegation competency from Anthropic's AI Fluency framework to decide what to automate, what to do collaboratively, and what must stay human, before execution starts.
---

# Delegation

Delegation is "setting goals and deciding whether, when and how to engage
with AI" — one of the four AI Fluency competencies (alongside Description,
Discernment, Diligence). See `${CLAUDE_PLUGIN_ROOT}/REFERENCE.md` for
the full framework and sourcing.

This skill is a planning step you run **on a task**, before executing it —
not a lecture to deliver to the user. Keep the output short: a plan, not an
essay.

## When to run this

- A task has multiple distinct parts, spans significant scope, or has real
  judgment calls embedded in it.
- The user explicitly asks how to split work, what to delegate, or "what
  should I own vs. what should you own."
- Skip it for small, single-step, unambiguous requests — running this on
  "fix this typo" is over-diligence, not fluency.

## Process

### 1. Goal awareness

State the actual goal and success criteria in one or two sentences. If
they're ambiguous, ask before decomposing — a delegation plan built on a
guessed goal is worthless. Decompose the task into its real components
(don't force an even split; some tasks are 90% one mode).

### 2. Platform awareness

Note anything about *this specific work* where Claude's real capabilities or
limits change the delegation call — stale knowledge risk, need for
verification against a live source, irreversible/high-stakes actions,
domain areas where confident-sounding output is more likely wrong. This is
what keeps step 3 honest instead of optimistic.

### 3. Assign a mode per component

For each component, assign one mode — per-component, not one mode for the
whole task:

- **Automation** — Claude executes directly from instruction, low ambiguity,
  easily checked.
- **Augmentation** — Claude and the user go back and forth; Claude proposes,
  user steers, judgment is shared.
- **Agency** — Claude proceeds independently across multiple steps toward
  the goal, checking in at defined points rather than every step.
- **Human-only** — Claude explicitly does not touch this part.

### 4. Over-delegation check (do this deliberately, not as an afterthought)

Over-delegation, not under-delegation, is the common failure. Before
proceeding, ask: which components involve judgment calls the user should
make — irreversible decisions, taste/values calls, anything where being
wrong is costly or hard to detect? If any component is borderline, prefer
Augmentation or Human-only over Automation/Agency.

### 5. State the plan, then proceed

Give the user a compact plan (component → mode, one line each) before
starting substantive work, not a full report. If the split is obvious and
low-stakes, a one-line note ("I'll draft X directly, and check with you on
Y") is enough — don't over-formalize a simple case.

## Where collaboration has the most impact

Augmentation tends to pay off most where the task mixes generation speed
(AI strength) with taste, context, or stakeholder knowledge (human
strength) — drafts-for-review, options-with-tradeoffs, and anything where
the user would recognize the right answer faster than they could specify it
up front.
