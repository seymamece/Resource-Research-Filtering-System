"""The site's classes, their weeks, and how a topic is named.

A secondary topic is named by its place in the owner's spreadsheet, "S6-5" (sheet S6, topic
5), which does not change when the site moves it to another class or week. The old name
"18:5" is the same topic and is still understood. A primary topic has no sheet code yet and
is named by its class and week, "lower-primary#3".

Which class and week a topic is in comes from the site's own lists,
content/tracks/<class>/track.json. Turkish titles and which weeks are already written come
from CURRICULUM-PLAN.md, the summary the site writes for this tool.
"""

import json
import re

from . import storage, vocab

_CODE = re.compile(r"^\s*[sS]([1-6])\s*-\s*0*([1-9]\d?)\s*$")
# A primary topic's place in the site's lists for ages 5 to 12: "A5-1" is age 5, topic 1.
_AGE_LIST = re.compile(r"^\s*[aA]([5-9]|1[0-2])\s*-\s*0*([1-9]\d?)\s*$")
_OLD = re.compile(r"^\s*([5-9]|1[0-8])\s*:\s*0*([1-9]\d?)\s*$")
_TRACK_WEEK = re.compile(r"^\s*([a-z-]+)\s*[#:]\s*0*([1-9]\d?)\s*$")
SHEET_OF_AGE = {age: sheet for sheet, age in vocab.SHEETS.items()}


def code(age: int, number: int) -> str:
    """The name of topic `number` in the old list for `age`: S6-5 for 18, A5-1 for 5."""
    return f"{SHEET_OF_AGE[age]}-{number}" if age in SHEET_OF_AGE else f"A{age}-{number}"


def parse(text: str) -> str:
    """'S6-5', 's6-05' or the old '18:5' as 'S6-5'; 'A5-1' or the old '5:1' as 'A5-1';
    'lower-primary#3' as it is. Raises ValueError for anything else."""
    for pattern, prefix in ((_CODE, "S"), (_AGE_LIST, "A")):
        m = pattern.match(text)
        if m and 1 <= int(m[2]) <= vocab.TOPICS_PER_AGE:
            return f"{prefix}{m[1]}-{int(m[2])}"
    m = _OLD.match(text)
    if m and 1 <= int(m[2]) <= vocab.TOPICS_PER_AGE:
        return code(int(m[1]), int(m[2]))
    m = _TRACK_WEEK.match(text)
    if m and m[1] in vocab.CLASS_IDS:
        return f"{m[1]}#{int(m[2])}"
    raise ValueError(f"'{text}' is not a topic: use a code like S6-5 or A5-1 (or 18:5, 5:1), "
                     f"or class#week")


def entry(topic: str) -> dict:
    """The export's form of a topic reference (section 4.4)."""
    if "#" in topic:
        track, week = topic.split("#")
        return {"track": track, "week": int(week)}
    return {"from": topic}


def key_of(ref: dict) -> str:
    """The name of the topic a reference points to, whatever form it is in."""
    if "from" in ref:
        return parse(ref["from"])
    if "track" in ref:
        return f"{ref['track']}#{ref['week']}"
    return code(ref["age"], ref["topic"])


def sheet_age(topic: str) -> int | None:
    """The old site age a code comes from (S6-5 -> 18, A5-1 -> 5), for the lists still kept
    by age; None for class#week."""
    if "#" in topic:
        return None
    prefix = topic.split("-")[0]
    return vocab.SHEETS[prefix] if prefix in vocab.SHEETS else int(prefix[1:])


def number(topic: str) -> int:
    return int(topic.split("-")[1] if "#" not in topic else topic.split("#")[1])


def sort_key(topic: str):
    """Primary codes before secondary ones, then by list and number."""
    if "#" in topic:
        return (2, topic.split("#")[0], number(topic))
    return (0 if topic.startswith("A") else 1, sheet_age(topic), number(topic))


def _parse_or(text: str, fallback: str) -> str:
    try:
        return parse(text)
    except ValueError:
        return fallback  # a code this tool does not know yet: the week still shows


# --- classes and weeks -----------------------------------------------------------------------

def class_info(class_id: str) -> dict:
    for cid, name, lo, hi in vocab.CLASSES:
        if cid == class_id:
            return {"id": cid, "name": name, "ages": {"min": lo, "max": hi}}
    raise KeyError(class_id)


def classes_for_ages(ages: dict) -> list[str]:
    """The classes whose approximate ages meet a range: how an old 'ages' becomes 'classes'."""
    return [cid for cid, _, lo, hi in vocab.CLASSES if lo <= ages["max"] and ages["min"] <= hi]


def ages_of(resource: dict) -> dict:
    """A resource's age note, or the span of the classes it lists."""
    if resource.get("ages"):
        return dict(resource["ages"])
    spans = [class_info(c)["ages"] for c in resource.get("classes", [])] or [{"min": 5, "max": 18}]
    return {"min": min(a["min"] for a in spans), "max": max(a["max"] for a in spans)}


def tracks() -> dict:
    """{class id: [{"week", "title", "from", "joined"}]} from the site's track files."""
    found = {}
    folder = storage.site_dir() / "content" / "tracks"
    for cid in vocab.CLASS_IDS:
        path = folder / cid / "track.json"
        if not path.exists():
            continue
        weeks = json.loads(path.read_text(encoding="utf-8")).get("weeks", [])
        found[cid] = [{"week": w["number"], "title": w["title"],
                       "from": _parse_or(w.get("from") or "", f"{cid}#{w['number']}"),
                       "joined": [p for p in (_parse_or(j, "") for j in w.get("joined", [])) if p]}
                      for w in weeks]
    return found


_PLAN_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|")


def plan_notes() -> dict:
    """{topic: {"tr": Turkish title, "written": bool}} from CURRICULUM-PLAN.md, if it is here."""
    path = storage.root() / "CURRICULUM-PLAN.md"
    notes = {}
    if not path.exists():
        return notes
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _PLAN_ROW.match(line)
        if not m:
            continue
        try:
            topic = parse(m[2])
        except ValueError:
            continue
        notes[topic] = {"tr": m[4].strip(), "written": m[6].strip().lower() == "yes"}
    return notes


def placement() -> dict:
    """{topic: {"class", "week", "main", "title"}}: where each topic is taught. A joined topic is
    placed in the week of the topic it was folded into, which is its "main"."""
    found = {}
    for cid, weeks in tracks().items():
        for w in weeks:
            found[w["from"]] = {"class": cid, "week": w["week"], "main": w["from"], "title": w["title"]}
            for j in w["joined"]:
                found[j] = {"class": cid, "week": w["week"], "main": w["from"], "title": w["title"]}
    return found


def joined_with(topic: str) -> list[str]:
    """A topic and every topic folded into the same week: they are researched together."""
    where = placement().get(topic)
    if not where:
        return [topic]
    main = where["main"]
    return [main] + [t for t, p in placement().items() if p["main"] == main and t != main]
