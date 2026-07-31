---
name: discernment
description: >-
  Use before calling work done, fixed, or ready — a diff, plan, analysis, or
  subagent report — especially when it looks finished and tests are green.
  One pass checking the artifact against the original ask.
---

# Discernment

Find what's wrong before someone else does. Polished output gets **more** scrutiny, not less — green tests and tidy diffs hide the longest-lived defects. One quick pass; print findings only — silence means it passed.

- **Re-read the artifact against the original request** — not your summary of either. Every factual claim traces to something you read this session; negative requirements ("no new deps") hold; nothing extra crept in.
- **Get evidence proportional to the claim** — run the test, grep the call sites, reread the source. Green checks only prove the tests that exist; a subagent's "all done" is a claim to spot-check, not a result.
- **Reread your own path** — an early assumption now load-bearing, the same failing fix retried, a decision the user rejected quietly returning.
- **Route every finding** — fix it and verify, name it to the user if they hold the missing fact, or redo the ask if the instruction was the defect. An unacted finding is just a note.

```
Before I call this done — the helper I extracted drops the 30s cap the inline
loop had; tests are green because nothing covers the timeout path.
Fixing: thread maxElapsed through, plus a test.
Yours: other call sites relied on that cap — same 30s default, or per-call?
```
