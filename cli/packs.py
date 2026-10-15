"""A topic's source pack: one page a lesson writer can work from.

What the catalogue holds for one topic, gathered: the book the owner's sheet points to, the
passages chosen so far with where they are, the moments in subtitled videos that speak to
the topic, and the paragraphs most worth reading next. Everything in it is made from the
catalogue and can be made again at any time, so packs are not kept in git.

Titles are the neutral ones. A source that cannot reach the site is still listed - the
writer may read it - but marked, so nothing from it is carried into a lesson by mistake.
"""

from . import search, text


def _excerpt(body: str, size: int = 280) -> str:
    """One line, so a page's own line breaks do not break the quote block around it."""
    flat = " ".join(body.split())
    return flat[:size] + ("…" if len(flat) > size else "")


def _link(item: dict, where: str | None = None) -> str:
    url = item.get("url")
    if not url:
        return ""
    if where and item.get("youtubeId"):
        start = where.split("-")[0]
        minutes, seconds = start.split(":")
        url = f"https://www.youtube.com/watch?v={item['youtubeId']}&t={int(minutes) * 60 + int(seconds)}s"
    return f" [link]({url})"


class Corpus:
    """Everything readable, indexed once for all the packs of a run."""

    def __init__(self, cat: dict):
        resources = {r["id"]: r for r in cat["resources"]}
        clips = [i for i in cat["items"] if i.get("kind") == "video"]
        texts = [i for i in cat["items"] if i.get("kind") != "video"]
        self.video_units = list(search.readable_units(clips, resources))
        self.text_units = list(search.readable_units(texts, resources))
        self.video_index = search.Index([(n, u[3]) for n, u in enumerate(self.video_units)])
        self.text_index = search.Index([(n, u[3]) for n, u in enumerate(self.text_units)])


def build(cat: dict, key: tuple, info: dict, cover: str, usable: set, corpus: Corpus,
          videos: int = 6, reading: int = 4) -> str:
    age, number = key
    resources = {r["id"]: r for r in cat["resources"]}
    items = {i["id"]: i for i in cat["items"]}

    def source(item):
        r = resources.get(item["resourceId"], {})
        mark = "" if item["id"] in usable else " — *not for the site*"
        return f"{item['title']} ({r.get('role', '?')}){mark}"

    lines = [f"# {age}:{number} {info['title']}", "",
             f"Coverage by the books: **{cover}**" + (f" · science: {info['science']}" if info.get("science") else ""),
             ""]

    hints = [h for h in cat["topicHints"] if (h["age"], h["topic"]) == key]
    lines += ["## From the owner's sheet", ""]
    hinted = []
    for h in hints:
        title = h["hint"].replace(" (related reading)", "")
        match = [i for i in cat["items"] if i["title"] == title and i["ages"]["min"] <= age <= i["ages"]["max"]]
        hinted += match
        book = f" · in the site's catalogue as `{h['catalogueId']}`" if h.get("catalogueId") else ""
        lines.append(f"- {h['hint']}{_link(match[0]) if match else ''}{book}")
    if not hints:
        lines.append("- (no hint for this topic)")
    lines.append("")

    passages = [p for p in cat["passages"] if any((t["age"], t["topic"]) == key for t in p["topics"])]
    lines += [f"## Passages ({len(passages)})", ""]
    for p in sorted(passages, key=lambda p: (p["status"] != "accepted", p["use"])):
        item = items.get(p["itemId"], {})
        refs = " · ".join(x for x in (f"Qur'an {p['qref']}" if p.get("qref") else "",
                                       p.get("href", "")) if x)
        lines.append(f"- **{p['use']}** · {p['status']}{' · ' + refs if refs else ''}")
        if p.get("quote"):
            lines.append(f"  > {p['quote']}")
        lines.append(f"  — {source(item)}, {p['where']}{_link(item, p['where'])} · `{p['id']}`")
    if not passages:
        lines.append("- (none yet)")
    lines.append("")

    # Talks are searched for the topic itself. The hint's book title would pull in any talk
    # that happens to say "word" or "third"; it helps only inside the reading.
    topic_words = " ".join([info["title"], info.get("science", "")])
    query = " ".join([topic_words] + [h["hint"] for h in hints])

    # Video moments: subtitles searched for the topic, at most one moment per video.
    def fits(item):
        return item["ages"]["min"] <= age <= item["ages"]["max"]

    lines += ["## Video moments", ""]
    seen = set()
    for _, n in corpus.video_index.rank(topic_words):
        item, where, _, body = corpus.video_units[n]
        if item["id"] in seen or not fits(item):
            continue
        seen.add(item["id"])
        minutes = f"{item['minutes']} min" if item.get("minutes") else "length ?"
        watched = "watched" if "watchedBy" in item else "not watched yet"
        lines.append(f"- **{item['title']}** — {where} · {minutes} · {watched}{_link(item, where)}")
        lines.append(f"  > {_excerpt(body)}")
        if len(seen) >= videos:
            break
    if not seen:
        lines.append("- (no subtitled video speaks to this topic yet)")
    lines.append("")

    # Reading: the best paragraphs and pages outside what is already quoted.
    quoted = {(p["itemId"], p["where"]) for p in passages}
    units = corpus.text_units
    lines += ["## Worth reading next", ""]
    hinted_ids = {i["id"] for i in hinted}
    ranked = [n for _, n in corpus.text_index.rank(query)
              if fits(units[n][0]) and (units[n][0]["id"], units[n][1]) not in quoted]
    # Some from the hinted chapter, then the best of everything else, books included.
    ranked = ([n for n in ranked if units[n][0]["id"] in hinted_ids][:3]
              + [n for n in ranked if units[n][0]["id"] not in hinted_ids][:reading])
    if ranked:
        for n in ranked:
            item, where, _, body = units[n]
            lines.append(f"- {source(item)}, {where}{_link(item)}")
            lines.append(f"  > {_excerpt(body)}")
    else:
        lines.append("- (nothing fetched yet)")
    lines.append("")
    return "\n".join(lines)
