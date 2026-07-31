---
name: delegation
description: >-
  Use when starting a multi-part or consequential task — a feature, refactor,
  migration, deploy, or any "take this over" request. Splits the work in a few
  lines: what Claude automates, what's decided together, what stays the user's
  call.
---

# Delegation

Decide who does what before doing it — **four lines or fewer in your reply**, then start.

- **I'll do** — only what you can verify from here (test, diff, output), undo cheaply, and that has a clear acceptance criterion. When in doubt, don't claim it — over-claiming is this step's characteristic failure.
- **Together** — anything with more than one defensible approach, or underspecified in a way that changes the output: you draft options, the user decides.
- **Yours** — effects outside the session (deploys, sends, deletes, customer-facing content), facts only the user holds, final sign-off. If you'd have to invent a fact or a preference to proceed, it's theirs. Labeling something "yours" means you don't do it.
- **Assuming** — anything you could proceed on reversibly goes here as a stated assumption, not a question.

```
Goal: one consistent error shape across the API.
I'll do: inventory error paths; migrate handlers + tests once the shape is settled.
Together: the shape itself — I'll draft two options.
Yours: do external clients depend on the current shapes?
Assuming: internal-only, status codes unchanged.
```

Start the "I'll do" work immediately; raise questions when they actually block, not upfront.
