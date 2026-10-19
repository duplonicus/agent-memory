---
name: search
description: Search your agent memory (NOW files, LOG, CLAUDE.md, rules, memory files, project notes) by meaning and keyword, and answer from the hits.
argument-hint: "[question]"
disable-model-invocation: true
allowed-tools: Bash(agent-memory search *)
---

## Hits for: $ARGUMENTS

!`agent-memory search "$ARGUMENTS" 10 2>&1`

The user does not see the output above, so open the reply with every hit as a numbered list, one line each, top hit first: `project · kind · the first ~100 characters`. Then answer the question from these hits in a few lines: lead with the answer, name the project and file it came from, and quote the entry where the wording matters.

If the hits don't answer it, say so plainly and name the nearest one; don't fill the gap from your own memory. If the output starts with "keyword only", say Ollama was down, so the results are keyword only. Open a source file only when a hit is cut off and the rest is needed.
