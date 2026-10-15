"""Sifting the catalogue by the conditions a lesson writer asks for.

Every condition narrows; a record is shown only if it meets all of them. By default only
what could reach the site is shown - the same rule the export applies - because a resource
that is archived, restricted or named in its URL is not one a lesson can use.

Where the catalogue does not know the answer, the record is left out and the count is
reported, never guessed: a video nobody has watched is not "without music".
"""

from . import model
from .names import normalise


def parse_range(text: str) -> tuple[float, float]:
    """'5-20', '5-' or '-20' as (low, high)."""
    lo, sep, hi = text.partition("-")
    try:
        if not sep:
            return float(lo), float(lo)
        return (float(lo) if lo.strip() else 0.0), (float(hi) if hi.strip() else float("inf"))
    except ValueError:
        raise ValueError(f"'{text}' is not a range like 5-20, 5- or -20")


def usable_ids(cat: dict, blocked, today: str) -> set:
    """Ids of every resource, item and passage the export would include."""
    doc, _ = model.build_export(cat, today, blocked)
    return {r["id"] for c in ("resources", "items", "passages") for r in doc[c]}


def _has_words(words, haystack: str) -> bool:
    hay = " " + normalise(haystack) + " "
    return all(" " + w in hay for w in words)


def _snippet(words, paragraphs, size=30) -> str | None:
    """The first paragraph holding every word, cut down around the first of them."""
    for text in paragraphs:
        if _has_words(words, text):
            tokens = text.split()
            plain = [normalise(t) for t in tokens]
            at = next((i for i, t in enumerate(plain) if t.startswith(words[0])), 0)
            start = max(0, at - size // 3)
            cut = " ".join(tokens[start:start + size])
            return ("… " if start else "") + cut + (" …" if start + size < len(tokens) else "")
    return None


def sift(cat: dict, collection: str, c: dict, usable: set | None, read_text) -> tuple[list, list]:
    """(results as (record, snippet or None), notes) for one collection.

    c holds the conditions given: kind, lang, age, strand, lens, role, rights, status,
    topic (age, number), use, minutes (low, high), subtitles, without [content],
    watched (True/False), query. read_text(item_id) gives an item's cached paragraphs.
    """
    resources = {r["id"]: r for r in cat["resources"]}
    items = {i["id"]: i for i in cat["items"]}
    reached = {}  # record id -> topics its passages reach
    for p in cat["passages"]:
        topics = {(t["age"], t["topic"]) for t in p["topics"]}
        item = items.get(p["itemId"], {})
        for key in (p["id"], p["itemId"], item.get("resourceId")):
            reached.setdefault(key, set()).update(topics)
    words = normalise(c["query"]).split() if c.get("query") else []

    video_asked = any(c.get(k) is not None for k in ("minutes", "subtitles", "without", "watched"))
    hidden = unknown_content = 0
    results = []
    for record in cat[collection]:
        if collection == "topicHints":
            if c.get("age") is not None and record["age"] != c["age"]:
                continue
            if c.get("topic") and (record["age"], record["topic"]) != c["topic"]:
                continue
            if words and not _has_words(words, f"{record['hint']} {record.get('fromSheet', '')}"):
                continue
            results.append((record, None))
            continue

        item = record if collection == "items" else items.get(record.get("itemId"))
        resource = record if collection == "resources" else resources.get((item or {}).get("resourceId"), {})
        described = record if collection in ("resources", "items") else (item or {})

        if usable is not None and record["id"] not in usable:
            hidden += 1
            continue
        if c.get("kind") and described.get("kind") != c["kind"]:
            continue
        if c.get("lang") and c["lang"] not in described.get("languages", []) + described.get("subtitles", []):
            continue
        if c.get("strand") and c["strand"] not in described.get("strands", []):
            continue
        if c.get("lens") and c["lens"] not in described.get("lenses", []):
            continue
        if c.get("role") and resource.get("role") != c["role"]:
            continue
        if c.get("rights") and resource.get("rights") != c["rights"]:
            continue
        if c.get("status") and (record.get("status") or resource.get("status")) != c["status"]:
            continue
        if c.get("age") is not None:
            if collection == "passages":
                if c["age"] not in {t["age"] for t in record["topics"]}:
                    continue
            elif not described["ages"]["min"] <= c["age"] <= described["ages"]["max"]:
                continue
        if c.get("topic") and c["topic"] not in reached.get(record["id"], set()):
            continue
        if c.get("use") and c["use"] != record.get("use") \
                and c["use"] not in {t.get("use") for t in record.get("topics", [])}:
            continue

        if video_asked:
            if described.get("kind") != "video":
                continue
            if c.get("minutes"):
                lo, hi = c["minutes"]
                if described.get("minutes") is None or not lo <= described["minutes"] <= hi:
                    continue
            if c.get("subtitles") and c["subtitles"] not in described.get("subtitles", []):
                continue
            if c.get("watched") is not None and ("watchedBy" in described) != c["watched"]:
                continue
            if c.get("without"):
                if "content" not in described:
                    unknown_content += 1
                    continue
                if set(c["without"]) & set(described["content"]):
                    continue

        snippet = None
        if words:
            if collection == "resources":
                own = " ".join(str(record.get(k, "")) for k in ("title", "notes", "privateName", "url"))
            elif collection == "items":
                own = " ".join(str(record.get(k, "")) for k in ("title", "channelPrivate", "url"))
            else:
                own = f"{record.get('quote', '')} {record.get('where', '')} {(item or {}).get('title', '')}"
            if not _has_words(words, own):
                body = read_text(record["id"]) if collection == "items" else None
                snippet = _snippet(words, body) if body else None
                if snippet is None:
                    continue
        results.append((record, snippet))

    notes = []
    if hidden:
        notes.append(f"{hidden} not shown: archived, restricted, or not able to reach the site. "
                     f"--all shows them.")
    if unknown_content:
        notes.append(f"{unknown_content} video(s) left out: nobody has recorded what is in them yet.")
    return results, notes


def topic_status(cat: dict, site_topics: dict, coverage: dict) -> list[dict]:
    """One row per site topic: its title, coverage, and what the catalogue holds for it."""
    hints, passages = {}, {}
    for h in cat["topicHints"]:
        hints[(h["age"], h["topic"])] = hints.get((h["age"], h["topic"]), 0) + 1
    for p in cat["passages"]:
        for t in p["topics"]:
            passages[(t["age"], t["topic"])] = passages.get((t["age"], t["topic"]), 0) + 1
    return [{"age": age, "topic": num, "title": info["title"], "cover": coverage.get((age, num), "?"),
             "hints": hints.get((age, num), 0), "passages": passages.get((age, num), 0)}
            for (age, num), info in sorted(site_topics.items())]
