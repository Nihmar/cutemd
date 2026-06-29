"""Tests for core/frontmatter.py"""

from core.frontmatter import parse_frontmatter, strip_frontmatter


def test_parse_tags_list():
    text = "---\ntags: [a, b, c]\n---\nbody"
    fm = parse_frontmatter(text)
    assert fm["tags"] == ["a", "b", "c"]


def test_parse_tags_bullet():
    text = "---\ntags:\n  - daily\n  - note\n---\nbody"
    fm = parse_frontmatter(text)
    assert fm["tags"] == ["daily", "note"]


def test_parse_title():
    text = "---\ntitle: My Note\n---\nbody"
    fm = parse_frontmatter(text)
    assert fm["title"] == "My Note"


def test_parse_aliases():
    text = "---\naliases: [alias1, alias2]\n---\nbody"
    fm = parse_frontmatter(text)
    assert fm["aliases"] == ["alias1", "alias2"]


def test_no_frontmatter():
    text = "# Just a heading\nbody"
    fm = parse_frontmatter(text)
    assert fm == {}


def test_strip_frontmatter():
    text = "---\ntitle: X\n---\nbody\nmore"
    assert strip_frontmatter(text) == "body\nmore"
