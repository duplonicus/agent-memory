# Benchmarks

Every number here carries its date, setup and sample size. A number not in this file is not one we publish.

## Search latency, 2026-10-18

**What it measures:** the time for one search, split into its steps, on a real memory corpus.
- **embed**: Ollama turns the question into a vector.
- **hybrid**: one `fn::search` call in SurrealDB that runs BM25 keyword search and an HNSW vector search and fuses them (reciprocal rank fusion), with the question vector passed in.
- **keyword**: the same call without a vector.
- **embed + hybrid**: the two together, which is what a search costs when the process is already running.

**What it does not measure:** search quality (hit rates), a CPU-only Ollama, Ollama inside WSL instead of on Windows, corpora much larger than 5,000 entries, or Python start-up for a one-shot command (below, separately).

| Step | p50 | p95 | n |
|---|---|---|---|
| embed (embeddinggemma, GPU) | 23.6 ms | 32.8 ms | 110 |
| hybrid `fn::search` | 14.6 ms | 20.5 ms | 110 |
| keyword `fn::search` | 5.4 ms | 12.1 ms | 110 |
| **embed + hybrid** | **38.8 ms** | **50.4 ms** | 110 |

- **Corpus:** the author's own memory, 5,190 active entries and 5,080 vectors (archived files get no vector). Private, so this run can't be repeated by others; the demo run below can.
- **Questions:** 22 real questions from the author's search eval, 5 passes each after one warm-up pass, 10 results per search.
- **Machine:** AMD Ryzen 7 5800X (WSL2 given 12 threads), NVIDIA RTX 3090, Windows 11 with WSL2 (kernel 6.18). The client and the sync daemon ran in WSL2; SurrealDB 3.3.4 in Docker Desktop; Ollama on native Windows, reached over WSL mirrored networking.
- **When:** 2026-10-18 10:18 PM ET (2026-10-19 02:18 UTC). Other programs had the GPU at 10% use and 3.1 GB of memory just before the run.
- **Code:** the author's private mirror, whose `fn::search` is this repo's minus one filter (this repo also drops superseded memories), with the same embedding model and prompt format; timed by `bench()` from [scripts/bench_search.py](../scripts/bench_search.py).

**One-shot command:** the author's `search` command (same code path) took 0.27 to 0.29 s from process start to output over 10 runs. Most of that is start-up: importing the SurrealDB Python SDK alone took 137 ms.

### Demo corpus (reproducible)

The same script on the invented demo (`agent-memory demo`, 75 entries), 3 questions × 3 passes, same machine and time: embed 13.4 ms p50, hybrid 9.8 ms, keyword 3.9 ms, embed + hybrid 23.1 ms (n = 9 each). Too small to say much beyond "it runs"; repeat it with:

```bash
agent-memory demo
printf 'why no NOAA calls at view time\nwho is the palette waiting on\nprobe battery life\n' > q.txt
AGENT_MEMORY_DB=demo .venv/bin/python scripts/bench_search.py q.txt --reps 3
```

## Ollama on Windows vs inside WSL, 2026-10-18

**Question:** on a WSL2 machine, is embedding faster with the Windows Ollama app or with Ollama running inside WSL (through WSL's CUDA support)?

**Answer: no meaningful difference.**

| | Windows app | Inside WSL |
|---|---|---|
| One question, p50 | 17.7 ms | 16.4 ms |
| One question, p95 | 29.7 ms | 33.5 ms |
| Batch of 32 entries (what the sync daemon sends), p50 | 419.5 ms | 432.3 ms |
| Batch of 32 entries, p95 | 470.4 ms | 484.0 ms |

- **Same model, same results:** the same embeddinggemma files (digest 85462619ee72) on both, and the two gave identical vectors for a test query (cosine 1.000000). Both ran Ollama 0.40.4 on the GPU; the WSL server's log shows it loaded the CUDA backend on the RTX 3090.
- **Method:** 22 questions × 5 passes (n = 110 per side) and 20 batches of 32 real entries (n = 20 per side), after a warm-up on each. The two servers were called alternately, and the order flipped every pass, so neither got a quieter GPU.
- **Machine and time:** as above (Ryzen 7 5800X, RTX 3090, Windows 11 + WSL2 with mirrored networking), 2026-10-18 around 11:05 PM ET. The client ran in WSL, so the Windows app was reached across the WSL network boundary and the WSL one was not.
- **Memory:** `ollama ps` showed the loaded model at 685,642,874 bytes, all of it in VRAM (`size_vram` equal to `size`), on both servers. A batch of 32 entries at 420 ms is about 13 ms per entry.
- **Not measured:** CPU-only Ollama, an AMD GPU, or default NAT networking.
