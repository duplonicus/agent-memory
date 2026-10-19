# Installing agent-memory (for an AI agent)

You are helping a person install agent-memory. Work through these steps with them. **Ask before every step that changes something outside this repository**, and show them what changed afterwards.

1. **Check the platform and prerequisites.** Run `python3 --version` (3.12 or newer), `uv --version`, `docker --version`, and `curl -s http://127.0.0.1:11434/api/version` (Ollama; optional). Report what is missing and link the install page; do not install system packages yourself without asking.
2. **Ask where their projects live** (default `~/dev`) and where the cross-project notes should go (default `~/agent-notes`).
3. **Run the installer** from the repository root: `./install.sh --projects <dirs> --notes <dir>` (Windows: `.\install.ps1 ...`). It asks before each change. Let the person answer, or pass `--yes` only after they have agreed to all of it.
4. **Read back what it did.** Show the new SessionStart entry in `~/.claude/settings.json`, the appended section at the end of `~/.claude/CLAUDE.md`, and the output of `agent-memory status`.
5. **Run `agent-memory demo`** and show them the brief and one query. The demo uses invented data in a separate database.
6. **Their first project.** In one of their project folders, copy `templates/NOW.md` to `NOW.md`, add `/NOW.md` and `/state/` to `.git/info/exclude` (NOW files hold private state and should not be committed), and fill it in with them.
7. **Tell them to start the agent from the project folder** (`cd ~/dev/<project> && claude`), and why: the brief and the memory are chosen by the folder the agent was started in.

If the installer stops with "Still to do" items, work through those, then run it again; every step is skipped once it is done.
