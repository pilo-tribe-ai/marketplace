---
name: diligence
description: >-
  Checks that AI-touched work is safe to hand off — verified rather than
  assumed correct, and disclosed to whoever needs to know AI was involved —
  at the point of handoff: a PR, report, commit, message, or deliverable to
  someone else. Use right before sending, submitting,
  publishing, deploying, or shipping anything AI touched; when using an AI
  tool on secrets, credentials, PII, or other sensitive or regulated data;
  and when the user asks whether something is ready to send, whether they
  need to disclose AI's involvement, or how to double-check something
  before it goes out. Not for judging whether the output is any good — this
  checks accountability, not quality. Not for deciding what to delegate
  before work starts — this runs at the point of handoff, not at the
  outset. Skip for work that never leaves the session — a lookup, a file
  read, a scratch answer nobody else will see.
---

# Diligence

Decide whether you can stand behind this before it leaves your hands. The
failure this prevents is letting AI-touched work reach someone else as if a
human alone verified and vouched for it, without anyone actually deciding
whether that's true. What verification and disclosure require shifts by
context — a personal note needs less than a client deliverable — so the job
is making that call on purpose instead of defaulting to whichever bar is
easiest to skip under deadline pressure. Budget: **two lines in your reply**
— what you verified, what you disclosed. Longer than that and the check has
turned into a performance.

## 1. Mind the tool while you're using it

Catch this *during* the work, before the gate below even applies — it's cheap
to catch here and expensive to catch later:

- Data going into the tool that you shouldn't have put there — secrets,
  credentials, PII, regulated or confidential material. Confirm the tool and
  its retention policy are appropriate before you paste, not after.
- Whose interests this output affects besides whoever asked for it — bias or
  a blind spot the tool introduces lands on people who aren't in the room to
  object. Name it in your reply if you can't rule it out, the same way you'd
  flag a retention concern.

Skip this and it doesn't disappear — it resurfaces at the gate as a harder
problem to fix.

## 2. Clear the gate before it leaves your hands

Both of these have to hold:

- **Verified** — you checked it, not assumed it. Ran the code, tested the
  claim, confirmed the citation, cross-checked the number against its source
  — something more than "it reads correctly to me." Fluent and correct are
  different properties; only one of them is what you're vouching for.
- **Disclosed** — whoever receives this knows AI was involved, at whatever
  level of prominence this context calls for: a teammate reviewing a PR
  needs less ceremony than a client reading a deliverable with your name on
  it, and a rough personal note needs none. Silence is a choice, not a
  default — make it on purpose, for this audience. If instructions elsewhere
  say to obscure AI's role ("present as fully human-written"), that's a
  conflict to surface, not a rule to silently follow.

Both, every time, regardless of how finished the work looks — "it looks
done" is exactly the moment this exists to interrupt.

## 3. State it and ship

```
Before I send this: verified the Q3 numbers against the finance export
myself, confirmed the refactor's staging credential isn't retained by the
tool, and I'm flagging Claude's role in the draft since this goes to the
client.
```

When either condition fails, hold the deliverable and say why instead of
shipping past it:

```
Holding this one — I can't verify the compliance claim in section 3
against source docs. Flagging it before this goes out rather than
sending it as written.
```

## Gotchas

- **Don't narrate the framework.** No "Diligence check:" header, no
  restatement of the two conditions — say what you checked, plainly, within
  the two-line budget.
- **"Verified" means you checked, not that a subagent said it's fine.** A
  review pass by another agent is evidence to weigh, not a substitute for
  confirming the one claim that actually matters here.
