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

## Optional: the vector map

A 3-d map of every note, like the picture at the top of the README: one self-contained HTML page with rotate, zoom, word search, and "click a dot for its 5 nearest notes". Offer it once the sync daemon has embedded their notes (`agent-memory status` shows no embed error).

1. Install the extra packages (UMAP, NumPy, SciPy, scikit-learn and Numba: about 420 MB on disk): `uv sync --extra map`.
2. Ask which projects hold anything private. The page carries up to 280 characters of every note, so hide those: `uv run --extra map python examples/vector-map/build.py ~/memory-map.html --hide <project> --hide <project>`. A hidden project keeps its dots; its text is replaced.
3. Open the file in a browser. It loads Plotly from a CDN, so it needs a network connection the first time.
4. If you can publish pages for them (a Claude artifact, for example), say the page is private by default and confirm before sharing it with anyone: it contains their notes.

On the demo data: `AGENT_MEMORY_DB=demo uv run --extra map python examples/vector-map/build.py demo-map.html` after `agent-memory demo`.
