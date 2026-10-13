"""What each record may hold, and the checks the site will run on the export.

ONLINE-CURRICULUM-REQUIREMENTS.md sections 2 to 4. The same checks guard every write to the
catalogue and the export itself, so a record that would be refused by the site is refused here
first, where it can still be corrected.
"""

import re
from datetime import date

from . import vocab

RESOURCE_FIELDS = {"id", "kind", "title", "privateName", "url", "languages", "ages", "strands",
                   "lenses", "role", "rights", "priority", "status", "retrieved", "notes",
                   "catalogueId", "verifiedBy"}
ITEM_FIELDS = {"id", "resourceId", "kind", "title", "url", "languages", "ages", "strands",
               "lenses", "retrieved"}
VIDEO_FIELDS = {"youtubeId", "minutes", "channelPrivate", "subtitles", "content", "watchedBy"}
PASSAGE_FIELDS = {"id", "itemId", "where", "quote", "qref", "href", "topics", "use", "status",
                  "acceptedBy"}
HINT_FIELDS = {"id", "age", "topic", "fromSheet", "hint", "catalogueId"}

# Real names may stay in these, and only in these (rule 2).
PRIVATE_FIELDS = {"privateName", "channelPrivate"}

QUOTE_WORDS = (5, 40)

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_URL = re.compile(r"^https?://\S+$")
_CATALOGUE_ID = re.compile(r"^s-[0-9a-f]{10}$")
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_TIMESTAMP = re.compile(r"^\d{1,3}:[0-5]\d(-\d{1,3}:[0-5]\d)?$")
_QREF = re.compile(r"^(\d{1,3}):(\d{1,3})(-\d{1,3})?$")
_YOUTUBE_URL = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")


def youtube_id(url: str) -> str | None:
    match = _YOUTUBE_URL.search(url or "")
    return match[1] if match else None


def is_date(value) -> bool:
    if not isinstance(value, str) or not _DATE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class _Checker:
    """Collects problems as (record id, message)."""

    def __init__(self):
        self.problems: list[tuple[str, str]] = []

    def bad(self, rid, message):
        self.problems.append((rid, message))

    def unknown(self, rid, record, allowed):
        for key in record:
            if key not in allowed:
                self.bad(rid, f"unknown field '{key}'")

    def text(self, rid, record, key, required=True):
        value = record.get(key)
        if value is None:
            if required:
                self.bad(rid, f"'{key}' is required")
        elif not isinstance(value, str) or not value.strip():
            self.bad(rid, f"'{key}' must be non-empty text")

    def choice(self, rid, record, key, choices, required=True):
        value = record.get(key)
        if value is None:
            if required:
                self.bad(rid, f"'{key}' is required ({', '.join(choices)})")
        elif value not in choices:
            self.bad(rid, f"'{key}' is '{value}', expected one of {', '.join(choices)}")

    def choices(self, rid, record, key, choices, required=True, nonempty=False):
        value = record.get(key)
        if value is None:
            if required:
                self.bad(rid, f"'{key}' is required (a list, may be empty)" if not nonempty
                         else f"'{key}' is required")
            return
        if not isinstance(value, list):
            self.bad(rid, f"'{key}' must be a list")
            return
        if nonempty and not value:
            self.bad(rid, f"'{key}' needs at least one of {', '.join(choices)}")
        for v in value:
            if v not in choices:
                self.bad(rid, f"'{key}' has '{v}', expected values from {', '.join(choices)}")
        if len(set(map(str, value))) != len(value):
            self.bad(rid, f"'{key}' lists a value twice")

    def ages(self, rid, record):
        ages = record.get("ages")
        if ages is None:
            self.bad(rid, "'ages' is required, as {min, max}")
            return
        if (not isinstance(ages, dict) or set(ages) != {"min", "max"}
                or not _is_int(ages["min"]) or not _is_int(ages["max"])):
            self.bad(rid, "'ages' must be {\"min\": int, \"max\": int}")
            return
        if not vocab.AGE_MIN <= ages["min"] <= ages["max"] <= vocab.AGE_MAX:
            self.bad(rid, f"'ages' {ages['min']}-{ages['max']} is not a range within "
                          f"{vocab.AGE_MIN}-{vocab.AGE_MAX}")

    def day(self, rid, record, key, required):
        value = record.get(key)
        if value is None:
            if required:
                self.bad(rid, f"'{key}' is required (YYYY-MM-DD)")
        elif not is_date(value):
            self.bad(rid, f"'{key}' is '{value}', expected YYYY-MM-DD")

    def url(self, rid, record, required):
        value = record.get("url")
        if value is None:
            if required:
                self.bad(rid, "'url' is required for anything on the web")
        elif not isinstance(value, str) or not _URL.match(value):
            self.bad(rid, f"'url' is '{value}', expected http:// or https://")

    def person(self, rid, record, key):
        """A person's decision: {"by": who, "on": YYYY-MM-DD}."""
        value = record.get(key)
        if value is None:
            return
        if (not isinstance(value, dict) or set(value) != {"by", "on"}
                or not isinstance(value["by"], str) or not value["by"].strip()
                or not is_date(value["on"])):
            self.bad(rid, f"'{key}' must be {{\"by\": a person's name, \"on\": YYYY-MM-DD}}")


def _check_resource(c: _Checker, r: dict):
    rid = r.get("id", "?")
    c.unknown(rid, r, RESOURCE_FIELDS)
    c.text(rid, r, "id")
    c.choice(rid, r, "kind", vocab.RESOURCE_KINDS)
    c.text(rid, r, "title")
    c.text(rid, r, "privateName", required=False)
    c.text(rid, r, "notes", required=False)
    web = r.get("kind") in vocab.WEB_RESOURCE_KINDS
    c.url(rid, r, required=web)
    c.day(rid, r, "retrieved", required=web)
    c.choices(rid, r, "languages", vocab.LANGUAGES, nonempty=True)
    c.ages(rid, r)
    c.choices(rid, r, "strands", vocab.STRANDS)
    c.choices(rid, r, "lenses", vocab.LENSES)
    c.choice(rid, r, "role", vocab.ROLES)
    c.choice(rid, r, "rights", vocab.RIGHTS)
    c.choice(rid, r, "status", vocab.RESOURCE_STATUSES)
    if "priority" in r and r["priority"] not in (1, 2, 3):
        c.bad(rid, f"'priority' is '{r['priority']}', expected 1, 2 or 3")
    if "catalogueId" in r:
        if not isinstance(r["catalogueId"], str) or not _CATALOGUE_ID.match(r["catalogueId"]):
            c.bad(rid, "'catalogueId' must be the site's s- plus 10 hex characters")
        elif r["catalogueId"] != r.get("id"):
            c.bad(rid, "a resource in the site's catalogue takes its catalogue id as its id")
    c.person(rid, r, "verifiedBy")
    if r.get("status") == "verified" and "verifiedBy" not in r:
        c.bad(rid, "'verified' is set by a person: verifiedBy is missing")
    if "verifiedBy" in r and r.get("status") != "verified":
        c.bad(rid, "'verifiedBy' is set but the status is not 'verified'")


def _within(c: _Checker, rid, item, resource):
    """An item may narrow its resource's values, never widen them."""
    ia, ra = item.get("ages"), resource.get("ages")
    if isinstance(ia, dict) and isinstance(ra, dict):
        try:
            if ia["min"] < ra["min"] or ia["max"] > ra["max"]:
                c.bad(rid, f"ages {ia['min']}-{ia['max']} go outside the resource's "
                           f"{ra['min']}-{ra['max']}")
        except (KeyError, TypeError):
            pass  # the shape itself is reported elsewhere
    for key in ("languages", "strands", "lenses"):
        mine, theirs = item.get(key), resource.get(key)
        if isinstance(mine, list) and isinstance(theirs, list) and theirs:
            extra = [v for v in mine if v not in theirs]
            if extra:
                c.bad(rid, f"'{key}' adds {', '.join(map(str, extra))}, which the resource "
                           f"does not have")


def _check_item(c: _Checker, i: dict, resource: dict | None):
    rid = i.get("id", "?")
    video = i.get("kind") == "video"
    c.unknown(rid, i, ITEM_FIELDS | (VIDEO_FIELDS if video else set()))
    c.text(rid, i, "id")
    if resource is None:
        c.bad(rid, f"resource '{i.get('resourceId')}' does not exist")
    c.choice(rid, i, "kind", vocab.ITEM_KINDS)
    c.text(rid, i, "title")
    web = resource is not None and resource.get("kind") in vocab.WEB_RESOURCE_KINDS
    c.url(rid, i, required=web)
    c.day(rid, i, "retrieved", required=True)
    c.choices(rid, i, "languages", vocab.LANGUAGES, nonempty=True)
    c.ages(rid, i)
    c.choices(rid, i, "strands", vocab.STRANDS)
    c.choices(rid, i, "lenses", vocab.LENSES)
    if resource is not None:
        _within(c, rid, i, resource)
    if not video:
        return
    if "youtubeId" in i and not (isinstance(i["youtubeId"], str) and _YOUTUBE_ID.match(i["youtubeId"])):
        c.bad(rid, "'youtubeId' must be the 11-character YouTube id")
    if "minutes" in i and not (isinstance(i["minutes"], (int, float))
                               and not isinstance(i["minutes"], bool) and i["minutes"] > 0):
        c.bad(rid, "'minutes' must be a positive number")
    c.text(rid, i, "channelPrivate", required=False)
    c.choices(rid, i, "subtitles", vocab.LANGUAGES, required=False)
    c.choices(rid, i, "content", vocab.VIDEO_CONTENT, required=False)
    c.person(rid, i, "watchedBy")


def _check_topics(c: _Checker, rid, topics):
    if not isinstance(topics, list) or not topics:
        c.bad(rid, "'topics' needs at least one {age, topic}")
        return
    seen = set()
    for t in topics:
        if not isinstance(t, dict) or not {"age", "topic"} <= set(t) or not set(t) <= {"age", "topic", "use"}:
            c.bad(rid, f"topic {t!r} must be {{age, topic}} with an optional use")
            continue
        if not (_is_int(t["age"]) and vocab.AGE_MIN <= t["age"] <= vocab.AGE_MAX):
            c.bad(rid, f"topic age {t['age']!r} is not within {vocab.AGE_MIN}-{vocab.AGE_MAX}")
        if not (_is_int(t["topic"]) and 1 <= t["topic"] <= vocab.TOPICS_PER_AGE):
            c.bad(rid, f"topic number {t['topic']!r} is not within 1-{vocab.TOPICS_PER_AGE}")
        if "use" in t and t["use"] not in vocab.USES:
            c.bad(rid, f"topic use '{t['use']}', expected one of {', '.join(vocab.USES)}")
        key = (t.get("age"), t.get("topic"))
        if key in seen:
            c.bad(rid, f"topic {key[0]}:{key[1]} is listed twice")
        seen.add(key)


def _check_passage(c: _Checker, p: dict, item: dict | None, resource: dict | None):
    rid = p.get("id", "?")
    c.unknown(rid, p, PASSAGE_FIELDS)
    c.text(rid, p, "id")
    if item is None:
        c.bad(rid, f"item '{p.get('itemId')}' does not exist")
    video = item is not None and item.get("kind") == "video"
    c.text(rid, p, "where")
    if video and isinstance(p.get("where"), str) and not _TIMESTAMP.match(p["where"]):
        c.bad(rid, f"'where' in a video is mm:ss or mm:ss-mm:ss, not '{p['where']}'")
    c.text(rid, p, "quote", required=not video)
    if isinstance(p.get("quote"), str):
        words = len(p["quote"].split())
        lo, hi = QUOTE_WORDS
        if not lo <= words <= hi:
            c.bad(rid, f"'quote' has {words} words; a quote is {lo} to {hi}, copied exactly")
    if "qref" in p:
        m = _QREF.match(p["qref"]) if isinstance(p["qref"], str) else None
        if not m or not 1 <= int(m[1]) <= 114:
            c.bad(rid, f"'qref' is '{p['qref']}', expected surah:ayah like 2:286 or 2:285-286")
    c.text(rid, p, "href", required=False)
    _check_topics(c, rid, p.get("topics"))
    c.choice(rid, p, "use", vocab.USES)
    c.choice(rid, p, "status", vocab.PASSAGE_STATUSES)
    c.person(rid, p, "acceptedBy")
    if p.get("status") == "accepted" and "acceptedBy" not in p:
        c.bad(rid, "'accepted' is set by a person: acceptedBy is missing")
    if "acceptedBy" in p and p.get("status") != "accepted":
        c.bad(rid, "'acceptedBy' is set but the status is not 'accepted'")

    # Rule 1, the order of authority, through the resource's role (section 3.4).
    role = resource.get("role") if resource else None
    uses = {p.get("use")} | {t.get("use") for t in p.get("topics") or [] if isinstance(t, dict)}
    if role == "planning":
        c.bad(rid, "a 'planning' resource may not be cited for anything")
    elif "faith" in uses and role == "method":
        c.bad(rid, "a 'method' resource is never the basis for a statement of faith")
    elif "faith" in uses and role == "religious-supporting" and not (p.get("qref") or p.get("href")):
        c.bad(rid, "a faith statement from a 'religious-supporting' resource must carry the "
                   "qref or href it quotes")


def _check_hint(c: _Checker, h: dict):
    rid = h.get("id", "?")
    c.unknown(rid, h, HINT_FIELDS)
    if not (_is_int(h.get("age")) and vocab.AGE_MIN <= h["age"] <= vocab.AGE_MAX):
        c.bad(rid, f"'age' {h.get('age')!r} is not within {vocab.AGE_MIN}-{vocab.AGE_MAX}")
    if not (_is_int(h.get("topic")) and 1 <= h["topic"] <= vocab.TOPICS_PER_AGE):
        c.bad(rid, f"'topic' {h.get('topic')!r} is not within 1-{vocab.TOPICS_PER_AGE}")
    c.text(rid, h, "fromSheet", required=False)
    c.text(rid, h, "hint")
    cid = h.get("catalogueId")
    if cid is not None and not (isinstance(cid, str) and _CATALOGUE_ID.match(cid)):
        c.bad(rid, "'catalogueId' must be null or the site's s- plus 10 hex characters")


def _strings(value, key=None):
    """Every string in a record, with the field it sits in."""
    if isinstance(value, str):
        yield key, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, k if key is None else key)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v, key)


def check(cat: dict, blocked=None) -> list[tuple[str, str]]:
    """Every problem in a catalogue or an export, as (record id, message)."""
    c = _Checker()
    resources = {r.get("id"): r for r in cat.get("resources", [])}
    items = {i.get("id"): i for i in cat.get("items", [])}

    seen = set()
    for collection in ("resources", "items", "passages", "topicHints"):
        for record in cat.get(collection, []):
            rid = record.get("id")
            if rid in seen:
                c.bad(rid, "this id is used twice")
            seen.add(rid)

    for r in cat.get("resources", []):
        _check_resource(c, r)
    for i in cat.get("items", []):
        _check_item(c, i, resources.get(i.get("resourceId")))
    for p in cat.get("passages", []):
        item = items.get(p.get("itemId"))
        _check_passage(c, p, item, resources.get(item.get("resourceId")) if item else None)
    for h in cat.get("topicHints", []):
        _check_hint(c, h)

    if blocked is not None:
        for collection in ("resources", "items", "passages", "topicHints"):
            for record in cat.get(collection, []):
                for key, text in _strings(record):
                    if key in PRIVATE_FIELDS:
                        continue
                    for name in blocked.found_in(text):
                        c.bad(record.get("id", "?"),
                              f"'{key}' contains a blocked name ('{name}'); keep it in privateName")
    return c.problems


def build_export(cat: dict, today: str) -> tuple[dict, list[tuple[str, str]]]:
    """The file the site reads, and what was left out of it and why."""
    left_out = []
    resources = []
    for r in cat["resources"]:
        if r.get("status") == "archived":
            left_out.append((r["id"], "archived"))
        elif r.get("rights") == "restricted":
            left_out.append((r["id"], "rights are restricted"))
        elif not r.get("url") and not r.get("catalogueId"):
            left_out.append((r["id"], "no url and not in the site's catalogue"))
        else:
            resources.append(r)
    kept = {r["id"] for r in resources}

    items = []
    for i in cat["items"]:
        if i.get("resourceId") not in kept:
            left_out.append((i["id"], "its resource is left out"))
        elif "drawn-prophet" in i.get("content", []):
            left_out.append((i["id"], "shows a drawn prophet, never usable"))
        else:
            items.append(i)
    kept_items = {i["id"] for i in items}

    passages = []
    for p in cat["passages"]:
        if p.get("itemId") not in kept_items:
            left_out.append((p["id"], "its item is left out"))
        else:
            passages.append(p)

    doc = {
        "version": 1,
        "exported": today,
        "resources": resources,
        "items": items,
        "passages": passages,
        "topicHints": list(cat["topicHints"]),
    }
    return doc, left_out
