"""A topic's source pack: one page a lesson writer can work from.

What the catalogue holds for one topic, gathered: the book the owner's sheet points to, the
passages chosen so far with where they are, the moments in subtitled videos that speak to
the topic, and the paragraphs most worth reading next. Everything in it is made from the
catalogue and can be made again at any time, so packs are not kept in git.

A topic is researched with the topics folded into its week ("joined"), and for the class it
is taught in: a source counts if it lists that class and its ages meet the class's.

gather() collects it as data; build() writes it as Markdown, and the web screen draws the
same data, so the two never disagree about what a topic has.

Titles are the neutral ones. A source that cannot reach the site is still listed - the
writer may read it - but marked, so nothing from it is carried into a lesson by mistake.
"""

from . import curriculum, search


def excerpt(body: str, size: int = 280) -> str:
    """One line, so a page's own line breaks do not break the quote block around it."""
    flat = " ".join(body.split())
    return flat[:size] + ("…" if len(flat) > size else "")


def link(item: dict, where: str | None = None) -> str | None:
    """The item's address; for a video placed at mm:ss, the address of that second."""
    url = item.get("url")
    if url and where and item.get("youtubeId") and ":" in where:
        minutes, seconds = where.split("-")[0].split(":")
        url = f"https://www.youtube.com/watch?v={item['youtubeId']}&t={int(minutes) * 60 + int(seconds)}s"
    return url


def context(topic: str, site_topics: dict, coverage: dict, placement: dict, notes: dict) -> dict:
    """Everything about a topic that is not in the catalogue: its title, class, week, the
    topics joined with it, and the ages the sources must suit."""
    place = placement.get(topic)
    main = place["main"] if place else topic
    codes = [main] + sorted((t for t, p in placement.items() if p["main"] == main and t != main),
                            key=curriculum.sort_key)
    info = site_topics.get(main, {})
    if place:
        ages = curriculum.class_info(place["class"])["ages"]
    else:
        age = curriculum.sheet_age(main)
        ages = {"min": age, "max": age} if age else {"min": 5, "max": 18}
    return {"code": main, "codes": codes, "class": place["class"] if place else None,
            "week": place["week"] if place else None, "ages": ages,
            "title": info.get("title") or (place or {}).get("title") or main,
            "title_tr": notes.get(main, {}).get("tr", ""),
            "written": notes.get(main, {}).get("written", False),
            "science": info.get("science", ""), "cover": coverage.get(main, "?"),
            "joined_titles": {c: site_topics.get(c, {}).get("title", "") for c in codes[1:]}}


def suits(item: dict, resource: dict, ctx: dict) -> bool:
    """A source suits a topic's class if it lists the class and its ages meet the class's."""
    if ctx["class"] and ctx["class"] not in resource.get("classes", [ctx["class"]]):
        return False
    ages = item.get("ages") or resource.get("ages")
    return not ages or (ages["min"] <= ctx["ages"]["max"] and ctx["ages"]["min"] <= ages["max"])


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


def gather(cat: dict, ctx: dict, usable: set, corpus: Corpus, videos: int = 6, reading: int = 4) -> dict:
    resources = {r["id"]: r for r in cat["resources"]}
    items = {i["id"]: i for i in cat["items"]}
    codes = set(ctx["codes"])

    def fits(item):
        return suits(item, resources.get(item["resourceId"], {}), ctx)

    def source(item):
        return {"item": item, "role": resources.get(item.get("resourceId"), {}).get("role", "?"),
                "usable": item.get("id") in usable}

    hints, hinted = [], []
    for h in (h for h in cat["topicHints"] if curriculum.key_of(h) in codes):
        title = h["hint"].replace(" (related reading)", "")
        match = [i for i in cat["items"] if fits(i) and (
            i["title"] == title or (h.get("catalogueId")
                                    and resources.get(i["resourceId"], {}).get("catalogueId") == h["catalogueId"]))]
        hinted += match
        hints.append({"hint": h, "code": curriculum.key_of(h), "item": match[0] if match else None})

    passages = sorted((p for p in cat["passages"] if any(curriculum.key_of(t) in codes for t in p["topics"])),
                      key=lambda p: (p["status"] != "accepted", p["use"]))
    passages = [dict(source(items.get(p["itemId"], {})), passage=p) for p in passages]

    # Talks are searched for the topic itself. The hint's book title would pull in any talk
    # that happens to say "word" or "third"; it helps only inside the reading.
    titles = [ctx["title"]] + [extra for extra in (ctx["science"],) if extra]
    titles += [t for code in ctx["codes"][1:] for t in [ctx.get("joined_titles", {}).get(code, "")] if t]
    topic_words = " ".join(titles)
    query = " ".join([topic_words] + [h["hint"]["hint"] for h in hints])

    moments, seen = [], set()
    for _, n in corpus.video_index.rank(topic_words):
        item, where, _, body = corpus.video_units[n]
        if item["id"] in seen or not fits(item):
            continue
        seen.add(item["id"])
        moments.append(dict(source(item), where=where, text=body))
        if len(moments) >= videos:
            break

    # Reading: the best paragraphs and pages outside what is already quoted - some from the
    # hinted chapter or book, then the best of everything else.
    quoted = {(p["passage"]["itemId"], p["passage"]["where"]) for p in passages}
    units = corpus.text_units
    hinted_ids = {i["id"] for i in hinted}
    ranked = [n for _, n in corpus.text_index.rank(query)
              if fits(units[n][0]) and (units[n][0]["id"], units[n][1]) not in quoted]
    ranked = ([n for n in ranked if units[n][0]["id"] in hinted_ids][:3]
              + [n for n in ranked if units[n][0]["id"] not in hinted_ids][:reading])
    to_read = [dict(source(units[n][0]), where=units[n][1], text=units[n][3]) for n in ranked]

    return {"ctx": ctx, "hints": hints, "passages": passages, "moments": moments, "reading": to_read}


def build(cat: dict, ctx: dict, usable: set, corpus: Corpus, videos: int = 6, reading: int = 4) -> str:
    g = gather(cat, ctx, usable, corpus, videos, reading)

    def md_link(item, where=None):
        url = link(item, where)
        return f" [link]({url})" if url else ""

    def source(s):
        mark = "" if s["usable"] else " — *not for the site*"
        return f"{s['item'].get('title', '?')} ({s['role']}){mark}"

    lines = [f"# {ctx['code']} {ctx['title']}", ""]
    if ctx["title_tr"]:
        lines += [f"*{ctx['title_tr']}*", ""]
    if ctx["class"]:
        name = curriculum.class_info(ctx["class"])["name"]
        lines.append(f"Class: **{name}** (`{ctx['class']}`), week {ctx['week']}")
    if len(ctx["codes"]) > 1:
        lines.append(f"Researched with: {', '.join(ctx['codes'][1:])} (joined in the same week)")
    lines.append(f"Coverage by the books: **{ctx['cover']}**"
                 + (f" · science: {ctx['science']}" if ctx["science"] else "")
                 + (" · **already written on the site**" if ctx["written"] else ""))
    lines += ["", "## From the owner's sheet", ""]
    for h in g["hints"]:
        book = f" · in the site's catalogue as `{h['hint']['catalogueId']}`" if h["hint"].get("catalogueId") else ""
        joined = f" ({h['code']})" if h["code"] != ctx["code"] else ""
        lines.append(f"- {h['hint']['hint']}{joined}{md_link(h['item']) if h['item'] else ''}{book}")
    if not g["hints"]:
        lines.append("- (no hint for this topic)")

    lines += ["", f"## Passages ({len(g['passages'])})", ""]
    for s in g["passages"]:
        p = s["passage"]
        refs = " · ".join(x for x in (f"Qur'an {p['qref']}" if p.get("qref") else "", p.get("href", "")) if x)
        lines.append(f"- **{p['use']}** · {p['status']}{' · ' + refs if refs else ''}")
        if p.get("quote"):
            lines.append(f"  > {p['quote']}")
        lines.append(f"  — {source(s)}, {p['where']}{md_link(s['item'], p['where'])} · `{p['id']}`")
    if not g["passages"]:
        lines.append("- (none yet)")

    lines += ["", "## Video moments", ""]
    for m in g["moments"]:
        item = m["item"]
        minutes = f"{item['minutes']} min" if item.get("minutes") else "length ?"
        watched = "watched" if "watchedBy" in item else "not watched yet"
        lines.append(f"- **{item['title']}** — {m['where']} · {minutes} · {watched}{md_link(item, m['where'])}")
        lines.append(f"  > {excerpt(m['text'])}")
    if not g["moments"]:
        lines.append("- (no subtitled video speaks to this topic yet)")

    lines += ["", "## Worth reading next", ""]
    for r in g["reading"]:
        lines.append(f"- {source(r)}, {r['where']}{md_link(r['item'])}")
        lines.append(f"  > {excerpt(r['text'])}")
    if not g["reading"]:
        lines.append("- (nothing fetched yet)")
    lines.append("")
    return "\n".join(lines)
