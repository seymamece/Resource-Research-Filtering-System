"""The topics' titles and coverage, read from the site's own lists.

curriculum/scope-and-sequence.md holds the owner's six sheets (the old ages 13 to 18), three
topics to a table row - the same reading the site's tools/topics.ts does, so a topic here is
the topic there. curriculum/lists-age-5-12.md holds the lists the primary classes draw on,
one topic per row. Topics are named by code - "S6-5" for the sheets, "A5-1" for the age
lists (see curriculum.py).
"""

import re

from . import curriculum, storage

_AGE_13_18 = re.compile(r"^### Age (\d+)")
_AGE_HEADING = re.compile(r"^## Age (\d+)")
_ROW_5_12 = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|")
_CELL = re.compile(r"^\s*(\d+)\s+(.+?)(?:\s*[·—].*)?$")
_EDITORIAL = re.compile(r"\*\(.*?\)\*")
# "— sci [ecology, conservation]" after a title: what the science lens of that topic covers.
_SCIENCE = re.compile(r"sci \[([^\]]+)\]")


def _plain(title: str) -> str:
    return re.sub(r"\*(.+?)\*", r"\1", title.replace("**", "")).strip()


def load() -> dict:
    """{"S6-5": {"title", "science"}}; empty if the site project is not there."""
    topics = {}
    site = storage.site_dir() / "curriculum"
    seq = site / "scope-and-sequence.md"
    if seq.exists():
        age = 0
        for line in seq.read_text(encoding="utf-8").splitlines():
            m = _AGE_13_18.match(line)
            if m:
                age = int(m[1])
                continue
            if line.startswith("## "):
                age = 0
            if age >= 13 and line.startswith("|") and not line.startswith(("|---", "| Topics")):
                for cell in filter(str.strip, line.split("|")):
                    clean = _EDITORIAL.sub("", cell).strip()
                    m = _CELL.match(clean)
                    if m:
                        science = _SCIENCE.search(clean)
                        topics[curriculum.code(age, int(m[1]))] = {
                            "title": _plain(m[2]), "science": science[1] if science else ""}
    lists = site / "lists-age-5-12.md"
    if lists.exists():
        age = 0
        for line in lists.read_text(encoding="utf-8").splitlines():
            m = _AGE_HEADING.match(line)
            if m:
                age = int(m[1])
                continue
            m = _ROW_5_12.match(line)
            if m and 5 <= age <= 12:
                topics[curriculum.code(age, int(m[1]))] = {"title": _plain(m[2]), "science": ""}
    return topics


def coverage() -> dict:
    """{"S6-5": "weak" | "fair" | "good"} from the site's coverage report."""
    path = storage.site_dir() / "curriculum" / "proposals" / "coverage.md"
    found = {}
    if not path.exists():
        return found
    age = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _AGE_HEADING.match(line)
        if m:
            age = int(m[1])
            continue
        cells = [c.strip() for c in line.split("|")]
        if age and len(cells) > 4 and cells[1].isdigit():
            found[curriculum.code(age, int(cells[1]))] = cells[3]
    return found
