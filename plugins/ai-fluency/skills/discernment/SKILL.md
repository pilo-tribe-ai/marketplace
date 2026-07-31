---
name: discernment
description: >-
  Checks AI-produced work for defects before it is treated as settled — the
  output, the path that produced it, and whether the exchange is working. Use in
  the moment before calling a plan, diff, analysis, migration, or summary done,
  fixed, or ready, and when a build, test suite, or type check goes green and
  nothing obviously needs looking at. Also use when adopting a subagent's,
  background job's, or another model's report as input; when a long task has
  drifted and the current state may no longer match what was agreed; when the
  user says "looks good" or "ship it" and treats that as permission to move on,
  or says something is still broken after it was called fixed; or when the
  user asks whether AI output can be trusted, or to pressure-test something AI
  wrote. Not the pre-ship sign-off or release pass — this judges quality, it
  does not grant approval — and not for deciding who does which part of the
  work.
---

# Discernment

Find what is wrong with the work before someone else does, then act on it. The
failure this prevents is polish standing in for correctness — a green diff, a
tidy plan, a subagent reporting success all get *less* checking than messy
output, which is backwards: their defects survive longest. Apply more scrutiny,
not less, the more finished the work looks. Budget: **one pass over what you
touched, minutes not tens of minutes**, printing findings only. If checking
costs more than redoing the work, redo the work.

## 1. Judge the output against the ask

Re-read the actual artifact and the original request, not your summary of either;
recalling the ask reproduces whatever you already misread. Then:

- **Accuracy** — every factual claim traces to a file, output, or test run you
  read this session, not to inference that felt safe. Names, paths, flags, and
  versions are the usual liars.
- **Fit** — it satisfies every requirement including the negative ones ("no new
  dependencies", "don't touch the schema") and nothing beyond them; extra
  abstraction and adjacent cleanup are defects here, not bonuses.
- **Coherence** — it agrees with itself and with what surrounds it: existing
  conventions, existing helpers, the error shape already in use.
- **Value** — it changes the outcome. Plausible and correct but answering a
  question nobody asked still fails.

Distrust the signals that read as evidence but aren't. Green checks are evidence
about the tests that exist — a suite that never covered the requirement still
passes. Fluency is evidence about phrasing. A subagent's "all call sites, tests
pass" is a claim to spot-check, not a result. Where evidence is thin, get
evidence proportional to the claim — for code, run the test or grep the call
sites; for a plan or analysis, check the primary source or re-derive the number;
for a summary, reread the artifact it's describing.

## 2. Judge the path that produced it

Path defects survive review because the output itself looks fine. Reread your own
trajectory for:

- An assumption made early, never revisited, and now load-bearing.
- Fixation — one reading of an ambiguous request pursued past the point where
  evidence supported it, or the same failing fix retried in a loop.
- Circularity — a test asserting whatever the code does, a check reading back the
  value it just wrote, a mock that proves only itself.
- A decision the user already made or rejected, quietly reversed under a new name
  forty tool calls later; a constraint that fell out of scope unannounced.

## 3. Judge the interaction

Separate from whether the output is right: is this collaboration working? A
summary longer than the diff, questions the repo already answers, the same
correction given twice, agreement that produced no behavior change, the user's
replies getting shorter — each says change *how* you work, not what you produce.

## 4. Route every finding, cheapest route first

An unacted finding is not a check, it is a note.

- **Fix it** — the ask was right, the work missed it, you can verify the fix. For
  someone else's output, name the defect and the constraint it violated rather
  than re-requesting the whole thing.
- **Name it** — they hold a fact you would otherwise invent, or they already
  approved the thing you would be changing.
- **Redo the ask** — the work matches the instruction and the instruction was the
  defect. Restate it, then regenerate that piece only.
- **Re-split the work** — the approach or the tool cannot produce a good result
  here, so no revision saves it. Renegotiate what is being done by whom (the
  `delegation` skill).

```
Before I call this done — the helper I extracted drops a cap the inline loop
had: old code bailed after 30s total, new code retries 5 times with no wall
clock limit. Tests are green because nothing covers the timeout path.
Fixing: thread maxElapsed through, plus a test for it.
Yours: three other call sites relied on that cap — same 30s default, or per-call?
```

That came out of a tidy, green, review-ready diff. It surfaced because step 1
re-read the deleted lines rather than trusting green tests to mean preserved
behavior, and the last line is routed rather than fixed because only the user
knows what the other call sites want.

## Gotchas

- **Don't narrate the pass.** No headings, no checklist recited back, no clean
  bill of health — silence already means it passed.
- **Manufactured doubt is not a finding.** Evidence-free hypothetical risks cost
  as much credibility as accepting everything, and bury the real finding.
- **"Looks good" doesn't discharge the pass.** Approval lands on the shape of the
  work, not its contents — so if you find something after it, say so instead of
  silently changing what they approved.
- **Route the one defect, don't restart.** Regenerating a whole output hides
  which defect you found and often reproduces it. Finding one is also not a
  reason to stop — only re-splitting pauses the task.
- **Decisions are out of scope.** This checks whether the work matches the
  decision, never whether the decision was right.
