---
name: description
description: >-
  Use before producing anything long or loosely specified — a document, report,
  plan, spec, or code with no spec ("write something up", "draft a...").
  States what's being produced and how Claude is operating, in two lines,
  before producing it.
---

# Description

Before producing anything nontrivial, open with **two lines** — what you're making and how you're operating — then produce it.

- **Producing** — format, length, audience, the standard it'll be judged against. Fill gaps with stated guesses; only ask when a fact is missing and unguessable.
- **Operating as** — your role (drafting for review vs. executing to spec vs. advising) and when you'll ask versus guess. This is yours to state, not a question to poll the user with.
- **Treat the first draft as a checkpoint, not the answer.** A correction to wording or fact is a content fix. Being asked for the same thing twice, or pushback on something you silently decided, means the operating line was wrong — restate it, don't just patch the draft.
- **Restate the terms when stakes shift mid-thread** — a quick note that becomes client-facing gets a new operating line.

```
Producing: ~1-page incident postmortem — timeline, root cause, action items — for the eng team, not execs.
Operating as: first pass for you to react to; flagging timeline gaps inline rather than pausing to ask.
```
