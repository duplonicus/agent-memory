# Installing agent-memory (for an AI agent)

You are helping a person install agent-memory. Work through these steps with them. **Ask before every step that changes something outside this repository**, and show them what changed afterwards.

1. **Check the prerequisites.** Run `scripts/install-deps.sh --dry-run` (Windows: `scripts\install-deps.ps1 -DryRun`). It lists uv, Python 3.12, Docker, the SurrealDB image and Ollama as ok or missing, and the exact commands it would run. Show the person the list and ask which to install.

   Then run `scripts/install-deps.sh --yes` yourself. You have no terminal to type a sudo password into, so the script does everything it can and prints the steps that need one under "These need your password". Give those to the person to run (in Claude Code they type `!` before the command), then run `--check` to confirm. On Windows, winget installs may pop up an admin (UAC) prompt for the person to accept.
2. **Ask where their projects live** (default `~/dev`) and where the cross-project notes should go (default `~/agent-notes`).
3. **Run the installer** from the repository root: `./install.sh --yes --projects <dirs> --notes <dir>` (Windows: `.\install.ps1 --yes ...`). It would normally ask before each change, but you can't answer its prompts, so explain what it does first (the list is in the README's Quickstart) and use `--yes` only after the person agrees to all of it.
4. **Read back what it did.** Show the new SessionStart entry in `~/.claude/settings.json`, the appended section at the end of `~/.claude/CLAUDE.md`, and the output of `agent-memory status`.
5. **Run `agent-memory demo`** and show them the brief and one query. The demo uses invented data in a separate database.
6. **Their first project.** In one of their project folders, copy `templates/NOW.md` to `NOW.md`, add `/NOW.md` and `/state/` to `.git/info/exclude` (NOW files hold private state and should not be committed), and fill it in yourself from what you can see in the project (its README, git log, open TODOs). Ask the person only what you can't find. From then on, keeping it current is your job, not theirs.
7. **Tell them to start the agent from the project folder** (`cd ~/dev/<project> && claude`), and why: the brief and the memory are chosen by the folder the agent was started in.

If the installer stops with "Still to do" items, work through those, then run it again; every step is skipped once it is done.
