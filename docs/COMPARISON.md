# agent-memory compared

The closest project is [ai-memory](https://github.com/akitaonrails/ai-memory) (Fabio Akita, MIT, Rust). Facts below come from its repository at v3.1.1, read on 2026-10-18; file references are to that version.

## Where ai-memory is ahead

- **It captures automatically.** Lifecycle hooks record prompts, tool calls and session boundaries (README.md:67), so nothing depends on the agent remembering to write. agent-memory records only what the agent writes down.
- **It supports many harnesses.** Its README says "more than twenty" (README.md:29), and its matrix names 31, at different support levels. agent-memory is built for Claude Code; other agents get only the file conventions.
- **One binary, embeddings built in.** It ships as one self-contained binary (README.md:94) with a local MiniLM model running in-process: no Docker, no Ollama.
- **Platforms.** Linux and macOS are supported, native Windows is experimental (README.md:130-134). agent-memory is tested on Linux, WSL2 and native Windows, not on macOS.
- **Teams.** It has multi-user auth and per-project sharing (README.md:56-59). agent-memory is single-user.
- **Handoffs between agents** have owners and are offered to the next session.
- **Memory aging**: decay, dedup and contradiction flagging (README.md:74), and typed edges with lint (docs/typed-edges.md).
- **Published benchmarks** with commit, dataset hash and hardware: LongMemEval-S retrieval hit@5 0.951 with full-text search (12 ms p50) and 0.940 with local embeddings (99 ms p50), on a Ryzen 9 7950X3D (docs/benchmarks/longmemeval-s-3.1.0-release.md). These are retrieval hit rates on raw chat transcripts, not answer accuracy. agent-memory has published no numbers yet.

## Where agent-memory is different

These are fields and checks we could not find in ai-memory's repository (searched 2026-10-18):

- **Waiting on whom.** Every NOW.md has an "Open threads (waiting on whom)" section, and `fn::waiting_on()` lists them across projects.
- **Unverified claims.** Anything written as "not verified" is listed by `fn::unverified()`.
- **Session audit.** Every LOG line carries its session id, so `fn::session()` shows everything one session logged, and the session-start brief lists sessions that edited files but never logged.
- **Stale state.** The brief warns when a repo has commits newer than its NOW.md.
- **Review dates.** `(review by YYYY-MM-DD)` brings an item back when it is due. ai-memory has `expires_at`, which deletes a page when it expires; a review date asks for a look instead.
- **Plain files stay the source of truth**, laid out for a person to read: one NOW.md per project, one LOG line per session. ai-memory also keeps markdown in git as its source of truth, with a SQLite index.
- **One database for graph, full-text and vectors.** SurrealDB holds the rows, the BM25 index, the HNSW vectors and the graph edges, so a hybrid search or a graph walk is one query, and Studio can browse it.
- **GPU embeddings through Ollama** when there is a GPU (CUDA, ROCm, Metal or Vulkan), CPU otherwise.

Both projects record decisions with what was rejected. In ai-memory it is a convention its decision template asks for ("Rejected alternatives and WHY"); in agent-memory it is the "Decisions (incl. things decided against)" section of every NOW.md. Both also have `supersedes` and `contradicts` between memories.

## Pick ai-memory if

You want capture without discipline, several different agents sharing one memory, a team, or a single binary with nothing else to run.

## Pick agent-memory if

You use Claude Code, you want your agent's memory in plain files you can read, and the questions you keep asking are "what is waiting on whom", "what did we never check" and "what did that session do".
