---
name: sum
description: End-of-session wrap-up. Writes the project's NOW.md and one LOG.md line so the next session starts from exactly here, and shows a short summary. Use on /sum, and whenever the user is wrapping up, switching machines or agents, running low on context, or asks to "save where we are", even if they never say "sum".
---

# /sum

Goal: the next session continues from exactly here, without re-reading this conversation and without the user explaining anything twice. The reader is an agent that starts cold, takes every line as fact, and acts on it.

## 1. Update the project's NOW.md

The project is the folder this session was started in (its git root). Overwrite its `NOW.md` in place; it is current state, not history. Keep the six sections, and write "none" in an empty one: State · Where things live · Next · Decisions (incl. things decided against) · Open threads (waiting on whom) · Gotchas. If there is no NOW.md yet, start from `templates/NOW.md` in the agent-memory repo, and add `/NOW.md` and `/state/` to `.git/info/exclude`.

- **Write what was observed, not what was intended.** "Tests pass" only if you saw them pass this session; otherwise "suite not re-run; last run 14 passed, 1 failed".
- **Every open thread says who or what it waits on.** Add `(review by YYYY-MM-DD)` to anything that should not sit forever.
- **Decisions not to do something go in Decisions.** They leave no trace anywhere else.
- **Anything claimed but not checked says "not verified"** in those words.
- **Absolute dates**, never "tomorrow".
- **No secrets.** Say where a secret is stored, never its value.

## 2. Append one LOG.md line

In the notes folder's `LOG.md` (the session-start brief names it), newest at the bottom:

`- YYYY-MM-DD · <agent> · <project> · <what happened, one line> · s:<id8>`

`<id8>` is the first 8 characters of this session's id; the brief printed it as the LOG.md tag. Several projects: `api + web`.

## 3. Reply

Two to five lines: what was saved where, and anything the user must do before the next session. No sign-off advice.
