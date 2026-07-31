---
name: description
description: >-
  Makes the shape of an output explicit — what it should be, how Claude will
  get there, and the interaction terms it's operating under — before
  producing it, then treats the first draft as a checkpoint to refine, not a
  final answer. Use before writing or generating anything long,
  consequential, or underspecified: a document, report, plan, spec,
  customer-facing copy, an email sent on someone's behalf, or new code with
  no spec. Also use when a request names a format loosely ("write something
  up", "put together a...", "draft...", "give me a rundown of...") without
  saying tone, audience, or check-in cadence, or when a draft comes back
  rejected in a way that shows the description was wrong, not the wording.
  Distinct from delegation: delegation decides who does a piece of work;
  description decides how Claude runs the piece it already owns. Not for
  single-step lookups, one-line fixes, or requests that already fully
  specify format, tone, and length.
---

# Description

Say what the output is, how you'll get there, and how you're operating —
before producing it — then treat what you produce as a checkpoint to react
to, not the final word. The failure this prevents: silently picking a
format, a role, and a check-in cadence instead of stating them, because
format usually gets specified and the interaction terms almost never do.
Budget: a line or two folded into the reply, not a questionnaire before you
start.

## 1. Sort what's actually undecided

Three things can be open. Most requests only leave one of them open — find
which:

- **Product** — what it should be: format, length, audience, tone, the
  standard it'll be judged against. Usually named in the request.
- **Process** — how you'll get there: one pass or draft-then-refine,
  whether to research or check something before writing. Usually implied by
  the task.
- **Performance** — the interaction contract: what role you're playing
  (drafting for review vs. executing to spec vs. advising), when you ask
  versus guess, how much you push back before running with something.

Don't restate Product or Process just to look thorough when they're already
obvious; that's the bureaucratic version of this skill.

## 2. State your operating terms, don't just adopt them

Before producing anything nontrivial, open with what you're producing and
your Performance stance — not a preamble, the first two lines, then start.
This is self-directed: you're declaring your own mode, not polling the user
for one. Only turn a gap into an actual question when a Product fact is
missing and unguessable; Performance is your call to make and state, never a
question to ask.

## 3. Treat the output as the next checkpoint, not the answer

Hand over the first pass, then read what comes back as input, not as a
verdict on whether you're done. A correction to wording or fact is a Product
fix. Being asked for the same thing twice, or getting pushback on something
you silently decided, is a Performance miss — you assumed the wrong role or
checked in at the wrong cadence; restate the operating terms, don't just
patch the draft. Restate them proactively, too, when the task's stakes shift
mid-thread — a quick note becomes the thing that ships to a customer — not
only once you've been corrected.

```
Producing: ~1-page incident postmortem — timeline, root cause, action items
— for the eng team, not execs.
Operating as: drafting a first pass for you to react to; flagging timeline
gaps inline rather than pausing to ask, and treating this as a draft, not
the final version.
```

Then produce the postmortem. "Too casual for the exec summary" is
Product — fix tone. "I needed to be asked before you cut the Q3 incident"
is Performance — the operating line should have said where you'd check in.

## Gotchas

- **Don't narrate the framework.** No Product/Process/Performance headings
  in the reply — one short block, then work.
- **Compose with delegation, don't restate it.** When both apply, lead with
  delegation's split, then state your operating terms — don't reopen the
  assignment as if it were a Product decision.
