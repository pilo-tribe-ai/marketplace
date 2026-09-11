---
description: "Set up UI Judge in this repository. Asks about the application, the dev server, the roles, and where the secrets live. Writes .uijudge/config.yaml and .uijudge/credentials.md."
argument-hint: "[base-url]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
---

# /ui-judge:setup

Set up UI Judge in this repository. Run it once. Run it again to change an
answer.

## Step 1 — Check what is already there

Read `.uijudge/config.yaml`. If it exists and is valid, say so, show the
current values, and ask whether to change them. Change only what the person
asks you to change.

## Step 2 — Find out about the application

Look in the repository for the answers before you ask for them:

- `package.json` scripts, for the command that starts the dev server.
- The framework, from the dependency list.
- The port, from the dev script or from a config file.
- A seed or reset script, in the same scripts list.

Then use `AskUserQuestion` to confirm what you found and to fill the gaps:

1. The address the application runs at. Offer what you found.
2. The command that starts it. Offer what you found. Allow "it is already
   running".
3. The command that puts the data back to a known state. Allow "there is none".
4. The people the missions sign in as. Allow "none, it is open to everyone".

## Step 3 — Ask where the secrets live

Ask this once per role. Never ask for the secret. Ask where it lives.

Offer these choices:

- a secret manager command, such as `infisical secrets get NAME --plain`
- an environment variable, named by the person
- ask each time the run starts

Write the answer into `credentials.md` as instructions. This file records only
the place. Never write the value into any file.

## Step 4 — Warn about the target, before you write anything

Read the address you got in Step 2. If it is not `localhost`, not `127.0.0.1`,
and does not hold the word `test` or `staging`, stop and warn:

> This looks like a real site. UI Judge clicks buttons and fills forms. It can
> change real data. Point it at a test copy instead.

Ask for a plain confirmation. Write no file until you have it. This check runs
before Step 5 on purpose: a config that names a real site is the thing that
lets a later run click buttons on that site, so the warning is worth nothing
after the file exists.

## Step 5 — Write the files

Create `.uijudge/` in the repository root. Copy these two templates into it and
fill in the answers:

- `${CLAUDE_PLUGIN_ROOT}/templates/config.yaml` to `.uijudge/config.yaml`
- `${CLAUDE_PLUGIN_ROOT}/templates/credentials.md` to `.uijudge/credentials.md`

The address from Step 2 goes in two places in `config.yaml`: `base_url` and
`allowed_origins`. Put it in both. `/ui-judge:explore` reads `allowed_origins`
before it follows any link, so a list that still holds only the template's
`http://localhost:3000` stops exploration at the application's own front door.

Create `.uijudge/missions/` and put the example mission in it, as
`missions/example.feature`, with `# status: draft`.

Create `.uijudge/.gitignore` with exactly this:

```
runs/
auth/
```

The run folder holds screenshots and logs. The auth folder holds saved browser
sessions. Neither belongs in the repository.

## Step 6 — Set up the browser

Check that the Playwright MCP server is set up. Read `~/.claude.json` and look
for an entry whose key is exactly `plugin_playwright_playwright`. If none is
there, tell the person to add it, and show them this:

```json
{
  "mcpServers": {
    "plugin_playwright_playwright": {
      "command": "npx",
      "args": [
        "-y", "@playwright/mcp@latest",
        "--caps=testing,storage",
        "--allowed-origins", "http://localhost:3000"
      ]
    }
  }
}
```

Put the address from Step 2 in place of `http://localhost:3000`. Separate
more than one origin with a semicolon.

`--caps=testing,storage` is not optional. Without `testing`, the
`browser_verify_*` tools do not exist, and the driver cannot check a `Then`
line. Without `storage`, `browser_storage_state` does not exist, and no
browser session can be saved or restored. Both groups are off by default.

The key must read exactly `plugin_playwright_playwright`. Claude Code builds
each tool name from the key, and the `mission-driver` agent is given tools named
`mcp__plugin_playwright_playwright__browser_*`. An entry under any other key,
such as a plain `playwright`, makes tools the driver was never given, and the
driver then walks every mission with no browser at all.

So if an entry that names `playwright` is already there under another key, say
so and tell the person to rename it. Then read its `args`. If they hold neither
`--caps=testing,storage` nor `--allowed-origins`, say so and show the person
what to add. An entry that exists is not the same as an entry that works.

Warn that Claude Code must restart before a new MCP server works, and after any
change to these arguments.

Then check the Playwright version:

```bash
npx playwright --version
```

Version 1.56 or newer is needed for `/ui-judge:compile`. If it is older, say
so. Everything else still works.

## Step 7 — Report

Say what you wrote, what you found out about the application, and what to run
next:

- `/ui-judge:missions` to write the first missions
- `/ui-judge:explore` to look around first
