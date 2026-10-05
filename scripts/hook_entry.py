#!/usr/bin/env python3
"""The one command every Claude Code hook in ``hooks/claude-hooks.json`` runs.

    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hook_entry.py" <event> <name>

The Claude plugin directory accepts a hook command only when each path in it
is written in full from ``${CLAUDE_PLUGIN_ROOT}``, with no other variable,
command substitution, wildcard or inline program. Each handler used to be a
small shell program (``IN=$(cat)``, ``case`` globs, the Cursor guard, a
prefilter, then the script); this file is that program, once, in stdlib
Python 3.9, keyed by ``(event, name)`` in ``ROUTES``.

For every route it keeps the shell's exact semantics:

* stdin is read once and handed on with trailing newlines removed, as
  ``IN=$(cat)`` then ``printf %s "$IN"`` did;
* a payload glob is a shell ``case`` pattern over that raw payload (quotes
  in the old ``*"gh pr"*`` were quoting, so it is ``*gh pr*`` here);
* the harness lanes stop unless ``MEMHUB_HARNESS_EXTRACT``, trimmed of ASCII
  whitespace only, is ``1``/``on``/``true``/``yes`` in any case;
* an empty ``CLAUDE_PLUGIN_ROOT`` skips the handler (the flush lane says so
  on stderr);
* ``claude_hook_guard`` gates every lane, then an optional prefilter must
  exit 0, then the script runs with this interpreter and inherits stdout and
  stderr, so a PreToolUse block's exit code and JSON reach Claude unchanged;
* the exit status is the last lane's, or 0 when it was skipped — SessionEnd
  runs its two lanes in order and the first one's failure never stops the
  second.

Scripts are found next to this file, never through the environment.

One difference from the shell is accepted, not fixable here: the empty-root
skip above only runs once this file has been found. If the host leaves
``CLAUDE_PLUGIN_ROOT`` unset, the command is ``python3 "/scripts/hook_entry.py"``
and Python itself exits 2 ("can't open file"), which PreToolUse,
UserPromptSubmit and the synchronous Stop lane read as a block. The directory
forbids the shell fallback that used to absorb this. Claude Code always sets
the variable for plugin hooks; only a host that imports ``claude-hooks.json``
without it is affected.
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, Optional, Tuple

SCRIPTS = Path(__file__).resolve().parent

# The bytes the old shell trim removed: space, \t \n \v \f \r and \x1c-\x1f.
# Exactly what str.strip() drops from ASCII; non-ASCII padding reads as off.
_FLAG_WS = " \t\n\v\f\r\x1c\x1d\x1e\x1f"
_FLAG_ON = {"1", "on", "true", "yes"}


class Lane(NamedTuple):
    guard: str                      # claude_hook_guard action: ignore | capture
    run: Tuple[str, ...]            # script, then its arguments
    prefilter: Optional[str] = None  # must exit 0 before ``run`` starts


class Route(NamedTuple):
    lanes: Tuple[Lane, ...]
    globs: Tuple[str, ...] = ()     # any one must match the payload
    harness: bool = False           # behind MEMHUB_HARNESS_EXTRACT
    loud_root: bool = False         # report an unset CLAUDE_PLUGIN_ROOT


def _one(guard: str, *run: str, prefilter: Optional[str] = None,
         **route: object) -> Route:
    return Route(lanes=(Lane(guard, tuple(run), prefilter),), **route)


ROUTES = {
    ("PreToolUse", "rulebook_hook"): _one("ignore", "rulebook_hook.py", "pre"),
    ("PreToolUse", "add_memory_gate"): _one("ignore", "add_memory_gate.py"),

    # Stage 1 is a cheap test over the whole payload; flush_prefilter.py is
    # the precise stage 2 on tool_input.command alone.
    ("PostToolUse", "flush_session"): _one(
        "ignore", "flush_session.py", prefilter="flush_prefilter.py",
        globs=("*git*commit*", "*gh pr*"), loud_root=True),
    ("PostToolUse", "artifact_sync_reminder"): _one(
        "ignore", "artifact_sync_reminder.py"),
    ("PostToolUse", "pr_babysit_trigger"): _one(
        "ignore", "pr_babysit_trigger.py", globs=("*gh*pr*create*",)),
    ("PostToolUse", "md_capture"): _one("ignore", "md_capture.py"),
    ("PostToolUse", "rulebook_hook"): _one("ignore", "rulebook_hook.py", "post"),
    # All four are needed: see docs/specs/pr-linking-plugin-spec.md §5.1.
    ("PostToolUse", "pr_link_trigger"): _one(
        "ignore", "pr_link_trigger.py",
        globs=("*gh*pr*", "*[Gg]it[Hh]ub*", "*api/v3*", "*repos/*pulls*")),

    ("SessionStart", "capture_health"): _one("ignore", "capture_health.py"),
    ("SessionStart", "brain_brief"): _one("ignore", "brain_brief.py", "brief"),
    ("SessionStart", "rulebook_hook"): _one("ignore", "rulebook_hook.py", "session"),
    ("SessionStart", "harness_stop"): _one(
        "ignore", "harness_stop.py", "session", harness=True),

    ("UserPromptSubmit", "brain_brief"): _one("ignore", "brain_brief.py", "prompt"),
    ("UserPromptSubmit", "rulebook_hook"): _one("ignore", "rulebook_hook.py", "prompt"),

    ("Stop", "flush_turn"): _one(
        "capture", "flush_turn.py", prefilter="turn_flush_prefilter.py"),
    ("Stop", "brain_brief"): _one("ignore", "brain_brief.py", "refresh"),
    ("Stop", "md_capture_flush"): _one("ignore", "md_capture_flush.py"),
    ("Stop", "rulebook_hook"): _one("ignore", "rulebook_hook.py", "flush"),
    ("Stop", "harness_stop"): _one("ignore", "harness_stop.py", "stop", harness=True),

    # One handler, two lanes, in order: Claude Code runs an event's handlers
    # in parallel, and the fire flush can only link rows capture has stored.
    ("SessionEnd", "session_end"): Route(lanes=(
        Lane("capture", ("flush_session.py",)),
        Lane("ignore", ("rulebook_hook.py", "flush", "final")),
    )),
}


def harness_enabled(environ=None) -> bool:
    value = (os.environ if environ is None else environ).get(
        "MEMHUB_HARNESS_EXTRACT", "").strip(_FLAG_WS)
    return value.isascii() and value.lower() in _FLAG_ON


def payload_matches(raw: bytes, globs: Tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(raw, glob.encode()) for glob in globs)


def _guard(action: str, event: str, raw: bytes) -> bool:
    """claude_hook_guard's verdict; any failure skips, as its exit 1 did."""
    try:
        import claude_hook_guard
        try:
            payload: object = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        return bool(claude_hook_guard.route(action, event, payload, raw))
    except Exception:
        return False


def _run(command: Tuple[str, ...], raw: bytes) -> int:
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        code = subprocess.run(
            [sys.executable, str(SCRIPTS / command[0]), *command[1:]],
            input=raw).returncode
    except OSError as exc:
        print(f"[memhub-hook] could not start {command[0]}: {exc}",
              file=sys.stderr)
        return 1
    return 128 - code if code < 0 else code  # a signal, as the shell reports it


def dispatch(event: str, name: str, raw: bytes, environ=None) -> int:
    env = os.environ if environ is None else environ
    route = ROUTES[(event, name)]
    if route.harness and not harness_enabled(env):
        return 0
    raw = raw.rstrip(b"\n")
    if route.globs and not payload_matches(raw, route.globs):
        return 0
    if not env.get("CLAUDE_PLUGIN_ROOT"):
        if route.loud_root:
            print("[memhub-flush] CLAUDE_PLUGIN_ROOT unset; cannot locate "
                  "flush scripts, skipping", file=sys.stderr)
        return 0
    status = 0
    for lane in route.lanes:
        status = 0
        if not _guard(lane.guard, event, raw):
            continue
        if lane.prefilter and _run((lane.prefilter,), raw) != 0:
            continue
        status = _run(lane.run, raw)
    return status


def main(argv=None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    if args not in ROUTES:
        # Non-zero but never 2: an unknown name must not block a tool call.
        print(f"[memhub-hook] unknown hook {' '.join(args)!r}", file=sys.stderr)
        return 1
    return dispatch(args[0], args[1], sys.stdin.buffer.read())


if __name__ == "__main__":
    raise SystemExit(main())
