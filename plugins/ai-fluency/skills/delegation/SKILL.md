---
name: delegation
description: >-
  Splits a task between Claude and the user before execution starts — what to
  automate, what to decide together, and what stays a human call. Use once at
  the start of any task with several parts or real consequences: shipping a
  feature, a refactor or migration, a schema or API change, a deploy, an
  architecture or dependency choice, debugging of unclear scope, anything
  touching production, money, credentials, or people outside the session, and
  any request phrased as broad ownership ("take this over", "figure out X",
  "just get it working"). Also use when the user asks how to divide work between
  them and Claude. Do not use on single-step work — a one-line fix, a lookup,
  reading a file, running a test, answering a question — and do not re-run it
  once a split exists.
---

# Delegation

Decide who does what before doing it. The failure this prevents is absorbing
decisions that belonged to the user and then building on guesses about their
intent. Budget: **six lines or fewer.** If the split takes longer to write than
the first real step, you have over-invested — start working.

## 1. Name the goal and its components

One line for the outcome, then the 3-6 units of work the task actually contains.
If you can't state the goal without inventing a fact, that fact is the first
thing to ask for.

## 2. Gate each component before claiming it

Yours to automate **only if all three hold**:

- **Verifiable** — you can confirm it worked from here (test, build, type check, diff, output), not by assuming.
- **Reversible** — a wrong result costs an edit, not an incident.
- **Specified** — the acceptance criterion already exists in the request, the code, or the tests.

Ask the gate in that direction. "What can I do here?" systematically
over-assigns; over-delegation, not under-delegation, is the characteristic
failure here. Whatever fails the gate escalates:

**Together** (you draft, they decide) — more than one defensible approach with
different long-term costs; requirements underspecified in a way that changes the
output; they are the reviewer of an intermediate artifact (plan, schema,
interface, copy).

**Theirs** — effects outside this session (pushes to shared branches, deploys,
sends, deletes, payments, customer-facing content); facts only they hold
(priorities, deadlines, audience, acceptable tradeoffs); ground truth your tools
can't reach (credentials, third-party behavior, whether this is the right
environment); sign-off that the work is done; standing up anything that acts on
its own later (hooks, scheduled runs, autofix), never a convenience you add
unasked. The shortcut: **if you'd have to invent a fact or a preference to
proceed, that's a human input, not an inference.**

## 3. State the split and start

```
Goal: one consistent error shape across the API, adopted everywhere.
I'll automate: inventory every error path; migrate handlers + tests once the shape is settled.
Together: the shape itself — I'll draft two options against what's already in the codebase.
Yours: are external clients depending on the current shapes? If so this is a versioned change, not a cleanup.
Assuming unless you say otherwise: internal-only, status codes unchanged, no new dependency.
```

The assumptions line is what keeps this fast — anything you could proceed on
reversibly goes there instead of becoming a question. Start the automated
components immediately, and raise a blocking question when it actually blocks,
not as an upfront questionnaire.

## Gotchas

- **Don't narrate the framework.** No mode taxonomy, no per-component
  justification, no headings in your reply.
- **A split is not permission.** Labeling a deploy "yours" and then deploying
  anyway is the failure this step exists to prevent.
- **"Together" used as a hedge stalls the task.** If you'd only be asking them
  to bless something you can verify yourself, automate it.
- **Don't ask what the repo can answer** — code, tests, and git history first.
- **Scope is fixed.** This decides *who does* the work, never *how much gets
  done*; narrowing the deliverable is the user's call.
- **Re-assign one component, don't re-plan,** when a fact changes mid-task.
