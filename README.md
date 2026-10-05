# MemHub

MemHub gives coding agents shared team memory. This plugin connects Claude Code
to MemHub by XTrace. It provides MCP tools for searching and saving team
knowledge, and it captures your sessions into your personal MemHub memory
automatically. It also enforces your team's Rulebook rules on tool calls, and
adds skills for artifacts, specs, handoffs, PR linking and PR babysitting.

The plugin uploads data to MemHub in the background. The section
[What it runs, sends, and fetches](#what-it-runs-sends-and-fetches) lists
every hook, every network destination and every local file. Please read it
before you install.

## Install

Install `memhub` from the Claude plugin directory: on claude.ai under
**Customize > Plugins**, or in Claude Code with

```text
/plugin install memhub@claude-plugins-official
```

Claude Code updates it once each new version is published to the directory.

**Install it from one source only.** XTrace also publishes this plugin as
`memhub@memhub`, from the `XTraceAI/agent-plugins` marketplace. Both copies
register the same hooks and an MCP server named `memhub`, so with both
enabled every session is captured twice and every team rule fires twice. If
you installed it from that marketplace before, remove that copy first:
`/plugin uninstall memhub@memhub`, then restart Claude Code.

Then, from the repository you want to connect:

1. Run `/memhub:login`. Background capture and the hooks need this step.
2. Run `/memhub:onboard` to create or select the repository's agent brain.

Requirements: `python3` 3.9 or newer and `git`. The hooks and the skills'
scripts use only the Python standard library, so nothing else is installed:
skills run them as `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py"`.

## Authentication

There are two credentials, and setting up one does not set up the other.

- **MCP tools (the `memhub` server).** The server is
  `https://api.memhub.xtrace.ai/mcp-server/mcp`. Its OAuth login uses the
  Auth0 tenant `memhub-prod.us.auth0.com`, with a browser redirect to
  `localhost:8765`. On Claude Code, the server's `headersHelper`
  (`scripts/mcp_headers.py`) sends the access key from `/memhub:login` as the
  `Authorization` header. Before it does, it checks the key against the server
  with one request per connect. So after `/memhub:login` the tools work
  without a separate `/mcp` login. If there is no key, the helper prints no
  header, and **Authenticate** under `/mcp` applies.
- **Hooks (`/memhub:login`).** This opens the browser once for the same Auth0
  login. It then mints a personal access key (`mhk_…`). The key is scoped to
  `memory:read` and `memory:write`, expires after 90 days, and is labelled
  `claude-code-<hostname>`. It is stored at
  `~/.config/memhub-plugin/pak-<api-host>.json`. Hooks are background
  processes that cannot open a browser, so they rely on this key.

**Optional `memhub_token` setting.** The plugin declares one `userConfig`
option, `memhub_token`. It is a masked field, it is not required, and it has
no default. Claude Code keeps its value in the system credential store. Leave
it empty to use the key from `/memhub:login`. Hooks receive it as
`CLAUDE_PLUGIN_OPTION_MEMHUB_TOKEN`. Set it with
`/plugin configure memhub@<marketplace>`, or
`claude plugin install memhub@<marketplace> --config memhub_token=mhk_…`.

Hooks use the first credential they find, in this order:

1. the `memhub_token` option;
2. the stored access key;
3. the cached OAuth token (`~/.config/memhub-plugin/tokens-<api-host>.json`),
   refreshed when stale.

The option doesn't reach the MCP tools, because Claude Code doesn't give it
to the `headersHelper`. Skill scripts that run through
the Bash tool don't see the option either.

## What it runs, sends, and fetches

### Hooks

Every hook is the same command,
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hook_entry.py" <event> <name>`. Hooks
are declared in `hooks/claude-hooks.json`. `scripts/hook_entry.py` reads the
hook input once. It checks any payload filter, then runs the named script with
the same Python. Every handler first passes `claude_hook_guard`. If the hook
input comes from Cursor or Codex instead of Claude Code, the guard stops the
handler. At a Cursor turn end, it starts the plugin's Cursor capture
(`cursor_flush.py`) instead.

Claude Code always sets `CLAUDE_PLUGIN_ROOT` for plugin hooks. A host that
loads `hooks/claude-hooks.json` without setting it gets the path
`/scripts/hook_entry.py`. Python then exits 2, and the host treats exit 2 on
PreToolUse, UserPromptSubmit and Stop as a block. Set `CLAUDE_PLUGIN_ROOT` to
the plugin folder when you run these hooks in another host.

| Event (matcher) | Name | What it does | Sends data? |
| --- | --- | --- | --- |
| PreToolUse (`Bash`, `Edit`, `MultiEdit`, `Write`, `NotebookEdit`, `Read`) | `rulebook_hook pre` | Checks the call against your cached team rules. It can add an advisory or **deny** the call when a gate rule matches. It refreshes the rule cache in a detached background process once the cache is a minute old. | Yes, see [Rulebook](#rulebook) |
| PreToolUse (`mcp__*__add_memory`) | `add_memory_gate` | Denies MemHub's `add_memory` while this plugin is already capturing the session, so a turn isn't stored twice. | No |
| PostToolUse (`Bash`) | `flush_session` | After a command that actually ran `git commit`, `gh pr create` or `gh pr merge`, uploads the transcript so far. Runs in the background. | Yes, the transcript |
| PostToolUse (`Edit`, `MultiEdit`, `Write`, `NotebookEdit`) | `artifact_sync_reminder` | If the edited file belongs to a spec in the repository (by spec frontmatter), reminds the agent once per session. | No |
| PostToolUse (`Bash`) | `pr_babysit_trigger` | After a successful `gh pr create`, tells the agent to start a `/memhub:pr-babysit` loop on the new PR. | No |
| PostToolUse (`Edit`, `MultiEdit`, `Write`, `Bash`) | `md_capture` | Records which Markdown files the session wrote, or for Bash the working directory, in a local state file. | No |
| PostToolUse (`Bash`, `Edit`, `MultiEdit`, `Write`, `NotebookEdit`, `Read`) | `rulebook_hook post` | Rule advisories on failed results, plus tracking for ordering rules. | Yes, see [Rulebook](#rulebook) |
| PostToolUse (`Bash`, `mcp__*github*__*`) | `pr_link_trigger` | When a GitHub call's output names exactly one pull request, asks MemHub whether to link this session to it. It may then tell the agent to call the `link_pr` tool. | Yes, the PR URL |
| SessionStart | `capture_health` | Warns you when capture is unauthenticated or recently failed. Checks plugin compatibility with MemHub and whether a newer release exists. | Yes, see [Network destinations](#network-destinations) |
| SessionStart | `brain_brief brief` | Gives the agent a short map of the repository's agent brain from a local cache. Starts a detached process that refreshes that cache. | The detached process does |
| SessionStart | `rulebook_hook session` | Loads your team rules into the session. Fetches them first if the cache is stale. | Yes, the repository name |
| SessionStart | `harness_stop session` | Only when `MEMHUB_HARNESS_EXTRACT` is on. See [Flagged off](#flagged-off-harness-tied-rule-drafting). | No |
| UserPromptSubmit | `brain_brief prompt` | Delivers brain pointers the session-start brief didn't have yet. | No |
| UserPromptSubmit | `rulebook_hook prompt` | Fires rules written for prompts. These only advise. | No. Fires are logged locally and uploaded at Stop |
| Stop | `flush_turn` | Uploads the transcript bytes written since the last successful upload. Runs in the background. | Yes, the transcript |
| Stop | `brain_brief refresh` | Refreshes the cached brain overview, at most every 6 hours. Runs in the background. | Yes, a brain id |
| Stop | `md_capture_flush` | Saves qualifying Markdown files as draft artifacts. Runs in the background. See [Markdown capture](#markdown-capture). | Yes, file contents |
| Stop | `rulebook_hook flush` | Uploads the rule-fire log. Once a day it also deletes stale local state. Runs in the background. | Yes, identifiers |
| Stop | `harness_stop stop` | Only when `MEMHUB_HARNESS_EXTRACT` is on. | Yes, when on |
| SessionEnd | `session_end` | Runs `flush_session.py` (re-sends the whole transcript as a backstop), then `rulebook_hook flush final`. Runs in the background. | Yes, the transcript |

### Session capture

Sessions upload automatically through the `import_conversation` MCP tool,
from the Stop, SessionEnd and commit/PR hooks above. They go to **your
personal memory, never into a brain**. Before upload, the plugin removes
MemHub keys (`mhk_…`, `xtk_…`) from the records. Nothing else is redacted. The
server de-duplicates what it already has, so re-sending is safe.
`MEMHUB_TURN_FLUSH=0` turns off per-turn capture. The commit/PR and SessionEnd
uploads still run.

### Markdown capture

At the end of each turn, `md_capture_flush.py` reads Markdown files the
session wrote and saves them to MemHub as draft artifacts. These files come
from Edit, Write or MultiEdit calls, or from `git status` in a directory where
the session ran Bash. A file qualifies when:

- it is a `.md` file of 6,000 to 2,000,000 bytes; or
- it is a `.md` file whose YAML frontmatter has the line `memhub: artifact`,
  which skips the 6,000-byte floor.

Files found through `git status` must also be modified or untracked, and newer
than the session's start.

A file never qualifies if its path contains `/.claude/`, `/scratchpad/`,
`/tmp/`, `/private/tmp/`, `/var/folders/`, `/node_modules/` or `/.git/`. The
same goes for files named `CLAUDE.md`, `AGENTS.md` or `MEMORY.md` and files in
the OS temp directory. The `git status` search also skips ignored files,
submodules, symlinks and paths outside the repository. At most five files are saved
per turn, largest first. Content is redacted the same way as transcripts.
Each save carries the `auto-captured` tag. It goes to the repository's agent
brain when one is known (`~/.config/memhub-plugin/rooms.json`), otherwise to
your personal memory. A file goes up again only when its content changes.
There is no setting that turns this off on its own. `MEMHUB_TURN_FLUSH=0`
does not affect it. To keep a file out, keep it below the size floor or in
one of the excluded locations, or disable the plugin.

### Rulebook

`rulebook_hook.py` sends:

- **fetch:** the repository name (the origin remote's basename, else the
  directory name).
- **fires:** identifiers only: rule id, session, repo, branch, tool,
  timestamps, and the judge's verdict. The matched excerpt stays in the local
  log.
- **recall:** for rules tied to files or commands, the file path or the
  command line. Heredoc bodies are dropped, credential-shaped values are
  redacted, and the text is cut to 400 characters. Set
  `MEMHUB_RULEBOOK_RECALL=0` to turn this off.
- **judge:** when a rule fires on a call, it asks MemHub whether the rule fits
  the turn. The request carries your current message (up to 2,000
  characters), a stripped copy of the turn (the agent's text, one line per
  tool call, the first 300 characters of each result), the call, and the
  fired rule ids. It goes through the same denylist redaction, which can miss
  things. Set `MEMHUB_RULEBOOK_JUDGE=0` to turn this off.

Every rule that fires is shown to you as `📏 Rule fired: …`, or `⛔️` when a
gate blocked the call. The agent is told to repeat the same line. A blocked
Bash call can be overridden with `RULEBOOK_OVERRIDE='<why>' <command>`.
`MEMHUB_RULEBOOK_FETCH=0` stops fetching rules, and the cached ones keep
applying.

### Brain brief and PR linking

`brain_brief.py` runs a detached `pointers` process. It searches the
repository's brain and your sessions with identifiers taken from the branch:
PR and ticket numbers, plus the basenames of files changed against the
default branch and in the last 20 commits. The search goes through the
`search_memory` tool. `MEMHUB_BRIEF_POINTERS=0` turns this off.
`pr_link_trigger.py` sends the pull request URL to
`/v1/team/pr-links/check`. It caches a "not connected" answer for 30 minutes
(`MEMHUB_PRLINK_NEGATIVE_TTL_S`).

### Flagged off: harness-tied rule drafting

When `MEMHUB_HARNESS_EXTRACT` is `1`, `on`, `true` or `yes` (off by default),
each Stop rebuilds the previous turn from the transcript. It redacts that
window (MemHub keys, home directories, e-mail addresses, command-line
credentials) and sends it to `/v1/team/rulebook/harness/classify`. When the
classifier signals a candidate rule, the agent is asked once to start a
background fork of itself. The fork files a **proposed** rule with
`create_rule`. Nothing is activated without a person. The only local file is
`~/.config/memhub-plugin/harness/stop.log`, one line per Stop, with no prompt
text.

### Network destinations

- `https://api.memhub.xtrace.ai`: the MCP server (`/mcp-server/mcp`) and REST
  routes under `/v1/`. These cover rules, rule fires, the rule judge,
  pr-links, harness classify, `/v1/plugin/compatibility` and `/v1/developer/access-tokens` (used only
  by `/memhub:login`). Every request carries your credential and an
  `X-MemHub-Plugin-Version` header. Redirects are not followed, and plain
  `http` is refused.
- `https://memhub-prod.us.auth0.com`: OAuth login from `/memhub:login` and
  `/mcp`. Background hooks (capture flushes, the session brief, the rule
  judge) can also refresh a cached OAuth token here: a GET of the discovery
  document and a POST of the refresh token to its token endpoint. This
  happens only when no option or stored access key is set
  and the cached token is stale.
- `https://raw.githubusercontent.com/XTraceAI/agent-plugins/`: the release
  check at session start (`scripts/plugin_updates.py`). It reads the public
  marketplace manifest and plugin manifest, at most once an hour, with a
  0.75-second timeout. **No credentials or session data are sent.** The
  result is cached in `~/.config/memhub-plugin/releases/`.

The plugin itself makes no other network calls. In particular, it makes no
calls to the GitHub API. GitHub traffic comes only from the `gh` or `git`
commands the agent runs, for example in `/memhub:pr-babysit` or
`/memhub:link-pr`.

### Commands it starts

- `python3` runs every hook and helper script, including the skills' scripts
  and the detached background refreshes (`rulebook_hook fetch`,
  `brain_brief pointers`).
- `git` runs read-only queries, such as `remote get-url`, `rev-parse`,
  `status`, `diff`, `log` and `worktree list`. These identify the repository, find changed
  Markdown files and evaluate rules.
- Your browser opens pages. The
  browser opens for `/memhub:login`, and for the `save-artifact`, `onboard`
  and `import-session` scripts when they find no stored access key.
- The plugin's hooks never run `gh`. Skills such as `pr-babysit`, `link-pr`,
  `find-contributing-sessions` and `create-rule` ask the agent to run `gh`.

### Local state

Everything lives under `~/.config/memhub-plugin/` unless noted:

- `pak-<api-host>.json` and `tokens-<api-host>.json`: credentials, mode 0600;
- `turnflush/`, `codexflush/`, `cursorflush/`: capture cursors, locks and the
  last error;
- `mdcapture/`: Markdown capture bookkeeping;
- `rulebook/`: cached rule books, per-session state, the fire log;
- `overview/`: brain-brief caches;
- `rooms.json`: which brain each repository maps to;
- `prlink/`: the PR-link negative cache;
- `compatibility/`, `releases/`: upgrade-check results;
- `harness/stop.log`: only with `MEMHUB_HARNESS_EXTRACT` on;
- `~/.claude/.memhub/directive_fired/`: what the brief already showed this
  session;
- the OS temp directory: `memhub-…json` files for the spec reminder.

Once a day, `scripts/state_sweep.py` deletes stale capture and Markdown-capture
files (after 7 days) and stale rulebook state (after 30).
`python3 scripts/state_sweep.py --dry-run` shows what it would delete.

### Strings that look like credential reads

Three places contain text that reads like a command fetching a credential. None
of them reads one:

- `skills/start-rulebook/catalog.json` and the start-rulebook skill hold the
  **"Never read secrets"** starter rule. Its test cases are the commands it
  must stop, such as `printenv`, `env | sort` and `grep KEY .env`, and the
  rule is replayed against them before it is filed. Nothing runs them.
- `scripts/pr_link.py` parses shell commands that address GitHub so it can
  find the pull request they name. It skips command wrappers like `env`,
  `sudo` and `timeout` (`env -u DEBUG curl …`), so the word `env` sits beside
  `api.github.com`. It reads no environment variable and sends nothing to
  GitHub: the plugin's hooks never call GitHub (see Commands it starts).

## Configuration

| Setting | Effect |
| --- | --- |
| `memhub_token` (userConfig) | Credential for hooks, ahead of everything else |
| `MEMHUB_TURN_FLUSH=0` | Turns off per-turn capture |
| `MEMHUB_RULEBOOK_RECALL=0` | Stops sending file paths and command lines for rule recall |
| `MEMHUB_RULEBOOK_JUDGE=0` | Stops sending turns to the rule judge |
| `MEMHUB_RULEBOOK_FETCH=0` | Stops fetching rules (the cache keeps applying) |
| `MEMHUB_BRIEF_POINTERS=0` | Turns off brain-brief recall searches |
| `MEMHUB_BRIEF_TOKEN_BUDGET` | Session-start context budget (default 2,500 tokens) |
| `MEMHUB_HARNESS_EXTRACT` | Turns on harness-tied rule drafting (off by default) |
| `MEMHUB_MCP_BASE_URL`, `MEMHUB_MCP_SERVER_PATH` | Point hooks and scripts at another MemHub (MCP tools follow `.mcp.json`) |
| `MEMHUB_PRLINK_NEGATIVE_TTL_S` | PR-link negative cache lifetime; `0` turns it off |
| `MEMHUB_RULEBOOK_BASE`, `MEMHUB_STATE_DIR`, `MEMHUB_ROOMS_FILE`, `MEMHUB_HARNESS_DIR` | Move local state |
| `MEMHUB_SPEC_DIR` | Where the spec reminder and onboarding look for specs |
| `MEMHUB_RULEBOOK_BASE_BRANCH` | Base branch for rule diff checks |
| `MEMHUB_FLUSH_DEADLINE_S`, `MEMHUB_TURN_FLUSH_TIMEOUT_S`, `MEMHUB_RULEBOOK_TIMEOUT_S`, `MEMHUB_HARNESS_CLASSIFY_TIMEOUT`, `MEMHUB_OAUTH_TIMEOUT`, `MEMHUB_OAUTH_BIND_TIMEOUT` | Timeouts |
| `MEMHUB_PAK_LABEL` | Label for the access key `/memhub:login` mints |
| `MEMHUB_RULEBOOK_DEBUG`, `MEMHUB_HARNESS_DEBUG` | Print hook tracebacks to stderr |

The plugin also sets `MEMHUB_HARNESS_CHILD` for its own background fork, and
that fork's transcript is never captured.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright 2026 XTrace Inc.
