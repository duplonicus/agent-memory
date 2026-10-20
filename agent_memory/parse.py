"""Deterministic, lossless markdown segmentation.

split_blocks(text) cuts a file into ordered blocks whose `raw` fields concatenate back to the
exact input (render_blocks). No model, no normalisation of the bytes: CRLF, trailing spaces and
odd indentation all stay inside `raw`. `text` is a cleaned copy for search and reading.

Block shapes: frontmatter (a leading --- block), heading, item (one list bullet, with its
indented continuation lines), para, code (a fenced block), table, blank (only when a file starts
with blank lines; otherwise blank lines ride on the block before them).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
ITEM = re.compile(r"^([ \t]*)([-*+]|\d{1,3}[.)])[ \t]+")
FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
TABLE = re.compile(r"^[ \t]*\|")


@dataclass
class Block:
    line: int                 # 1-based first line
    block: str                # heading | frontmatter | item | para | code | table | blank
    raw: str                  # exact bytes (with line endings and trailing blank lines)
    text: str                 # cleaned
    section: list[str] = field(default_factory=list)   # heading path at this point
    level: int | None = None  # heading level
    depth: int | None = None  # list nesting depth
    fields: dict = field(default_factory=dict)  # frontmatter keys


def _strip(line: str) -> str:
    return line.rstrip("\r\n")


def _blank(line: str) -> bool:
    return _strip(line).strip() == ""


def _clean(lines: list[str]) -> str:
    return "\n".join(_strip(l).strip() for l in lines).strip()


def _indent(line: str) -> int:
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 4
        else:
            break
    return n


def parse_frontmatter(lines: list[str]) -> dict:
    """The keys a memory file's frontmatter carries (name, description, type, metadata.*).
    Tolerant: a flat `key: value` scan, nested keys prefixed by their parent. Never fails."""
    out: dict = {}
    parent = None
    for l in lines[1:-1]:
        s = _strip(l)
        m = re.match(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$", s)
        if not m:
            continue
        ind, key, val = m.groups()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if ind:
            if parent:
                out[f"{parent}.{key}"] = val
        else:
            parent = key if val == "" else None
            if val != "":
                out[key] = val
    return out


def split_blocks(content: str) -> list[Block]:
    # A UTF-8 byte order mark (PowerShell 5.1, older Notepad) would hide the frontmatter or first heading.
    # Parse without it and put it back on the first block's raw, so rendering stays byte for byte.
    if content.startswith("\ufeff"):
        blocks = split_blocks(content[1:])
        if blocks:
            blocks[0].raw = "\ufeff" + blocks[0].raw
        else:
            blocks = [Block(1, "blank", "\ufeff", "", [])]
        return blocks
    lines = content.splitlines(keepends=True)
    blocks: list[Block] = []
    section: list[str] = []
    item_stack: list[int] = []   # indents of open list items, for depth
    i, n = 0, len(lines)

    def push(b: Block):
        blocks.append(b)

    # frontmatter
    if n and _strip(lines[0]) == "---":
        j = 1
        while j < n and _strip(lines[j]) != "---":
            j += 1
        if j < n:
            chunk = lines[: j + 1]
            push(Block(1, "frontmatter", "".join(chunk), _clean(chunk[1:-1]), [], fields=parse_frontmatter(chunk)))
            i = j + 1

    while i < n:
        line = lines[i]
        if _blank(line):
            if blocks:
                blocks[-1].raw += line
            else:
                push(Block(i + 1, "blank", line, "", list(section)))
            i += 1
            continue
        s = _strip(line)
        m = FENCE.match(s)
        if m:
            fence = m.group(1)[0]
            j = i + 1
            while j < n:
                t = _strip(lines[j])
                mm = FENCE.match(t)
                if mm and mm.group(1)[0] == fence and len(mm.group(1)) >= len(m.group(1)) and t.strip() == mm.group(1):
                    break
                j += 1
            end = min(j + 1, n)
            chunk = lines[i:end]
            push(Block(i + 1, "code", "".join(chunk), "\n".join(_strip(l) for l in chunk[1:-1] if True).strip("\n") if len(chunk) > 2 else "", list(section)))
            item_stack = []
            i = end
            continue
        m = HEADING.match(s)
        if m:
            level, title = len(m.group(1)), m.group(2)
            del section[level - 1:]
            while len(section) < level - 1:
                section.append("")
            section.append(title)
            push(Block(i + 1, "heading", line, title, list(section), level=level))
            item_stack = []
            i += 1
            continue
        if TABLE.match(s):
            j = i
            while j < n and not _blank(lines[j]) and TABLE.match(_strip(lines[j])):
                j += 1
            chunk = lines[i:j]
            push(Block(i + 1, "table", "".join(chunk), _clean(chunk), list(section)))
            item_stack = []
            i = j
            continue
        m = ITEM.match(s)
        if m:
            ind = _indent(s)
            while item_stack and item_stack[-1] >= ind:
                item_stack.pop()
            depth = len(item_stack)
            item_stack.append(ind)
            j = i + 1
            while j < n:
                t = _strip(lines[j])
                if _blank(lines[j]) or HEADING.match(t) or FENCE.match(t) or TABLE.match(t) or ITEM.match(t):
                    break
                if _indent(t) <= ind:
                    break
                j += 1
            chunk = lines[i:j]
            first = s[m.end():]
            push(Block(i + 1, "item", "".join(chunk), _clean([first] + chunk[1:]), list(section), depth=depth))
            i = j
            continue
        # paragraph
        j = i + 1
        while j < n:
            t = _strip(lines[j])
            if _blank(lines[j]) or HEADING.match(t) or FENCE.match(t) or TABLE.match(t) or ITEM.match(t):
                break
            j += 1
        chunk = lines[i:j]
        push(Block(i + 1, "para", "".join(chunk), _clean(chunk), list(section)))
        item_stack = []
        i = j
    return blocks


def render_blocks(blocks: list[Block]) -> str:
    return "".join(b.raw for b in blocks)


def sections(blocks: list[Block]) -> list[list[Block]]:
    """Group blocks into heading-led sections: each heading starts a new group; blocks before the
    first heading form a leading group. Used for docs (one entry per section)."""
    groups: list[list[Block]] = []
    for b in blocks:
        if b.block == "heading" or not groups:
            groups.append([b])
        else:
            groups[-1].append(b)
    return groups
