---
description: Use when the user wants the MemHub companion — the small animal above the prompt that shows what the plugin is doing — turned on, turned off, swapped for another animal, or explained (e.g. "turn on the companion", "activate the goose", "enable my companion", "what is that goose above my prompt", "show me the hippo instead", "turn the companion off", "/memhub:companion"). Checks whether this Claude Code loads it (mods ship in 2.1.287+ behind Anthropic's rollout; nothing local to turn on), shows or hides it, and says what each of its states means.
argument-hint: "[on | off | status]"
allowed-tools: Bash, Read, Edit
---

The companion is a pixel animal drawn in the band above the prompt — Gus the
Goose, Hugo the Hippo, Penelope the Penguin or Popo the Shiba, one per session, picked from the session
id unless the person pins one. It shows, without costing a token, what MemHub
is doing in the session:

| It does this | Because |
| --- | --- |
| Sleeps | nothing is happening |
| Wakes and looks around | Claude is answering, or you are typing |
| Rises and says a rule | a MemHub rule fired on a tool call |
| Says it crossly | a rule **blocked** that call |
| Hops up under a gold `!` and asks, in a gold bubble — every animal in its own way | MemHub proposed a new rule; it is **not active** yet. The bubble names the rule, and its **rule↗** is clickable — click it to open the rule in MemHub Studio, the page the Stop notice links. Buttons inside the bubble, where others say Got it, answer it — **1 Activate**, **2 Reject**, **3 Later** (press the digit from an empty prompt, or click). Activating takes a rulebook or org admin; for anyone else the animal says so and the rule waits in MemHub Studio (the Stop notice carries the link) |
| Shows a heart | you clicked the small ♥ just left of its ground: that pets it (asleep, it wakes first; saying a rule, the click is Got it and the bubble goes; a proposal is never dismissed by a click) |
| Opens your browser | you clicked a proposal's **rule↗** (or the rule's name on the "new rule waiting:" row): that rule's page in MemHub Studio. Where the machine has no `open` / `xdg-open` (SSH, a container) the click does nothing |

It ships inside this plugin as a Claude Code **mod** (a plugin of function
hooks, `hooks/hooks.json` → `companion/register.ts`). Mods ship in Claude
Code **2.1.287**, and an installed, enabled plugin's mod loads with the plugin
— **where Anthropic's server-side rollout of mods has reached the account**.
Nothing on the machine turns that rollout on or off. The old early-access
switch, `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS`, no longer does anything (set to
`1` it does not get past the rollout; set to `0` it does not stop a mod); a
copy left in `~/.claude/settings.json` is harmless and can be removed.

**Claude Code only** — in the terminal and in the Claude desktop app's Code
tab. Codex and Cursor have no equivalent band; say so and stop if the user is
on either. On the desktop the band is drawn as a picture rather than terminal
cells, which changes three things: a proposal's **Activate / Reject / Later**
buttons sit on the "new rule waiting:" row under the animal, not inside the
bubble; the rule opens from its name on that row, since the bubble's **rule↗**
is not clickable there; and a bubble says at most three lines, so the card
above the prompt stays short.

## `status` (also what to run first for `on`)

```bash
claude --version
claude plugin list 2>/dev/null | grep -iE -A2 'memhub' || true
# Runs the companion's own tests. Claude Code refuses to run them, naming the
# rollout switch, when mods are not on for this account.
claude plugin test "${CLAUDE_PLUGIN_ROOT}" 2>&1 | grep -iE 'rollout|turned off|^ *[0-9]+ (pass|fail)' | head -3
python3 - <<'PY2'
import json, pathlib
p = pathlib.Path.home() / ".claude" / "settings.json"
env = (json.loads(p.read_text()) if p.exists() else {}).get("env", {})
if "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS" in env:
    print("settings.json: obsolete CLAUDE_CODE_ENABLE_FUNCTION_HOOKS is still set (harmless)")
PY2
```

- Older than 2.1.287: tell them to update Claude Code (`claude update`) and
  restart, rather than setting the old variable.
- Plugin not listed or disabled: it has to be installed and enabled
  (`/plugin`); the companion comes with it.
- The test line says **"the rollout switch served off"**: mods are not on for
  this account yet. Say so plainly: there is nothing to set — not the old env
  var, not a setting — and it appears on its own once the rollout reaches
  them (a new session picks it up). Everything else in the plugin (capture,
  the Rulebook) works without it.
- Tests pass, version and plugin fine: the companion loads. If no animal is
  showing, it was hidden with `/<animal> off` — any animal's command
  (`/goose`) brings it back.

## `on`

1. Run the `status` block and fix what it names (update Claude Code, enable
   the plugin; a rollout that has not reached them is only waited out). If the animal was hidden, `/goose` (or any animal) shows it
   again. A restart is needed only after an update or a fresh install.
2. Then tell them what they will see, in one line each: it sleeps while idle,
   watches while Claude works, and stands up to announce a rule — or hops up with a newly
   proposed one and asks: press 1 to activate it, 2 to reject it, 3 for later.
   Clicking the ♥ beside it pets it, and a proposal's **rule↗** opens that
   rule in MemHub Studio. Each
   session gets its own animal, picked from the session id; each animal is
   its own command — `/goose` for Gus, `/hippo` for Hugo, `/penguin` for
   Penelope, `/shiba` for Popo — and running one switches **this session** to it. `/hippo always`
   pins Hugo for every new session (`/hippo random` undoes it), and
   `/penguin never` / `/penguin include` leave Penelope out of, or put her
   back in, the random pick. `/goose off` hides it, `/goose` brings it back,
   `/goose demo` plays the whole loop — a rule firing, a rule blocking, and a
   new rule proposed with its Activate / Reject / Later buttons —
   `/goose propose` loops just the proposal, `/goose pet` the pet (every
   animal has both), and `/goose scale 1-4` sets how chunky it is. The demo's
   buttons only say what they would do; nothing reaches MemHub until a real
   proposal arrives.

## `off`

`/goose off` in the session — any animal's command hides whichever is
showing. It is remembered across sessions, and running that command again
brings it back. The companion has no separate switch beyond that: it is part
of the plugin, and disabling the plugin would also stop capture and the
Rulebook hooks, so do not suggest it for this. Do **not** remove an env var to
turn it off — `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` no longer does anything.

## Which animal

`plugins/memhub-staging/companion/animals/` holds them, one folder each, and
every one is its own command: Gus is `/goose`, Hugo is `/hippo`,
Penelope is `/penguin`, Popo is `/shiba`. Which one a session shows, first match wins:

1. the animal run in **this session** (`/hippo`) — remembered under the
   session id, so a resume shows it again;
2. the **pin**, `/<animal> always` — for every new session; `/<animal> random`
   drops it;
3. otherwise the **session id** picks, from every animal except those left
   out with `/<animal> never` (`/<animal> include` puts one back; the last one
   cannot be left out).

A `/clear` or `/resume` moves to another session id, so it may bring a different animal. A new animal is written to
the contract in `companion/animal.ts`; in the development repo
`docs/companion/ANIMALS.md` is the guide and `docs/companion/DESIGN-BRIEF.md`
is what to hand a designer.
