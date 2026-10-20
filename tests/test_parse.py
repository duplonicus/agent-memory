"""Lossless segmentation: every fixture renders back byte for byte, and the blocks have the
shape a reader expects (heading path, item depth, frontmatter keys)."""
import pytest

from agent_memory.parse import split_blocks, render_blocks, sections, parse_frontmatter

FIXTURES = {
    "plain": "# Title\n\nA paragraph\nover two lines.\n\n- item one\n- item two\n  continued\n  - nested\n\n## Second\n\nText.\n",
    "crlf": "---\r\nname: x\r\ndescription: \"a b\"\r\nmetadata:\r\n  type: feedback\r\n---\r\n\r\nBody line.\r\n- bullet\r\n",
    "no_trailing_newline": "# H\n- a\n- b",
    "leading_blanks": "\n\n# H\ntext\n",
    "code_fence": "# H\n\n```bash\n- not a bullet\n# not a heading\n```\n\n- real bullet\n\n~~~\nunterminated fence\n",
    "table": "| a | b |\n|---|---|\n| 1 | 2 |\n\nafter\n",
    "numbered": "1. one\n2. two\n   more\n10) ten\n",
    "tabs_and_spaces": "- a\n\t- tab child\n    - four-space child\n- b   \n",
    "headings_skip_level": "# One\n### Three\ntext\n## Two\n- x\n",
    "frontmatter_only": "---\nname: y\n---\n",
    "frontmatter_unterminated": "---\nname: y\nbody\n",
    "hr_and_comments": "<!-- generated -->\n---\ntext\n***\n",
    "trailing_spaces": "- a  \n\n\n- b\t\n",
    "unicode": "- décision · s:abc12345 — «quoted»\n- 🚀 emoji\n",
    "empty": "",
    "only_blank": "\n\n",
}


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_roundtrip(name):
    text = FIXTURES[name]
    assert render_blocks(split_blocks(text)) == text


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_idempotent(name):
    text = FIXTURES[name]
    once = split_blocks(text)
    again = split_blocks(render_blocks(once))
    assert [(b.block, b.raw, b.text, b.section) for b in once] == [(b.block, b.raw, b.text, b.section) for b in again]


def test_shapes_plain():
    b = split_blocks(FIXTURES["plain"])
    kinds = [x.block for x in b]
    assert kinds == ["heading", "para", "item", "item", "item", "heading", "para"]
    assert b[0].level == 1 and b[0].text == "Title"
    assert b[1].text == "A paragraph\nover two lines."
    assert b[3].text == "item two\ncontinued" and b[3].depth == 0
    assert b[4].text == "nested" and b[4].depth == 1
    assert b[5].section == ["Title", "Second"] and b[6].section == ["Title", "Second"]
    assert b[1].raw.endswith("\n\n")  # the blank line rides on the block before it


def test_frontmatter_crlf():
    b = split_blocks(FIXTURES["crlf"])
    assert b[0].block == "frontmatter"
    assert b[0].fields == {"name": "x", "description": "a b", "metadata.type": "feedback"}
    assert [x.block for x in b[1:]] == ["para", "item"]
    assert b[2].text == "bullet"
    assert "\r" not in b[1].text and "\r" in b[1].raw


def test_code_fence_hides_markup():
    b = split_blocks(FIXTURES["code_fence"])
    assert [x.block for x in b] == ["heading", "code", "item", "code"]
    assert b[1].text == "- not a bullet\n# not a heading"
    assert b[3].raw == "~~~\nunterminated fence\n"


def test_table_and_numbered():
    assert [x.block for x in split_blocks(FIXTURES["table"])] == ["table", "para"]
    b = split_blocks(FIXTURES["numbered"])
    assert [x.block for x in b] == ["item"] * 3
    assert b[1].text == "two\nmore" and b[2].text == "ten"


def test_depth_with_tabs():
    b = split_blocks(FIXTURES["tabs_and_spaces"])
    assert [x.depth for x in b] == [0, 1, 1, 0]
    assert b[3].text == "b"


def test_skipped_heading_level_keeps_path_positions():
    b = split_blocks(FIXTURES["headings_skip_level"])
    assert b[1].section == ["One", "", "Three"]
    assert b[2].section == ["One", "", "Three"]
    assert b[3].section == ["One", "Two"]


def test_unterminated_frontmatter_is_not_frontmatter():
    b = split_blocks(FIXTURES["frontmatter_unterminated"])
    assert b[0].block == "para"


def test_leading_blank_block():
    b = split_blocks(FIXTURES["leading_blanks"])
    assert b[0].block == "blank" and b[0].raw == "\n\n"


def test_sections_grouping():
    g = sections(split_blocks("intro\n\n# A\n- x\n## B\n- y\n# C\n"))
    assert [len(x) for x in g] == [1, 2, 2, 1]
    assert g[0][0].block == "para" and g[1][0].text == "A"


def test_parse_frontmatter_tolerates_junk():
    assert parse_frontmatter(["---\n", "name: a\n", "junk line\n", "metadata:\n", "  type: user\n", "  modified: 2026-09-29T01:27:19.281Z\n", "---\n"]) == \
        {"name": "a", "metadata.type": "user", "metadata.modified": "2026-09-29T01:27:19.281Z"}


def test_a_byte_order_mark_does_not_hide_the_frontmatter():
    """Windows PowerShell 5.1's `Set-Content -Encoding UTF8` and older Notepad start the file with a BOM."""
    text = "﻿---\nname: x\ntype: feedback\nsupersedes: old-one\n---\n\n# Title\n- item\n"
    b = split_blocks(text)
    assert b[0].block == "frontmatter" and b[0].fields == {"name": "x", "type": "feedback", "supersedes": "old-one"}
    assert render_blocks(b) == text  # the BOM stays in raw, so the file still renders back byte for byte
    h = split_blocks("﻿# Title\ntext\n")
    assert h[0].block == "heading" and h[0].text == "Title"
