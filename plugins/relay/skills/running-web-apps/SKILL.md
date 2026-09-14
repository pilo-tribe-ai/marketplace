---
name: running-web-apps
description: Idempotent web-app setup wizard (Playwright MCP + permissions + framework detection + .relay/web-app.yaml) and per-run server start + health-check via relay:leaf-reader dispatching roles/server-runner.md. Returns {base_url, dev_command, framework, server_status}.
user-invocable: false
---

# relay:running-web-apps

Idempotent web-app **setup** (run once, skipped when artifacts already exist and are valid) **and** per-run **server start + health-check**. Ported from `plugins/website/commands/setup.md` for the setup phase; delegates server lifecycle via `relay:leaf-reader` dispatching `roles/server-runner.md`.

**Announce at start:** "I'm using the running-web-apps skill to configure and start the dev server."

## Setup Phase (idempotent — skipped when already configured)

Each setup step checks whether its artifact already exists and is valid before acting. If all artifacts are valid, the entire setup phase is skipped and the run phase proceeds immediately.

### Step 1 — Playwright MCP Merge

Read `~/.claude.json`. Check whether any entry in `mcpServers` references `playwright`.

**If NOT configured:**

Add the Playwright MCP server entry to `~/.claude.json`:

```json
{
  "mcpServers": {
    "plugin_playwright_playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"]
    }
  }
}
```

Merge, preserving existing entries and avoiding duplicates (create `mcpServers` if absent).

After merging, warn: "Playwright MCP added to `~/.claude.json`. You may need to restart Claude Code for this change to take effect."

**If already configured:** confirm and continue to Step 2.

### Step 2 — Permissions Merge

Read `.claude/settings.local.json` (create if absent). Ensure all Playwright tool permissions are in the `permissions.allow` array:

```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_playwright_playwright__browser_navigate",
      "mcp__plugin_playwright_playwright__browser_snapshot",
      "mcp__plugin_playwright_playwright__browser_take_screenshot",
      "mcp__plugin_playwright_playwright__browser_resize",
      "mcp__plugin_playwright_playwright__browser_click",
      "mcp__plugin_playwright_playwright__browser_evaluate",
      "mcp__plugin_playwright_playwright__browser_wait_for",
      "mcp__plugin_playwright_playwright__browser_press_key",
      "mcp__plugin_playwright_playwright__browser_fill_form",
      "mcp__plugin_playwright_playwright__browser_type",
      "mcp__plugin_playwright_playwright__browser_hover",
      "mcp__plugin_playwright_playwright__browser_tabs"
    ]
  }
}
```

Merge, preserving existing entries and avoiding duplicates.

**Idempotency check:** if all 12 entries are already present, skip the write.

### Step 3 — Framework and Dev Command Detection

Read `package.json` from the project root. Detect the framework from `dependencies` / `devDependencies`:

| Package key present | Detected framework |
|---|---|
| `next` | Next.js |
| `react` + (`vite` or `react-scripts`) | React (Vite or CRA) |
| `vue` | Vue |
| `svelte` | Svelte / SvelteKit |
| `@angular/core` | Angular |
| `index.html` present, no packages | Static HTML |
| No `package.json` | Unknown |

Detect `dev_command` from `package.json` scripts in priority order:
1. `scripts.dev`
2. `scripts.start`
3. `scripts.serve`
4. `scripts.develop`

If a command is found, use it directly (no user prompt in skill context — the shim is non-interactive). If not found and the caller did not supply a `dev_command` input, emit a warning and default to `npm run dev`.

Detect the expected URL from framework defaults or config files:
- Next.js default: `http://localhost:3000`
- Vite default: `http://localhost:5173`
- Other / unknown: `http://localhost:3000`

### Step 4 — Write Project Config

Write (or update) `.relay/web-app.yaml`:

```yaml
url: <detected_url>
dev_command: <confirmed_dev_command>
framework: <detected_framework>
```

Create the `.relay/` directory if it does not exist.

**Idempotency check:** if `.relay/web-app.yaml` already exists and contains valid `url`, `dev_command`, and `framework` fields, skip the write and read the stored values instead.

---

## Run Phase (every invocation)

### Step 5 — Start Dev Server via roles/server-runner.md

Delegate server startup via `relay:leaf-reader` dispatching `roles/server-runner.md` (§5 resolution
order: role-class=reader → `relay:leaf-reader`). Assemble the prompt by reading `roles/server-runner.md`,
stripping its YAML frontmatter, substituting `{{PROJECT_DIRECTORY}}` and `{{REPO_ROOT}}` slots, and
prepending the standard autonomous preamble. Then dispatch:

```
Agent(agentType='relay:leaf-reader', prompt=<assembled roles/server-runner.md body>)
```

The assembled `roles/server-runner.md` body auto-detects the start command, launches the app as a
background task, and emits one of:
- `SERVER_READY` + `BASE_URL=http://localhost:<port>` — server is up.
- `SERVER_FAILED` — server could not start (error output captured).

### Step 6 — Health-Check and Return

Parse the `roles/server-runner.md` leaf output:

- **`SERVER_READY`:** extract `BASE_URL` from the `BASE_URL=<url>` token. The server is running and the URL is confirmed.
- **`SERVER_FAILED`:** record `server_status: failed`. Surface the failure to the caller. The caller (e.g. the `relay:refining-ui` shim or `relay:running-web-apps` invoker) must handle this by aborting any dependent loop.

Perform a lightweight health-check after `SERVER_READY`: confirm the URL returns a non-5xx HTTP status (smoke check — does the site still load?). If the smoke check fails, treat as `SERVER_FAILED`.

---

## Return Contract

Return a handle dict to the caller:

```yaml
base_url: "http://localhost:<port>"      # confirmed reachable URL
dev_command: "<command>"                 # the command used to start the server
framework: "<detected_framework>"        # e.g. Next.js, React, Vue, Unknown
server_status: "ready" | "failed"        # SERVER_READY → ready; SERVER_FAILED → failed
```

If `server_status: failed`, the `base_url` field is absent. The caller must not proceed with any browser-dependent operations.

---

## Error Handling

- **`~/.claude.json` not writable:** warn the user and continue (Playwright may not work until manually configured).
- **`package.json` absent or unreadable:** set `framework: unknown`, default `dev_command: npm run dev`.
- **`.relay/web-app.yaml` write failure:** warn and continue; use in-memory values for the current session.
