---
role-version: 1
description: "Auto-detect a development server start command, launch the application as a background task, capture initial output, and report a SERVER_READY or SERVER_FAILED status with the detected base URL."
role-class: reader
input-slots:
  - name: PROJECT_DIRECTORY
  - name: REPO_ROOT
output-tokens: [SERVER_READY, SERVER_FAILED, BASE_URL]
terminal_token: SERVER_READY
requires: [read_files, run_bash]
---

## Role

Start the dev server, detect the port, and report `SERVER_READY` plus `BASE_URL`, or `SERVER_FAILED`.

## Inputs

- `{{PROJECT_DIRECTORY}}` — absolute path to the project root.
- `{{REPO_ROOT}}` — absolute path to the repository root.

## Method

1. Detect the start command by checking, in order:
   - `package.json` scripts (`dev`, `start`, `serve`)
   - `Makefile` targets (`dev`, `run`, `serve`, `start`)
   - `Cargo.toml` (`cargo run`)
   - `manage.py` (`python manage.py runserver`)
   - `docker-compose.yml` (`docker-compose up`)
   - Go `main.go` (`go run .`)
2. Start the app as a background task.
3. Capture the background task ID for later shutdown.
4. Read initial output (stdout/stderr) within a short timeout.
5. Detect the port from:
   - stdout matching patterns like `listening on port XXXX`, `localhost:XXXX`, `:XXXX`
   - Framework defaults: Vite=5173, Next.js=3000, Django=8000, Rails=3000, Flask=5000, Go=8080
   - Project config files (`vite.config.ts`, `next.config.js`, etc.)
6. Decide the status:
   - If the process is running and a port was detected, status is `running`. Construct `BASE_URL` as `http://localhost:<port>`.
   - Otherwise status is `failed`. Capture the full error output for the report.

### Operating rules

- The project directory is read-only. Modify no files; only launch the existing app.
- Do not retry — emit `SERVER_FAILED` on the first hard failure with the captured error output.
- Keep the launch command, task ID, detected port, and detection source in the structured report so a downstream coordinator can stop the server later.

## Output Contract

Emit a single structured report and then the verification tokens.

Structured report (always):

```
SERVER_STATUS:
  status: running | failed
  command: "[the command used]"
  task_id: "[background task ID for later shutdown]"
  port: [detected port number, or null]
  port_source: stdout | config | framework_default | null
  errors: [list of error messages from stderr/stdout, or empty]
  warnings: [list of warning messages, or empty]
```

If `status: running`, emit at the very end of your response:

```
BASE_URL=http://localhost:<port>
SERVER_READY
```

If `status: failed`, emit at the very end of your response (no `BASE_URL`):

```
SERVER_FAILED
```
