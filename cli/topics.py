"""The site's 504 topics, read from the site's own lists so the titles are always its titles.

curriculum/scope-and-sequence.md holds ages 13 to 18, three topics to a table row;
curriculum/lists-age-5-12.md holds ages 5 to 12, one topic per row. This is the same reading
the site's tools/topics.ts does, so a topic here is the topic there.
"""

import re

from . import storage

_AGE_13_18 = re.compile(r"^### Age (\d+)")
_AGE_5_12 = re.compile(r"^## Age (\d+)")
_CELL = re.compile(r"^\s*(\d+)\s+(.+?)(?:\s*[·—].*)?$")
_ROW_5_12 = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|")
_EDITORIAL = re.compile(r"\*\(.*?\)\*")
# "— sci [ecology, conservation]" after a title: what the science lens of that topic covers.
_SCIENCE = re.compile(r"sci \[([^\]]+)\]")


def _plain(title: str) -> str:
    return re.sub(r"\*(.+?)\*", r"\1", title.replace("**", "")).strip()


def load() -> dict:
    """{(age, number): {"title", "science"}}; empty if the site project is not there."""
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
                        topics[(age, int(m[1]))] = {"title": _plain(m[2]),
                                                    "science": science[1] if science else ""}
    lists = site / "lists-age-5-12.md"
    if lists.exists():
        age = 0
        for line in lists.read_text(encoding="utf-8").splitlines():
            m = _AGE_5_12.match(line)
            if m:
                age = int(m[1])
                continue
            m = _ROW_5_12.match(line)
            if m and age:
                topics[(age, int(m[1]))] = {"title": _plain(m[2]), "science": ""}
    return topics


def coverage() -> dict:
    """{(age, number): "weak" | "fair" | "good"} from the site's coverage report."""
    path = storage.site_dir() / "curriculum" / "proposals" / "coverage.md"
    found = {}
    if not path.exists():
        return found
    age = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _AGE_5_12.match(line)
        if m:
            age = int(m[1])
            continue
        cells = [c.strip() for c in line.split("|")]
        if age and len(cells) > 4 and cells[1].isdigit():
            found[(age, int(cells[1]))] = cells[3]
    return found
