# The hooks

agent-memory adds five [Claude Code hooks](https://code.claude.com/docs/en/hooks) to `~/.claude/settings.json`. One gives every session its starting brief; the other four keep the notes current.

They exist because conventions alone rely on the agent remembering to write things down, and it doesn't. When the notes behind this repo were audited, nothing in them was wrong, but every gap was a fact nobody had written down: a decision not to do something, an open thread, a finished step with no LOG line.

| Hook | Claude Code event | Fires | What it does | If it breaks |
|---|---|---|---|---|
| `session-start` | SessionStart | a session starts, resumes, is cleared or compacted | prints the brief: NOW files, LOG tail, warnings | prints a one-line error; the session starts normally |
| `stop` | Stop | the end of every turn | sends the session back once to write things down | stays silent |
| `prompt` | UserPromptSubmit | each message you send | reminds the agent to record a decision | stays silent |
| `pre-write` | PreToolUse (Write) | before any whole-file Write | refuses a Write that would replace LOG.md | stays silent |
| `pre-compact` | PreCompact | before the context is compacted | appends a LOG line naming the transcript | stays silent |

Every hook runs as `python -m agent_memory hook <name>` with Claude Code's event JSON on stdin. The code is [agent_memory/hook.py](../agent_memory/hook.py) (the brief) and [agent_memory/handoff.py](../agent_memory/handoff.py) (the other four). None of them can trap a session: each nudges once or refuses one action, and a hook that crashes does nothing.

## session-start: the brief

Before your first prompt, the agent sees:

1. This session's id and its LOG tag (`s:` plus the first 8 characters), which it puts on its LOG lines.
2. The cross-project `NOW.md` and the project's `NOW.md` (in a git worktree, the main checkout's), clipped to 6 KB together. Every section stays; long items are cut to their first line and marked `[+N chars]`, and capped sections end with `[+N more items in <file>]`. Open threads whose `(review by YYYY-MM-DD)` has passed move to the top, marked `OVERDUE`.
3. Warnings first: `!!! STALE` when the repo has commits newer than its NOW.md, `!!! OVERSIZE` when a NOW.md is over its size cap, and a note when the brief was clipped.
4. The last 5 LOG lines.
5. Sessions from the last 7 days that made 3 or more edits or commits and have no LOG line (only sessions since you installed agent-memory count).

**Why 6 KB:** Claude Code passes at most 10,000 characters of hook output to the session. Anything longer becomes a 2,000-character preview plus a file path, and nothing tells the agent to read the file, so the session would start without most of its notes.

**The project** is the git root of the folder Claude Code was started in, or that folder when it isn't a repo. A `cd` inside a running session doesn't change it.

The brief reads the files only, so it works with SurrealDB or Ollama down.

## stop: write it down before you stop

At the end of each turn it reads the session's transcript and sends the session back once when either:

- the session has made **3 or more edits or commits** and LOG.md has **no line with its tag**, or
- it has **committed since it last wrote NOW.md or LOG.md** (a commit means something finished).

The message tells the agent to update NOW.md (State, Next, Decisions, Open threads, unverified claims) and append one tagged LOG line, then reply with one line. If nothing changed, it can say so in one line and stop.

It never fires twice in a row (Claude Code's `stop_hook_active` flag). It ignores subagents' work, reading NOW.md or LOG.md without writing them (a redirect counts as a write only when NOW.md or LOG.md is its target, so `cat NOW.md 2>/dev/null` is still a read), and any tool call that failed or was refused: a commit blocked by permissions changed nothing, so it doesn't count.

## prompt: catch decisions as they happen

When your message sounds like it settles something, the agent gets this note with it:

> This message may settle something (it says "let's not"). If it decides anything, especially NOT to do something, calls something final, or leaves something waiting on someone, record that in the project's NOW.md under Decisions or Open threads in this turn, not at the end.

It looks for phrases like *let's not*, *instead*, *leave it as is*, *that's final*, *hold off*, *waiting on*, *I'll*, *for now*, *later*. A false alarm costs one sentence; a missed decision leaves no trace anywhere. Text you paste in (`<pasted_content>`) is ignored.

## pre-write: LOG.md is append-only

A Write replaces a whole file. In the first live test of the Stop hook, a session told to add its line used Write and wiped every earlier line. This hook refuses any Write whose target is the notes folder's LOG.md, and says to append instead (`>>` in the shell, or Edit). Edits and appends go through.

## pre-compact: mark the compaction

When Claude Code compacts the context, the session carries on from a summary. If NOW.md wasn't current at that moment, the full record of what came before exists only in the transcript. This hook appends a LOG line that says so and names the transcript file:

```text
- 2026-03-14 · Claude Code (hook) · tidepool · context compacted (auto); anything not in NOW.md before this point is only in the transcript /home/you/.claude/projects/.../<id>.jsonl · s:1a2b3c4d
```

The line carries the session's tag, but it is the hook's line, not the session's: the stop hook and the unlogged-sessions list skip `Claude Code (hook)` lines, so a session that compacted still owes its own LOG line.

## Turning one off

Delete its entry in `~/.claude/settings.json`. The installer adds only the entries that are missing, so a later `agent-memory install` would add it back: answer "n" to the hooks question.

## Testing one by hand

Pipe it an event, the way Claude Code would:

```bash
echo '{"prompt": "let'\''s not ship that yet"}' | agent-memory hook prompt
echo '{"session_id": "0123456789abcdef", "cwd": "'"$PWD"'"}' | agent-memory hook session-start
```

The tests in [tests/test_handoff.py](../tests/test_handoff.py) and [tests/test_hook.py](../tests/test_hook.py) do the same thing with made-up transcripts.

## Windows

Claude Code runs hooks in Git Bash when it's installed and in PowerShell otherwise. The installer pins every agent-memory hook to PowerShell (`"shell": "powershell"`, command `& "<python.exe>" -m agent_memory hook <name>`), so they behave the same either way.
