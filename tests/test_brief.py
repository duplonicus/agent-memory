"""The clipped NOW.md brief: under budget, every section kept, every cut marked with what it left out."""
import re

from agent_memory import brief as now_brief

CAP = 6000
CHARS = re.compile(r" \[\+(\d+) chars\]$")
ITEMS = re.compile(r"^\[\+(\d+) more items in (.+)\]$")

# Invented project, long enough that it must be clipped.
DEMO = """# Lighthouse app — NOW

Updated: 2026-01-02 by Claude Code · s:00000000

## State
- Beacon sync is live on main; """ + "the retry queue drains every 30 s and keeps a backlog file. " * 12 + """
- Tests green at abc1234.

## Next
1. Ship the map view. """ + "It needs the tile cache first, then the legend. " * 20 + """
   - sub-point that belongs to item 1
2. Short item.

## Decisions (incl. things decided against)
""" + "".join(f"- 2026-01-0{i % 9 + 1}, Ana: decision number {i}. " + "Because of reasons. " * 10 + "\n" for i in range(15)) + """
## Open threads (waiting on whom)
- Waiting on Ana: the logo. (review by 2026-03-01)
- Waiting on Ben: hosting quote. (review by 2026-02-01)
- Waiting on Cy: nothing dated.
- Waiting on Di: next year. (Review by 2027-01-01)

## Gotchas
"""


def check(files, out, today="2026-10-18"):
    """Every header is printed, and every cut is marked with exactly what it left out."""
    blocks = out.split("\n\n")
    assert len(blocks) == len(files)
    for (path, text), block in zip(files, blocks):
        head, sections = now_brief.parse(text)
        lines = block.split("\n")
        assert lines[0].startswith(f"=== {path} ")
        headers = [h for h, _ in sections]
        assert [l for l in lines if l.startswith("## ")] == headers
        for header, items in sections:
            if now_brief.ACT_ON.search(header):
                items = now_brief.order(items, today)
            body = lines[lines.index(header) + 1 :]
            body = body[: next((i for i, l in enumerate(body) if l.startswith(("## ", "=== "))), len(body))]
            if not items:
                assert body == ["(empty)"]
                continue
            more = [l for l in body if ITEMS.match(l)]
            shown = [l for l in body if not ITEMS.match(l)]
            hidden = int(ITEMS.match(more[0]).group(1)) if more else 0
            assert len(shown) + hidden == len(items)
            for line, item in zip(shown, items):
                m = CHARS.search(line)
                if m:
                    kept = line[: m.start()]
                    assert item.startswith(kept)
                    assert len(item) - len(kept) == int(m.group(1))
                else:
                    assert line == item


def test_demo_is_clipped_marked_and_under_cap():
    files = [("/demo/NOW.md", DEMO)]
    out = now_brief.brief(files, 2500, today="2026-10-18")
    assert len(out.encode()) <= 2500
    assert "[+" in out
    check(files, out)


def test_overdue_threads_lead_oldest_first_and_nothing_is_lost():
    out = now_brief.brief([("/demo/NOW.md", DEMO)], 50000, today="2026-06-01")
    thr = out.split("## Open threads (waiting on whom)\n")[1].split("\n## ")[0].split("\n")
    assert thr == ["OVERDUE - Waiting on Ben: hosting quote. (review by 2026-02-01)",
                   "OVERDUE - Waiting on Ana: the logo. (review by 2026-03-01)",
                   "- Waiting on Cy: nothing dated.",
                   "- Waiting on Di: next year. (Review by 2027-01-01)"]
    check([("/demo/NOW.md", DEMO)], now_brief.brief([("/demo/NOW.md", DEMO)], 2500, today="2026-06-01"), "2026-06-01")


def test_sub_points_fold_into_their_item():
    _, sections = now_brief.parse(DEMO)
    nxt = dict(sections)["## Next"]
    assert len(nxt) == 2 and "sub-point" in nxt[0]


def test_small_file_is_printed_whole():
    text = "# T\n\n## State\n- one\n- two\n\n## Next\nnone\n"
    out = now_brief.brief([("/t/NOW.md", text)], CAP)
    assert "[+" not in out
    assert out.split("\n")[1:] == ["# T", "## State", "- one", "- two", "## Next", "none"]


def test_reference_sections_are_capped_before_actionable_ones():
    out = now_brief.brief([("/demo/NOW.md", DEMO)], 2500)
    assert re.search(r"^\[\+\d+ more items in /demo/NOW.md\]$", out, re.M)
    nxt = out.split("## Next\n")[1].split("\n## ")[0]
    assert "more items" not in nxt
