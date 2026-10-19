# agent-memory

**Agent memory as plain files, mirrored into [SurrealDB](https://surrealdb.com): graph links, full-text and vector search in one database, across every project.** Embeddings run locally through [Ollama](https://ollama.com), on your GPU when you have one.

Your coding agent forgets everything between sessions. The usual fix is a notes file per project, and it works until you have twenty of them. Then you can no longer answer simple questions:

- **What is waiting on whom?** Every open thread in every project, with the person or thing it waits on.
- **What did we claim but never check?** "Tests pass", "works on Windows", written down and never verified.
- **Which sessions did work and logged nothing?** Every LOG line carries its session id, so the gap shows up at the next session start.

agent-memory keeps the notes as markdown you can read and edit by hand. A small daemon mirrors them into SurrealDB, so one query answers those questions across all your projects. Built for Claude Code. The conventions work with any agent that reads files, and the hook and skills could be adapted to agents with the same building blocks, such as Codex, which has SessionStart hooks and SKILL.md skills.

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

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/), [Docker](https://docs.docker.com/get-started/get-docker/) for [SurrealDB](https://surrealdb.com) 3.3.4 (or your own SurrealDB), and optionally [Ollama](https://ollama.com); without Ollama, search is keyword only. **The installer checks for all of them first** and, if any are missing, asks whether to install them: you get a checklist of what's missing, untick what you'd rather install yourself, and it runs each vendor's own installer, showing every command first. On WSL it installs Ollama as the Windows app (recommended for speed) through winget. To see the list without changing anything: `scripts/install-deps.sh --dry-run`.

```bash
git clone https://github.com/duplonicus/agent-memory && cd agent-memory
./install.sh          # checks dependencies, then asks before every change outside the repo; --yes to accept all
agent-memory demo     # invented demo projects in their own database: the brief, the queries, a search
```

On Windows, run `.\install.ps1` in PowerShell (its dependency step uses winget: uv, Docker Desktop, Ollama). Or point your agent at [INSTALL_FOR_AGENTS.md](INSTALL_FOR_AGENTS.md) and let it do the install with you.

The installer writes `~/.config/agent-memory/config.toml` and an `.env` with random passwords, starts SurrealDB in [Docker](https://www.docker.com) (loopback only), applies the schema, offers to download the embedding model (about 620 MB), and adds the SessionStart hook, the `/sum` and `/search` skills and a short conventions section to `~/.claude`. Existing `settings.json` and `CLAUDE.md` are backed up, then added to. Nothing is overwritten.

## Start the agent in the project folder

```bash
cd ~/dev/tidepool && claude
```

The brief, the project's NOW.md and Claude Code's own project memory are all picked by **the folder the agent was started in**. A `cd` inside a running session changes none of them.

- **Symlinks are fine.** A path through a symlink resolves to the real folder.
- **The same folder by two real paths is two projects to Claude Code.** On WSL, `/home/you/dev/x` and `/mnt/c/Users/you/dev/x` (or `C:\Users\you\dev\x` from a Windows launch) each get their own memory folder.
- **On WSL's `/mnt/c`, case matters to Claude Code but not to the disk.** `cd /mnt/c/users/...` and `/mnt/c/Users/...` both work, and Claude Code treats them as two paths. One way that shows up: the global CLAUDE.md is loaded twice. Pick one spelling, or add the other to `claudeMdExcludes`.

## Where things run

Four pieces: the **agent** (Claude Code and its hook), **your files**, **SurrealDB** with the **sync daemon**, and **Ollama** for embeddings. Each talks to the others over `127.0.0.1`, so they normally all live on one machine.

### Linux

Everything runs natively. SurrealDB is a Docker container on `127.0.0.1:8000`, the sync daemon is a systemd user service (`agent-memory-sync.service`), Ollama is on its default port 11434, and Claude Code runs in your shell. The defaults need no changes.

### WSL2 (Linux on Windows)

Run Claude Code, your project folders and agent-memory **inside WSL**, as on Linux. Keep the projects on the Linux disk (`~/dev`), not under `/mnt/c`: it is faster, and file paths are case-sensitive the way Claude Code expects (see the path notes above). The installer is `./install.sh`, and the sync daemon is a systemd user service, which needs systemd enabled in WSL.

- **SurrealDB:** Docker Desktop for Windows with WSL integration turned on, or Docker Engine installed inside WSL. Both serve `127.0.0.1:8000` to WSL.
- **Ollama as the Windows app (recommended for speed), with everything else in WSL.** This is what the dependency installer sets up. It runs on the GPU natively, without going through WSL. WSL can only reach it at `127.0.0.1` with [mirrored networking](https://learn.microsoft.com/en-us/windows/wsl/networking#mirrored-mode-networking) (`networkingMode=mirrored` under `[wsl2]` in `%UserProfile%\.wslconfig`, Windows 11 22H2 or later). On the default NAT networking, WSL has to use the Windows host's IP address instead, and Ollama has to listen beyond `127.0.0.1` (`OLLAMA_HOST=0.0.0.0`), which opens it to your network. If Ollama answers anywhere but `127.0.0.1:11434`, set `[embed] url` in the config to that address.
- **Or Ollama inside WSL too**, which needs no networking change. NVIDIA GPUs work in WSL 2 through the normal Windows driver ([NVIDIA's guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html); don't install a Linux GPU driver inside WSL).

### Windows (native, no WSL)

Run `.\install.ps1` in PowerShell. Everything runs as Windows programs: agent-memory under Windows Python (uv installs it), SurrealDB in Docker Desktop, Ollama as the Windows app on port 11434, and the sync daemon as a Task Scheduler task that starts at logon. Claude Code runs hooks in Git Bash when it is installed and in PowerShell otherwise; the installer pins this hook to PowerShell so it behaves the same either way.

### What has been tested

| | Tested | Not yet tested |
|---|---|---|
| Linux, WSL2 | Test suite, installer, and the hook in a real Claude Code session | The systemd service the installer writes |
| Windows (native) | Test suite, installer and the hook with Windows Python | The Task Scheduler task; Claude Code for Windows running the hook |
| macOS | Nothing yet | No service either: run `agent-memory daemon` yourself |

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

## SurrealDB version

Pinned to **3.3.4**, the version this is tested on. One planner bug in that version: an indexed field (`kind`, `status`, `project`) and a graph condition (`->about->...`) in one `WHERE` can silently return too few rows. The `fn::` reads go through the graph edge first to avoid it, and the daemon checks for it on every full pass. Write your own queries the same way.

## Compared with other tools

See [docs/COMPARISON.md](docs/COMPARISON.md), including where the alternatives are ahead.

## License

MIT
