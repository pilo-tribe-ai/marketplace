---
name: delegation
description: >-
  Splits a task between Claude and the human before execution starts — what to
  automate, what to work through together, and what must stay a human decision.
  Use at the start of any non-trivial task with more than one part: shipping a
  feature, a migration or refactor, an architecture or tooling choice, a
  research-then-decide question, debugging of unclear scope, or any request
  phrased as broad ownership ("take this over", "figure out X", "just get it
  working"). Also use when work already underway turns out to be larger or more
  consequential than it looked, or when the user asks how to divide work between
  them and Claude. Skip single-step edits and pure lookups.
---

# Delegation

Decide who does what before doing it. The failure this prevents is not
laziness — it is quietly absorbing decisions that belonged to the human and
then building on guesses about their intent.

## Workflow

**1. Name the goal in one sentence.** The outcome, not the activity. If you
cannot write it without inventing a fact, that missing fact is the first thing
to ask for.

**2. Break the work into components.** Aim for 3–7 pieces that could be
assigned separately. Don't force an even split — some tasks are 90% one mode.

**3. Check what this session can actually do.** Before assigning anything to
yourself, confirm it: which tools and permissions are live, whether you can
read the relevant code, run the tests, reach the network, see the failing
output, verify the result. Library versions and APIs may have moved since your
training cutoff, so check the code and docs rather than recalling them. An
unverifiable component is not automatable, however easy it looks.

**4. Assign a mode per component** — per component, not once for the task.

- **Automation** — you execute against a spec that already exists. Use when
  success is checkable without the human's taste.
- **Augmentation** — you propose, they steer, iteratively. Use when the goal is
  under-specified or the answer turns on judgment.
- **Agency** — you set something up to act on its own later (hooks, scheduled
  runs, subagents, autofix). Standing up agency is itself a decision the human
  signs off on, never a convenience you add unasked.
- **Human-only** — they decide or act; at most you gather the inputs.

**5. Run the over-delegation pass.** This is the step that earns the skill.
Over-delegation, not under-delegation, is the characteristic failure mode: a
split derived only from "what can I do here?" will systematically over-assign.
Re-read what you just gave yourself and pull back anything that is:

- Irreversible or visible outside this machine — pushing, merging, deploying,
  sending, deleting, spending, changing shared state.
- A preference rather than a correctness question — product scope, an API shape
  or name the team lives with, adopting a dependency, trading rigor for speed.
- Dependent on facts not in the repo or this conversation — deadlines,
  stakeholder intent, which constraint is real, why the strange code is strange.
- The definition of done.
- Cheap for them to answer and expensive for you to be confidently wrong about.

The test: **if you would have to invent a fact or a preference to proceed, that
is a human input, not an inference.**

**6. State the split and start.** Don't wait for approval on the parts that
were yours to begin with.

## Output format

A few lines the user can redirect in one message, not a document.

```
Goal: <one sentence>
I'll handle: <components>
Together: <components where you'll steer me>
Need from you: <the specific decisions or inputs that block me>
Assuming unless you say otherwise: <the guesses I'm running with>
```

The assumptions line is what keeps this fast: anything you could otherwise
proceed on reversibly goes there instead of becoming a question, so the guess
is visible and cheap to correct without turning the handoff into an interview.

## Example

> "Our API error responses are a mess, can you clean them up?"

```
Goal: one consistent error shape across the API, adopted everywhere.
I'll handle: inventory every error path and how it responds today; once the
  shape is settled, mechanical migration of handlers + tests.
Together: designing the shape — I'll draft two options against what's already
  in the codebase.
Need from you: are external clients depending on the current shapes? If so this
  is a versioned change, not a cleanup.
Assuming unless you say otherwise: internal-only, HTTP status codes unchanged,
  no new dependency.
```

What stayed human: whether this breaks clients, and the final shape — both
cheap to ask and expensive to guess wrong.

## For the rest of the task

- Re-split when scope changes materially. A task that grew a database migration
  or a deploy step needs a fresh over-delegation pass, not the original plan.
- Don't re-litigate a split the user already accepted.

Framework definitions, sub-competencies, and sourcing live in
`${CLAUDE_PLUGIN_ROOT}/REFERENCE.md` — read it only if the user asks about the
AI Fluency framework itself, not to execute the workflow above.
