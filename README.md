# experimental-plugins

A [Claude Code plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) for Tribe AI.

## Plugins

| Plugin | Description | Comes from |
|---|---|---|
| [`adr`](./plugins/adr) | Write architecture decision records, and ask questions about past decisions | mirror |
| [`ai-fluency`](./plugins/ai-fluency) | Skills operationalizing the AI Fluency framework (Delegation, Description, Discernment, Diligence) | this repo |
| [`engineering`](./plugins/engineering) | Engineering skills: diagnose, tdd, triage, zoom-out, and more | mirror |
| [`git`](./plugins/git) | Interactive rebase, with guided help through conflicts | mirror |
| [`github`](./plugins/github) | Pull requests, issues and milestones, through a GitHub MCP server or the `gh` CLI | mirror |
| [`osaat`](./plugins/osaat) | Do a series of steps one at a time. You confirm each step | mirror |
| [`pr-flow`](./plugins/pr-flow) | Build a PR review system for a repository, then run it | mirror |
| [`prd`](./plugins/prd) | Write PRDs and roadmaps through guided questions | mirror |
| [`productivity`](./plugins/productivity) | Hand off, dispatch and wrap up work across sessions | mirror |
| [`prompt-fit`](./plugins/prompt-fit) | Measure a prompt, skill or plugin against prompt rules, then make it smaller | mirror |
| [`relay`](./plugins/relay) | Multi-agent orchestration. **Needs `superpowers`** | mirror |
| `superpowers` | Core skills: TDD, debugging and collaboration patterns | [obra/superpowers](https://github.com/obra/superpowers) |
| [`thinktank`](./plugins/thinktank) | Multi-agent strategic analysis and deliberation | mirror |
| [`ui-judge`](./plugins/ui-judge) | Open a web application in a browser and check it against its own documentation | mirror |
| [`wiki`](./plugins/wiki) | Build a knowledge wiki in a repository, add sources to it, and ask it questions | mirror |

## Using this marketplace

```
/plugin marketplace add pilo-tribe-ai/marketplace
/plugin install <plugin-name>@experimental-plugins
```

Install `superpowers` before `relay`. Every relay command stops if superpowers
is absent.

```
/plugin install superpowers@experimental-plugins
/plugin install relay@experimental-plugins
```

## Mirrored plugins

The plugins marked **mirror** are copies. They come from a private monorepo,
[`ai-advanced-futures/claude-code-dev-plugins`](https://github.com/ai-advanced-futures/claude-code-dev-plugins).

The copies live in this repository on purpose. You cannot install a plugin from
a repository you cannot read, so a pointer to the private monorepo would fail
for anyone outside it. The copies let anyone install these plugins from this
marketplace.

[`scripts/vendored-plugins.txt`](./scripts/vendored-plugins.txt) lists the
mirrored plugins. Every other directory in `plugins/` belongs to this
repository, and the sync never touches it.

[`.upstream-sync.json`](./.upstream-sync.json) records the upstream commit and
the version of each plugin at the last sync.

### How the sync runs

[`.github/workflows/sync-upstream.yml`](./.github/workflows/sync-upstream.yml)
runs every day at 06:00 UTC. You can also start it by hand from the Actions tab.
It copies the plugins, then opens a pull request on the `sync-upstream` branch
if anything changed. An open pull request is updated, not duplicated.

The workflow needs one secret, `UPSTREAM_DEPLOY_KEY`:

1. Make an SSH key pair with no passphrase.
2. Add the public key to the upstream repository as a deploy key.
   Leave "Allow write access" off. The sync only reads.
3. Add the private key to this repository as the secret `UPSTREAM_DEPLOY_KEY`.

### Running the sync on your machine

You need read access to the upstream repository.

```
$ scripts/sync-upstream.sh
```

To copy from a different branch or tag:

```
$ UPSTREAM_REF=v1.7.0 scripts/sync-upstream.sh
```

Do not edit a mirrored plugin here. The next sync writes over your change.
Make the change upstream.

## Adding a plugin

1. Create the plugin under `plugins/<plugin-name>/`, with a `.claude-plugin/plugin.json` manifest and any `skills/`, `agents/`, `commands/`, or `hooks/` it needs.

   Writing a skill? Run `/writing-skills` first — this repo's
   [authoring guide](./.claude/skills/writing-skills/SKILL.md) covers the quality bar
   and repo conventions.

2. Add an entry to the `plugins` array in `.claude-plugin/marketplace.json`:

   ```json
   {
     "name": "<plugin-name>",
     "source": "./plugins/<plugin-name>"
   }
   ```

   Only `name` and `source` are required here. `plugin.json` is the authority for
   `description` and `version` — don't duplicate them in this entry, since a stale
   copy loses silently.

3. Validate before pushing:

   ```
   claude plugin validate .
   ```

4. Test locally:

   ```
   /plugin marketplace add ./
   /plugin install <plugin-name>@experimental-plugins
   /reload-plugins
   ```

See the [plugin marketplace docs](https://code.claude.com/docs/en/plugin-marketplaces) and [plugin docs](https://code.claude.com/docs/en/plugins) for full schema details.
