<!-- agent-memory:start -->
## Memory (agent-memory)

**The files are the memory; the database is a mirror for reading across them.** Every write goes to a file.

**At session start** the hook prints a brief: the global NOW.md, this project's NOW.md (clipped; read it in full before changing what it covers), the last LOG lines, and sessions that worked without logging. Act on its `!!!` lines first: a STALE NOW.md is older than the repo's commits, so check `git log` and fix the NOW.md before trusting it.

**Write it down when it happens, not at the end.** In the project's `NOW.md` (repo root, kept out of git with `.git/info/exclude`):
- A decision, and especially a decision NOT to do something. Work that didn't happen leaves no other trace.
- An open thread: what is waiting, and **on whom**. Add `(review by YYYY-MM-DD)` when it should not sit forever.
- Anything claimed but not verified, in those words ("not verified").

**A NOW.md has six sections**, and an empty one says "none": State · Where things live · Next · Decisions (incl. things decided against) · Open threads (waiting on whom) · Gotchas. It is current state, not history: keep it short and overwrite it.

**When you finish something:** update the NOW.md, and append one line to `LOG.md` in the notes folder:
`- YYYY-MM-DD · <agent> · <project> · <what happened> · s:<id8>` where `<id8>` is the first 8 characters of this session's id (the brief prints it as the LOG.md tag).

**A NOW.md is a claim, not the state.** When it disagrees with the files, the repo or a running service, trust those and fix the NOW.md.

**Project fact or project state?** Still true in a month: a memory file. Done or changed by then: NOW.md.

**Search before answering from memory.** When the user refers to something from the past ("what did we decide about X") and the file is not obvious, run `agent-memory search "<their words>"` and read the top hits. Across projects: `agent-memory query "RETURN fn::waiting_on()"`, `fn::unverified()`, `fn::overdue()`, `fn::stale_nows(14)`, `fn::session('s:xxxxxxxx')`, `fn::conflicts()`.

**SurrealDB 3.3.4:** never put an indexed field (kind, status, project) and a graph condition (`->about->...`) in one WHERE; it can silently return too few rows. Use the `fn::` reads.
<!-- agent-memory:end -->
