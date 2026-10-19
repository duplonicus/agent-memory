# agent-memory

**Agent memory as plain files, mirrored into SurrealDB: graph links, full-text and vector search in one database, across every project.** Embeddings run locally through Ollama, on your GPU when you have one.

Your coding agent forgets everything between sessions. The usual fix is a notes file per project, and it works until you have twenty of them. Then you can no longer answer simple questions:

- **What is waiting on whom?** Every open thread in every project, with the person or thing it waits on.
- **What did we claim but never check?** "Tests pass", "works on Windows", written down and never verified.
- **Which sessions did work and logged nothing?** Every LOG line carries its session id, so the gap shows up at the next session start.

agent-memory keeps the notes as markdown you can read and edit by hand. A small daemon mirrors them into SurrealDB, so one query answers those questions across all your projects. Built for Claude Code; the conventions work with any agent that reads files.

## What a session sees

A SessionStart hook prints a brief before your first prompt: the cross-project NOW.md, this project's NOW.md, the last LOG lines, and warnings. Overdue threads go first. It is **capped at 6 KB** because Claude Code shows only 10,000 characters of hook output; anything longer becomes a 2,000-character preview, and nothing asks the agent to read the rest. A long NOW.md is clipped per item and marked `[+N chars]`, never cut silently.

```text
=== this session ===
Session ID: 0123456789abcdef (LOG.md tag: s:01234567)

=== ~/dev/tidepool/NOW.md ===
# Tidepool — NOW
Updated: 2026-03-14 by Claude Code · s:9a7f3b11
## State
- Tide charts render from local harmonic math (no NOAA calls at view time); staging is live, production is not.
## Decisions (incl. things decided against)
- 2026-03-10, Sam: decided against a native mobile app; the PWA covers offline charts.
## Open threads (waiting on whom)
OVERDUE - Waiting on Priya: the colour-blind-safe palette for the tide bands. (review by 2026-03-20)
OVERDUE - Waiting on Marco: whether the VPS can take production traffic, or we move to a paid host. (review by 2026-04-01)
- Claimed, not verified: the harmonic math matches NOAA within 3 cm for all 40 stations (checked 6 of them).

=== last 5 of ~/agent-notes/LOG.md ===
- 2026-03-11 · Claude Code · tidepool + garden-sensors · shared the MQTT broker config between both projects · s:e03d6c58
- 2026-03-14 · Claude Code · garden-sensors · decided against solar panels for now; started a 30-day battery test · s:7f3a91c2
```

When the repo has commits newer than its NOW.md, the brief opens with `!!! STALE`. When sessions edited files but never wrote a LOG line, it lists them by tag.

## Ask across projects

```text
$ agent-memory query "RETURN fn::waiting_on()"
garden-sensors · Waiting on Ines: whether the shed has a spare outlet for the gateway. (review by 2026-03-21)
tidepool · Waiting on Marco: whether the VPS can take production traffic, or we move to a paid host. (review by 2026-04-01)
tidepool · Waiting on Priya: the colour-blind-safe palette for the tide bands. (review by 2026-03-20)

$ agent-memory query "RETURN fn::unverified()"
tidepool · Claimed, not verified: the harmonic math matches NOAA within 3 cm for all 40 stations (checked 6 of them).

$ agent-memory query "RETURN fn::session('s:e03d6c58')"
- 2026-03-11 · Claude Code · tidepool + garden-sensors · shared the MQTT broker config between both projects · s:e03d6c58

$ agent-memory search "why don't we call the tide API when someone opens a chart" 3
tidepool · state · Tide charts render from local harmonic math (no NOAA calls at view time); ...  [projects/tidepool/NOW.md:6]
tidepool · frontmatter · name: no-noaa-at-view-time description: tide charts must not call the NOAA API while a user waits ...
```

The search line fuses keyword (BM25) and vector hits in one SurrealDB query. The old memory that `no-noaa-at-view-time` **supersedes** is left out of the results; archived files are too.

Also there: `fn::overdue()` (past their `review by` date), `fn::stale_nows(14)` (NOW.md files nobody touched in two weeks), `fn::conflicts()` (memories marked as contradicting each other), `fn::history('<memory>')`, `fn::entries('<project>', 'decided_against')` and `fn::logs('<project>')`. SurrealDB Studio can browse all of it as a graph.

## Quickstart

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and Docker (or your own SurrealDB 3.3.4). [Ollama](https://ollama.com) is optional; without it, search is keyword only.

```bash
git clone https://github.com/duplonicus/agent-memory && cd agent-memory
./install.sh          # asks before every change outside the repo; --yes to accept all
agent-memory demo     # invented demo projects in their own database: the brief, the queries, a search
```

On Windows, run `.\install.ps1` in PowerShell. Or point your agent at [INSTALL_FOR_AGENTS.md](INSTALL_FOR_AGENTS.md) and let it do the install with you.

The installer writes `~/.config/agent-memory/config.toml` and an `.env` with random passwords, starts SurrealDB in Docker (loopback only), applies the schema, offers to download the embedding model (about 620 MB), and adds the SessionStart hook, the `/sum` and `/search` skills and a short conventions section to `~/.claude`. Existing `settings.json` and `CLAUDE.md` are backed up, then added to. Nothing is overwritten.

## Start the agent in the project folder

```bash
cd ~/dev/tidepool && claude
```

The brief, the project's NOW.md and Claude Code's own project memory are all picked by **the folder the agent was started in**. A `cd` inside a running session changes none of them.

- **Symlinks are fine.** A path through a symlink resolves to the real folder.
- **The same folder by two real paths is two projects to Claude Code.** On WSL, `/home/you/dev/x` and `/mnt/c/Users/you/dev/x` (or `C:\Users\you\dev\x` from a Windows launch) each get their own memory folder.
- **On WSL's `/mnt/c`, case matters to Claude Code but not to the disk.** `cd /mnt/c/users/...` and `/mnt/c/Users/...` both work, and Claude Code treats them as two paths. One way that shows up: the global CLAUDE.md is loaded twice. Pick one spelling, or add the other to `claudeMdExcludes`.

## How it works

1. **You and your agent write markdown.** One `NOW.md` per project (current state, six sections), one shared `LOG.md` (one line per session), Claude Code's memory files, your `CLAUDE.md`. These files are the memory, and they stay readable and editable by hand.
2. **The sync daemon copies them into SurrealDB every 20 seconds, one way.** Every block (bullet, paragraph, heading) becomes a row with its exact bytes, so each file can be rebuilt byte for byte. An edited file only touches the blocks that changed; a removed block is marked superseded, not deleted.
3. **Graph edges tie it together.** Entries and LOG lines point at their project, LOG lines at the session that wrote them, memories at the memories they supersede or contradict.
4. **Ollama embeds each block** (embeddinggemma, 768 dimensions) into an HNSW index in the same database.
5. **The SessionStart hook reads the files, not the database.** A session starts with its brief even when SurrealDB is down.

A moved or renamed project folder keeps its ids, vectors and edges: a new file whose bytes match exactly one file that vanished in the same pass is treated as the same file. A sync that would retire more than 10 files at once (or more than a fifth of them, when that is more) is refused, so an unmounted drive cannot wipe the mirror.

## The conventions

The templates are the product as much as the code: [templates/NOW.md](templates/NOW.md), [templates/LOG.md](templates/LOG.md), [templates/memory.md](templates/memory.md) and the [CLAUDE.md section](templates/CLAUDE.md) that teaches the agent to use them. The short version:

- **Write it down when it happens.** A decision, especially a decision **not** to do something; an open thread and who it waits on; anything claimed but not verified.
- **NOW.md is state, LOG.md is history.** Overwrite NOW.md; append to LOG.md.
- **Every LOG line ends with `s:<first 8 characters of the session id>`.** It ties the line to the transcript that wrote it.
- **`(review by YYYY-MM-DD)`** on an open thread, or `review_by:` in a memory's frontmatter, makes it come back by itself.
- **`supersedes:` and `contradicts:`** in a memory's frontmatter link it to the memory it replaces or conflicts with.

## Platforms

| | Status |
|---|---|
| Linux, WSL2 | Tested: test suite, installer, and the hook in a real Claude Code session. Not yet run: the systemd user service the installer writes |
| Windows (native) | Tested: test suite, installer and hook with Windows Python. Not yet tested: the Task Scheduler sync task, and Claude Code on Windows running the hook |
| macOS | Not tested. No service yet: run `agent-memory daemon` yourself |

On Windows, Claude Code runs hooks in Git Bash, or in PowerShell when Git Bash is missing. The installer pins the hook to PowerShell so it behaves the same either way.

## SurrealDB version

Pinned to **3.3.4**, the version this is tested on. One planner bug in that version: an indexed field (`kind`, `status`, `project`) and a graph condition (`->about->...`) in one `WHERE` can silently return too few rows. The `fn::` reads go through the graph edge first to avoid it, and the daemon checks for it on every full pass. Write your own queries the same way.

## Compared with other tools

See [docs/COMPARISON.md](docs/COMPARISON.md), including where the alternatives are ahead.

## License

MIT
