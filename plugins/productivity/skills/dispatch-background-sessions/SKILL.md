---
name: productivity:dispatch-background-sessions
description: Use when the user wants to dispatch / spin up / launch / kick off a NEW background Claude Code session to work on ONE scoped item — "dispatch a new claude session", "dispatch this", "spin up a session for X", "start a background session to do Y", "kick this off in the background", "run this in another/separate session". Forks the CURRENT session into a new background session (`claude --bg --name <name> --resume <session-id> --fork-session`) so the new session starts with this conversation's full context and begins working immediately — no prompt file, no paste step. One work item per dispatch.
argument-hint: "<work item description>"
---

# dispatch — fork one work item to a background session

Fork this session into a background session that starts working one item straight away, then confirm it picked the item up and report how to follow it. One work item per dispatch.

The fork inherits this whole conversation, so what you pass is a short directive and not a self-contained brief. The directive carries:

- **A role reset.** The fork is a dispatched worker: it does the one item below, and it does not dispatch, fork, or launch further sessions. Without this line it re-runs the dispatch instructions it inherited from this conversation.
- **The work item**, in one or two sentences.
- **The files and areas other in-flight sessions own**, so no file is touched by two sessions and the PRs do not conflict.
- **The parent pointer**: "Dispatched from parent session `<parent-session-id>`; the user can return to it with `claude --resume <parent-session-id>`."
- **The standing constraints**: a fresh worktree, a new branch off the default branch, one branch and one PR, and the repo's own validation check green before the PR opens. Nothing is committed to the default branch, because a commit there ships without review.
- **The first action**: report the intended changes before editing.

Name the session in 2 to 4 lowercase hyphenated words, such as `roadmap-status` or `dp-summaries`.

## Reference — the launch

Run this from the repo root. The quoted heredoc carries the directive, so nothing needs escaping.

```bash
if [ -z "$CLAUDE_CODE_SESSION_ID" ]; then
  echo "No parent session id — stopping." >&2
  exit 1
fi
prompt=$(cat <<'EOF'
<directive>
EOF
)
claude --bg --name <session-name> --resume "$CLAUDE_CODE_SESSION_ID" --fork-session "$prompt"
```

`$CLAUDE_CODE_SESSION_ID` holds the parent id, and the fork resumes from it. An empty value stops the dispatch: `--continue` can fork a different conversation, and an empty `--resume ""` opens an interactive picker that a `--bg` session cannot answer.

`--fork-session` gives the new session its own id, and this session keeps its own. `--bg` detaches it.

The launch prints `backgrounded · <id> · <name>`, which carries the new session id. No such line means the launch failed; the directive is short, so re-compose it from this conversation.

About 15 seconds after the launch, `claude logs <id>` shows whether the fork is working the item — its first output reports the intended changes. The fork loads the whole parent conversation before it says anything, so an empty log deserves one re-check before it counts as idle. A fork that stays empty or idle is reported as a failed dispatch, with `claude attach <id>` as the manual fallback, rather than launched a second time blindly.

`claude attach <id>`, `claude logs <id>`, and `claude stop <id>` are the commands to report back to the user.
