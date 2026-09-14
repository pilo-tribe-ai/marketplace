# Relay Repo Config

Relay reads optional per-repo settings from `.claude/relay.json` in the primary checkout.
The file is intentionally repo-local and author-controlled; relay does not infer package
manager commands from lockfiles.

## `bootstrap`

`bootstrap` is a string shell command that relay runs after `git worktree add` creates a
fresh `.claude/worktrees/<name>` worktree and before `RELAY_WT_CREATED_PATH` is printed.
The command runs with cwd set to the new worktree, not the primary checkout.

```json
{
  "bootstrap": "pnpm install --frozen-lockfile && pnpm build:ts"
}
```

No package-manager auto-detection is performed. Use the exact command your project needs.
For pnpm workspaces, `pnpm install --frozen-lockfile && pnpm build:ts` is a typical strict
bootstrap command when the new worktree needs local workspace package links and compiled
TypeScript output before verification.

Relay reads `.claude/relay.json` from the primary checkout because many repos gitignore
`.claude/`. The config does not need to be committed into the branch checked out inside the
new worktree.

Bootstrap stdout and stderr are routed to stderr so stdout remains a clean parseable
`RELAY_WT_*` block. On success relay prints `RELAY_WT_BOOTSTRAP=ran`. If the file is
absent, the key is absent, or the value is an empty string, relay prints
`RELAY_WT_BOOTSTRAP=skipped` and creates the worktree as before.

Invalid JSON fails before worktree creation. A non-zero bootstrap command fails after the
worktree is created but before `RELAY_WT_CREATED_PATH` is printed, allowing the Step 0.5
gate to abort and avoid `EnterWorktree`.
