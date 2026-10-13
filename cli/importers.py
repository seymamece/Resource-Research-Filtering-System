"""Reading the owner's spreadsheets into the catalogue.

Each importer turns rows into records in the export's shape and leaves the saving, and the
checks that come with it, to the command. Ids come from the URL (or the row's own content),
so running an import again adds what is new and leaves what is already there alone.
"""

import re
from urllib.parse import urlsplit

from openpyxl import load_workbook

from . import model, storage

# The owner's series and the site's ages (requirements section 3.1). S4 is labelled 17-18
# but is the site's age 16.
SERIES_AGE = {"S1": 13, "S2": 14, "S3": 15, "S4": 16, "S5": 17, "S6": 18}

# Who wrote or published a source, as the topic sheet writes it before the title. A hint
# names the book, not the author or the publisher (section 4.5).
_SOURCE_PREFIX = re.compile(r"^(?:Gülen|Said Nursi|Green Dome Foundation)(?:, | – )")
_RELATED = re.compile(r"^Related reading:\s*", re.I)
_SITE_IN_BRACKETS = re.compile(r"\s*\([\w.-]+\.[a-z]{2,}\)\s*$")

# Books in the site's own catalogue (SOURCES_DIR/_private/source-catalog.json), by how the
# topic sheet names them. Only where the edition is certain: the fgulen.com path says which
# volume of Key Concepts a chapter is from, and only volume 1 is catalogued.
SITE_BOOKS = (
    ("The Messenger of God: Muhammad", None, "s-5a47013e44"),
    ("Essentials of the Islamic Faith", None, "s-4e7221047a"),
    ("Key Concepts in Sufism", "/key-concepts-in-the-practice-of-sufism-1/", "s-6b15280cee"),
)


def _host(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def resource_for(cat: dict, url: str) -> dict | None:
    """The resource a URL belongs to: same site, and the longest matching path."""
    host, path = _host(url), urlsplit(url).path
    best, best_len = None, -1
    for r in cat["resources"]:
        if not r.get("url") or _host(r["url"]) != host:
            continue
        rpath = urlsplit(r["url"]).path.rstrip("/")
        rpath = rpath.rsplit("/", 1)[0] if "." in rpath.rsplit("/", 1)[-1] else rpath
        if path.startswith(rpath) and len(rpath) > best_len:
            best, best_len = r, len(rpath)
    return best


# --- the topic sheet -------------------------------------------------------------------------

def topic_rows(path: str):
    """Week | Topic | Source, one sheet per series. Yellow sources are related reading."""
    for ws in load_workbook(path).worksheets:
        series = ws.title.split()[0]
        if series not in SERIES_AGE:
            raise ValueError(f"sheet '{ws.title}' is not one of {', '.join(SERIES_AGE)}")
        for week, topic, source in ws.iter_rows(min_row=2, max_col=3):
            if not isinstance(week.value, int):
                continue
            yield {
                "series": series,
                "age": SERIES_AGE[series],
                "week": week.value,
                "topic": topic.value,
                "source": str(source.value or "").strip(),
                "url": source.hyperlink.target if source.hyperlink else None,
                "related": bool(_RELATED.match(str(source.value or ""))),
            }


def clean_hint(source: str) -> str:
    """'Related reading: Gülen, Pearls of Wisdom – Art (fgulen.com)' -> 'Pearls of Wisdom – Art'"""
    text = _RELATED.sub("", source)
    text = _SITE_IN_BRACKETS.sub("", text)
    return _SOURCE_PREFIX.sub("", text).strip()


def _catalogue_id(hint: str, url: str | None) -> str | None:
    for book, in_path, cid in SITE_BOOKS:
        if book in hint and (in_path is None or (url and in_path in url)):
            return cid
    return None


def import_topics(cat: dict, rows, today: str) -> tuple[list[str], list[str], list[str]]:
    """Adds a topic hint per row, and the linked page as an item of its site.

    Returns (changed ids, notes for the person running it, rows that could not be placed).
    """
    changed, notes, skipped = [], [], []
    hints = {h["id"]: h for h in cat["topicHints"]}
    items = {i["id"]: i for i in cat["items"]}
    for row in rows:
        where = f"{row['series']} week {row['week']}"
        hint = clean_hint(row["source"])
        if not hint:
            skipped.append(f"{where}: no source")
            continue
        text = hint + " (related reading)" if row["related"] else hint
        hid = storage.make_id("topicHints", str(row["age"]), str(row["week"]), text)
        cid = _catalogue_id(hint, row["url"])
        if hid not in hints:
            hints[hid] = {"id": hid, "age": row["age"], "topic": row["week"], "fromSheet": where,
                          "hint": text, "catalogueId": cid}
            cat["topicHints"].append(hints[hid])
            changed.append(hid)
        elif cid and hints[hid].get("catalogueId") is None:
            # The book has been catalogued by the site since the last import.
            hints[hid]["catalogueId"] = cid
            changed.append(hid)

        if not row["url"]:
            skipped.append(f"{where}: no link")
            continue
        resource = resource_for(cat, row["url"])
        if resource is None:
            skipped.append(f"{where}: no resource for {_host(row['url'])} yet")
            continue
        iid = storage.make_id("items", row["url"])
        item = items.get(iid)
        if item is None:
            works = "/fethullah-gulens-works/" in row["url"] or "/risale-i-nur-collection/" in row["url"]
            item = {
                "id": iid, "resourceId": resource["id"], "kind": "chapter" if works else "article",
                "title": hint, "url": row["url"], "languages": ["en"],
                "ages": {"min": row["age"], "max": row["age"]}, "strands": [], "lenses": [],
                "retrieved": today,
            }
            cat["items"].append(item)
            items[iid] = item
            changed.append(iid)
        elif not item["ages"]["min"] <= row["age"] <= item["ages"]["max"]:
            # The same chapter serves topics at several ages.
            item["ages"] = {"min": min(item["ages"]["min"], row["age"]),
                            "max": max(item["ages"]["max"], row["age"])}
            changed.append(iid)
    if any(h.get("catalogueId") for h in cat["topicHints"] if h["id"] in changed):
        notes.append("Hints for books in the site's catalogue carry their catalogueId.")
    return list(dict.fromkeys(changed)), notes, skipped
