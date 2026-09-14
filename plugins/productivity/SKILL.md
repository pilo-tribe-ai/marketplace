---
name: productivity:productivity
description: When the user wants to move work between sessions and agents — wrap up and hand off a conversation, dispatch a task to a background session, or tear down a finished worktree — this primer surfaces the productivity toolbox so the model knows which skill to reach for.
---

# productivity — session productivity toolbox

The productivity plugin bundles small, model-callable skills for moving work between sessions and agents:

- **`handoff`** — compact the current conversation into a handoff document for another agent to pick up. Renders the document directly in the reply (no file written), suggests follow-on skills, references existing artifacts by path instead of duplicating them, and redacts secrets.
- **`dispatch-background-sessions`** — hand ONE scoped work item to a separate background session in a single call: fork the current session with a short directive so the new session starts with this conversation's full context and begins working immediately.
- **`wrapping-up-sessions`** — tear down a finished session's workspace: verify nothing is uncommitted/unpushed, then remove the worktree and local branch, return to the default branch, and pull latest.

These are independent utilities, not a single automated loop: `dispatch-background-sessions` hands a scoped item out to a fresh background session, while `wrapping-up-sessions` tears down the worktree of whatever session it is *run inside* once that session's work has landed (the teardown is in-session — it cannot reach across and clean up a different session's workspace). `handoff` carries context across a single session boundary.

This primer is a landing page, not a decision tree — each skill's own `description` carries the trigger logic. The umbrella's job is purely to make sure the model knows the skill names exist when the user's phrasing is generic.
