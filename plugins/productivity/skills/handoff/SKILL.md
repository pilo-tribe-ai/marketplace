---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up.
argument-hint: "What will the next session be used for?"
---

Render a handoff document in your reply that summarises this conversation closely enough for a fresh agent to continue the work. Keep it in the reply and write no file, because the rendered text is the deliverable the user carries into the next session.

Include a "suggested skills" section that names the skills the next agent should invoke.

Reference existing artifacts (PRDs, plans, ADRs, issues, commits, diffs) by path or URL rather than restating them, because a copy goes stale as soon as the artifact changes.

Redact API keys, passwords, and personally identifiable information.

An argument, when the user passes one, names what the next session will focus on. Tailor the document to it.
