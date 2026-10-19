"""Clip NOW.md files into a session-start brief that fits a byte budget.

Claude Code caps a hook's output at 10,000 characters; over that, the session gets the
path to a file and a 2,000-character preview, and nothing asks it to read the file. A
session that starts on a big NOW.md starts blind. So every section is kept, but each item
is cut to its opening and marked with how much was left out. Nothing is cut silently: every
cut says how many characters or items are missing and where the full file is.
"""
import re
import sys
from datetime import date

# Item limits tried in turn, longest first; the first one that fits the budget wins.
# Sections a session acts on get the full limit; reference sections get half of it.
LIMITS = (500, 400, 320, 260, 220, 180, 150, 120, 90, 60)
ACT_ON = re.compile(r"next|open|state|to-?do|waiting", re.I)
ITEM = re.compile(r"^(\s*)([-*]|\d+\.)\s")
CLIP = " [+{} chars]"
REVIEW_BY = re.compile(r"\(review by (\d{4}-\d{2}-\d{2})\)", re.I)
OVERDUE = "OVERDUE "


def order(items, today):
    """Items whose "(review by YYYY-MM-DD)" has passed come first, oldest date first, marked
    OVERDUE; everything else keeps its order."""
    late = sorted((m.group(1), n) for n, i in enumerate(items)
                  if (m := REVIEW_BY.search(i)) and m.group(1) <= today)
    first = [n for _, n in late]
    return [OVERDUE + items[n] for n in first] + [i for n, i in enumerate(items) if n not in first]


def parse(text):
    """Split into (head lines, [(header, [items])]). An item is a top-level list entry with
    its continuation lines, or a plain paragraph line."""
    head, sections, cur = [], [], None
    for line in text.splitlines():
        if line.startswith("## "):
            cur = (line, [])
            sections.append(cur)
        elif cur is None:
            head.append(line)
        elif not line.strip():
            continue
        else:
            m = ITEM.match(line)
            if (m and not m.group(1)) or not cur[1] or (not m and not line.startswith(" ")):
                cur[1].append(line)
            else:
                cur[1][-1] += "\n" + line
    return head, sections


def clip(item, limit):
    """First line only, cut to `limit` chars at a sentence or word end, plus a marker."""
    if len(item) <= limit and "\n" not in item:
        return item
    first = item.split("\n", 1)[0]
    if len(first) > limit:
        cut = first[:limit]
        end = cut.rfind(". ")
        if end > limit * 3 // 4:
            cut = cut[: end + 1]
        elif " " in cut[limit // 2 :]:
            cut = cut[: cut.rfind(" ")]
        first = cut
    return first + CLIP.format(len(item) - len(first))


def render(path, head, sections, limit, ref_cap, max_items, today):
    out = [f"=== {path} (brief: items clipped, read the file for the rest) ==="]
    out += [h if h.startswith(("#", "Updated:")) else clip(h, limit) for h in head if h.strip()]
    for header, items in sections:
        out.append(header)
        if not items:
            out.append("(empty)")
        act = ACT_ON.search(header)
        items = order(items, today) if act else items
        cap = max_items if act else min(x for x in (ref_cap, max_items, len(items)) if x is not None)
        shown = items if cap is None else items[:cap]
        lim = limit if act else max(limit // 2, 60)
        out += [clip(i, lim) for i in shown]
        if len(items) > len(shown):
            out.append(f"[+{len(items) - len(shown)} more items in {path}]")
    return "\n".join(out)


def brief(files, budget, today=None):
    """files: [(path, text)]. Returns the brief, under budget whenever headers alone fit."""
    today = today or date.today().isoformat()
    parsed = [(p, *parse(t)) for p, t in files]
    # Prefer readable items: cap the reference sections (Decisions, Gotchas) before
    # shrinking items, and cap the sections a session acts on only as a last resort.
    tries = [(limit, ref_cap, None) for limit in LIMITS for ref_cap in (None, 6, 4, 2)]
    tries += [(LIMITS[-1], 0, m) for m in (6, 4, 3, 2, 1, 0)]
    for limit, ref_cap, max_items in tries:
        text = "\n\n".join(render(p, h, s, limit, ref_cap, max_items, today) for p, h, s in parsed)
        if len(text.encode()) <= budget:
            return text
    return text
