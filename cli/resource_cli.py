#!/usr/bin/env python3
"""Resource Research & Filtering System - the catalogue.

Run as `py -m cli <command>`. Every record can be added, corrected (`set`, `unset`) and
removed (`remove`) from here. Every write is checked against the site's rules first, and
nothing is saved if the record would be refused.

`verify`, `watched` and `accept` are a person's decisions (rule 3). They always name the
person, and no script or AI may run them.
"""

import json
import sys
from datetime import date
from pathlib import Path

import click

from . import curriculum, model, storage, vocab
from .names import BlockedNames

LIST_FIELDS = {"languages", "classes", "strands", "lenses", "subtitles", "content"}
INT_FIELDS = {"priority", "age", "topic"}
PERSON_FIELDS = {"verifiedBy", "watchedBy", "acceptedBy"}
PERSON_STATUSES = {"verified", "accepted"}
WHAT = ("resources", "items", "passages", "hints")


def _today() -> str:
    return date.today().isoformat()


def _fail(message: str):
    click.echo(f"Error: {message}", err=True)
    sys.exit(1)


def _csv(text: str) -> list[str]:
    return [v.strip() for v in text.split(",") if v.strip()]


def _ages(text: str) -> dict:
    lo, _, hi = text.partition("-")
    try:
        return {"min": int(lo), "max": int(hi or lo)}
    except ValueError:
        raise click.BadParameter(f"'{text}' is not an age (16) or a range (15-18)")


def _topic(text: str) -> str:
    """S6-5 (or the old 18:5), or class#week for a primary class."""
    try:
        return curriculum.parse(text)
    except ValueError as e:
        raise click.BadParameter(str(e))


def _classes(text: str) -> list[str]:
    found = _csv(text)
    unknown = [c for c in found if c not in vocab.CLASS_IDS]
    if unknown:
        raise click.BadParameter(f"{', '.join(unknown)}: expected {', '.join(vocab.CLASS_IDS)}")
    return found


def _minutes(text: str):
    value = float(text)
    return int(value) if value.is_integer() else value


def _parse(key: str, value: str):
    if key in LIST_FIELDS:
        return _csv(value)
    if key == "ages":
        return _ages(value)
    if key == "topics":
        return [curriculum.entry(_topic(t)) for t in _csv(value)]
    if key in INT_FIELDS:
        try:
            return int(value)
        except ValueError:
            raise click.BadParameter(f"'{key}' must be a whole number")
    if key == "minutes":
        try:
            return _minutes(value)
        except ValueError:
            raise click.BadParameter("'minutes' must be a number")
    return value


def _quote_checks(cat: dict, only=None) -> tuple[list, list]:
    from . import records
    return records.quote_checks(cat, only)


def _save(cat: dict, record_id: str, done: str):
    """Saves only if the record passes every check the site will run."""
    blocked = storage.load_blocked()
    problems = [m for rid, m in model.check(cat, blocked) if rid == record_id]
    quote_problems, unchecked = _quote_checks(cat, {record_id})
    problems += [m for _, m in quote_problems]
    if unchecked:
        click.echo("Warning: the item has not been fetched, so the quote was not checked. "
                   "Run `fetch`.", err=True)
    if problems:
        click.echo(f"Not saved - {record_id}:", err=True)
        for m in problems:
            click.echo(f"  - {m}", err=True)
        sys.exit(1)
    storage.save(cat)
    click.echo(f"{done} {record_id}")
    if blocked is None:
        click.echo("Warning: no research/blocked-names.json, so names were not checked. "
                   "Run `sync-names`.", err=True)


def _new(cat: dict, collection: str, record: dict):
    if storage.find(cat, record["id"])[1] is not None:
        _fail(f"{record['id']} already exists. Correct it with `set`.")
    cat[collection].append(record)
    _save(cat, record["id"], "Added")


def _require(cat: dict, record_id: str, collection: str | None = None) -> dict:
    found, record = storage.find(cat, record_id)
    if record is None:
        _fail(f"no record {record_id}")
    if collection and found != collection:
        _fail(f"{record_id} is in {found}, not {collection}")
    return record


def _vocab(values):
    return click.Choice(values)


@click.group()
def cli():
    """Resource Research & Filtering System: the catalogue the site's export is made from."""


# --- setup -----------------------------------------------------------------------------------

@cli.command()
def init():
    """Create an empty catalogue and fetch the blocked-name fingerprints."""
    path = storage.catalogue_path()
    if path.exists():
        click.echo(f"Catalogue already exists: {path}")
    else:
        storage.save(storage.empty())
        click.echo(f"Created {path}")
    source = storage.site_dir() / "research" / "blocked-names.json"
    if source.exists():
        _copy_names(source)
    else:
        click.echo(f"Site project not found at {storage.site_dir()}; run `sync-names --site <path>`.")


def _copy_names(source):
    text = source.read_text(encoding="utf-8")
    try:
        names = BlockedNames(json.loads(text))
    except ValueError as e:
        _fail(f"{source}: {e}")
    target = storage.blocked_names_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    click.echo(f"Copied {names.count} blocked-name fingerprints from {source}")


@cli.command("sync-names")
@click.option("--site", type=click.Path(exists=True, file_okay=False), default=None,
              help="The site project folder (default: SITE_DIR, or ../online-curriculum-).")
def sync_names(site):
    """Copy research/blocked-names.json from the site project. Run after the site changes it."""
    folder = storage.site_dir() if site is None else Path(site)
    source = folder / "research" / "blocked-names.json"
    if not source.exists():
        _fail(f"{source} does not exist")
    _copy_names(source)


# --- adding ----------------------------------------------------------------------------------

@cli.group()
def add():
    """Add a resource, item, passage or topic hint."""


@add.command("resource")
@click.option("-t", "--title", required=True, help="Neutral title, no institution name.")
@click.option("-k", "--kind", required=True, type=_vocab(vocab.RESOURCE_KINDS))
@click.option("-u", "--url", help="Required for everything except a book.")
@click.option("-l", "--lang", "languages", required=True, help="Comma list: en,tr,sw,lg,ar")
@click.option("-c", "--classes", help="Comma list of class ids; default: the classes the ages meet.")
@click.option("-a", "--ages", help="16 or 15-18: kept as a note, and gives the classes if none are named.")
@click.option("-s", "--strands", default="", help="Comma list: " + ",".join(vocab.STRANDS))
@click.option("--lenses", default="", help="Comma list: " + ",".join(vocab.LENSES))
@click.option("-r", "--role", required=True, type=_vocab(vocab.ROLES))
@click.option("--rights", default="pending", show_default=True, type=_vocab(vocab.RIGHTS))
@click.option("-p", "--priority", type=click.IntRange(1, 3))
@click.option("--private-name", help="The real name. Never shown by the site.")
@click.option("--notes", help="Our own words, no institution names.")
@click.option("--catalogue-id", help="The site's s-... id, for a book already in its catalogue.")
@click.option("--retrieved", help="Date last checked (default: today).")
def add_resource(title, kind, url, languages, classes, ages, strands, lenses, role, rights, priority,
                 private_name, notes, catalogue_id, retrieved):
    """A site, channel, book, app or course."""
    if not classes and not ages:
        raise click.BadParameter("give --classes, or --ages to work them out from")
    age_range = _ages(ages) if ages else None
    chosen = _classes(classes) if classes else curriculum.classes_for_ages(age_range)
    cat = storage.load()
    if catalogue_id:
        rid = catalogue_id
    elif url:
        rid = storage.make_id("resources", url.strip())
    else:
        rid = storage.make_id("resources", kind, title.strip())
    record = {"id": rid, "kind": kind, "title": title}
    if private_name:
        record["privateName"] = private_name
    if url:
        record["url"] = url.strip()
    record.update({"languages": _csv(languages), "classes": chosen})
    if age_range:
        record["ages"] = age_range
    record.update({"strands": _csv(strands), "lenses": _csv(lenses), "role": role, "rights": rights})
    if priority:
        record["priority"] = priority
    record["status"] = "to_verify"
    if url or retrieved:
        record["retrieved"] = retrieved or _today()
    if notes:
        record["notes"] = notes
    if catalogue_id:
        record["catalogueId"] = catalogue_id
    _new(cat, "resources", record)


@add.command("item")
@click.option("-R", "--resource", "resource_id", required=True)
@click.option("-k", "--kind", required=True, type=_vocab(vocab.ITEM_KINDS))
@click.option("-t", "--title", required=True, help="Neutral title, no institution name.")
@click.option("-u", "--url")
@click.option("-l", "--lang", "languages", help="Default: the resource's languages.")
@click.option("-a", "--ages", help="Default: the resource's ages.")
@click.option("-s", "--strands", help="Default: the resource's strands.")
@click.option("--lenses", help="Default: the resource's lenses.")
@click.option("--retrieved", help="Default: today.")
@click.option("--minutes", type=float, help="Video length.")
@click.option("--channel", "channel_private", help="Video channel name. Kept private.")
@click.option("--subtitles", help="Video subtitle languages, comma list.")
@click.option("--content", help="What the video shows: " + ",".join(vocab.VIDEO_CONTENT))
def add_item(resource_id, kind, title, url, languages, ages, strands, lenses, retrieved,
             minutes, channel_private, subtitles, content):
    """One article, video, chapter, lesson plan, activity or worksheet of a resource."""
    cat = storage.load()
    resource = _require(cat, resource_id, "resources")
    video = (minutes, channel_private, subtitles, content)
    if kind != "video" and any(v is not None for v in video):
        _fail("--minutes, --channel, --subtitles and --content are for videos")
    iid = storage.make_id("items", url.strip() if url else f"{resource_id}\n{kind}\n{title.strip()}")
    record = {"id": iid, "resourceId": resource_id, "kind": kind, "title": title}
    if url:
        record["url"] = url.strip()
    record.update({
        "languages": _csv(languages) if languages is not None else list(resource.get("languages", [])),
        "ages": _ages(ages) if ages else curriculum.ages_of(resource),
        "strands": _csv(strands) if strands is not None else list(resource.get("strands", [])),
        "lenses": _csv(lenses) if lenses is not None else list(resource.get("lenses", [])),
        "retrieved": retrieved or _today(),
    })
    if kind == "video":
        yid = model.youtube_id(url)
        if yid:
            record["youtubeId"] = yid
        if minutes is not None:
            record["minutes"] = _minutes(str(minutes))
        if channel_private:
            record["channelPrivate"] = channel_private
        if subtitles is not None:
            record["subtitles"] = _csv(subtitles)
        if content is not None:
            record["content"] = _csv(content)
    _new(cat, "items", record)


@add.command("passage")
@click.option("-I", "--item", "item_id", required=True)
@click.option("-w", "--where", required=True, help="Page, section heading, or mm:ss in a video.")
@click.option("-q", "--quote", help="5 to 40 words, exactly as in the source. Required for text.")
@click.option("-T", "--topic", "topics", multiple=True, required=True,
              help="18:5 or 18:5:story. Repeat for several topics.")
@click.option("--use", required=True, type=_vocab(vocab.USES))
@click.option("--qref", help="A Qur'an reference it quotes, like 2:286.")
@click.option("--href", help="A hadith reference it quotes, like 'Bukhari 6094'.")
def add_passage(item_id, where, quote, topics, use, qref, href):
    """One place in an item that fits one or more topics."""
    cat = storage.load()
    _require(cat, item_id, "items")
    from . import records
    record = records.make_passage(item_id, where, quote, [curriculum.entry(_topic(t)) for t in topics],
                                  use, qref, href)
    _new(cat, "passages", record)


@add.command("hint")
@click.option("--age", required=True, type=int)
@click.option("--topic", required=True, type=int)
@click.option("--hint", "text", required=True, help="No institution or website names.")
@click.option("--from-sheet", help="Where in the owner's spreadsheet, like 'S6 week 5'.")
@click.option("--catalogue-id", help="The site's s-... id when the book is in its catalogue.")
def add_hint(age, topic, text, from_sheet, catalogue_id):
    """A source hint for one topic, from the owner's topic spreadsheet."""
    cat = storage.load()
    record = {"id": storage.make_id("topicHints", str(age), str(topic), text.strip()),
              "age": age, "topic": topic}
    if from_sheet:
        record["fromSheet"] = from_sheet
    record.update({"hint": text, "catalogueId": catalogue_id})
    _new(cat, "topicHints", record)


# --- importing the owner's spreadsheets ------------------------------------------------------

def _save_many(cat: dict, changed: list[str]):
    """Saves an import only if every record it touched passes; otherwise nothing at all."""
    blocked = storage.load_blocked()
    touched = set(changed)
    problems = [(rid, m) for rid, m in model.check(cat, blocked) if rid in touched]
    if problems:
        click.echo("Nothing imported. These records would be refused:", err=True)
        for rid, m in problems:
            click.echo(f"  {rid}: {m}", err=True)
        sys.exit(1)
    storage.save(cat)
    if blocked is None:
        click.echo("Warning: no research/blocked-names.json, so names were not checked. "
                   "Run `sync-names`.", err=True)


@cli.group("import")
def import_group():
    """Read one of the owner's spreadsheets into the catalogue. Safe to run again."""


@import_group.command("topics")
@click.argument("xlsx", type=click.Path(exists=True, dir_okay=False))
@click.option("--retrieved", help="Date the linked pages were checked (default: today).")
def import_topics(xlsx, retrieved):
    """The topic sheet (S1-S6: Week | Topic | Source): a hint per topic, and each linked page
    as an item of its site."""
    from . import importers
    cat = storage.load()
    changed, notes, skipped = importers.import_topics(cat, importers.topic_rows(xlsx),
                                                      retrieved or _today())
    _save_many(cat, changed)
    hints = sum(1 for c in changed if c.startswith("h-"))
    click.echo(f"Topic hints added or updated: {hints}; items added or widened: {len(changed) - hints}")
    for line in notes:
        click.echo(line)
    for line in skipped:
        click.echo(f"  skipped {line}")


@import_group.command("plan")
def import_plan():
    """Take the site's classes (content/tracks): each hinted chapter gets the ages of the
    classes its topics are taught in. Run again when the site rewrites its plan."""
    from . import importers
    placement = curriculum.placement()
    if not placement:
        _fail(f"the site's track files were not found under {storage.site_dir()}")
    cat = storage.load()
    changed, report = importers.adopt_plan(cat, placement)
    _save_many(cat, changed)
    click.echo(f"Topics placed in classes: {len(placement)}; chapters re-aged: {len(changed)}")
    for line in report:
        click.echo(f"  {line}")


@import_group.command("books")
def import_books():
    """Every book and set of notes in the site's catalogue (SOURCES_DIR), by catalogue id.
    The text is read from the site's extraction, never copied here."""
    from . import importers
    path = storage.sources_dir() / "_private" / "source-catalog.json"
    if not path.exists():
        _fail(f"{path} not found; set SOURCES_DIR to the site's sources folder")
    cat = storage.load()
    changed, skipped = importers.import_books(cat, json.loads(path.read_text(encoding="utf-8")),
                                              _today(), storage.load_blocked())
    _save_many(cat, changed)
    click.echo(f"Books and notes added: {sum(1 for c in changed if c.startswith('s-'))}")
    for line in skipped:
        click.echo(f"  skipped {line}")


@import_group.command("videos")
@click.argument("xlsx", type=click.Path(exists=True, dir_okay=False))
def import_videos(xlsx):
    """The subtitled-videos sheet (No | title | minutes | channel | link): each video YouTube
    still serves, as an item of its channel. Checks every video online first."""
    from . import importers, youtube
    rows = list(importers.video_rows(xlsx))
    click.echo(f"Asking YouTube about {len({r['youtubeId'] for r in rows if r['youtubeId']})} videos...")
    found = youtube.lookup_many(r["youtubeId"] for r in rows if r["youtubeId"])
    cat = storage.load()
    changed, skipped = importers.import_videos(cat, rows, found, _today(), storage.load_blocked())
    _save_many(cat, changed)
    click.echo(f"Videos added: {len(changed)}")
    for line in skipped:
        click.echo(f"  skipped {line}")


# --- reading sources -------------------------------------------------------------------------

@cli.command()
@click.option("-I", "--item", "item_ids", multiple=True, help="These items only.")
@click.option("-a", "--age", type=click.IntRange(vocab.AGE_MIN, vocab.AGE_MAX),
              help="Items whose ages include this age.")
@click.option("-R", "--resource", "resource_id", help="Items of this resource.")
@click.option("--refresh", is_flag=True, help="Fetch again even if already cached.")
@click.option("--videos", is_flag=True,
              help="Fetch the English subtitles of videos instead (needs yt-dlp; slow).")
def fetch(item_ids, age, resource_id, refresh, videos):
    """Download the text of articles and chapters into cache/text, once each.
    With --videos, the subtitles of videos into cache/subtitles."""
    from concurrent.futures import ThreadPoolExecutor
    from . import text
    cat = storage.load()
    chosen = [i for i in cat["items"] if (i.get("kind") == "video") == videos and i.get("url")]
    if item_ids:
        chosen = [i for i in chosen if i["id"] in item_ids]
    if age is not None:
        chosen = [i for i in chosen if i["ages"]["min"] <= age <= i["ages"]["max"]]
    if resource_id:
        chosen = [i for i in chosen if i["resourceId"] == resource_id]
    cached = text.subtitles_path if videos else text.cache_path
    if not refresh:
        chosen = [i for i in chosen if not cached(i["id"]).exists()]
    if not chosen:
        click.echo("Nothing to fetch.")
        return
    if videos:
        _fetch_subtitles(cat, chosen)
        return
    click.echo(f"Fetching {len(chosen)} item(s)...")
    with ThreadPoolExecutor(4) as pool:
        pages = list(pool.map(lambda i: text.fetch(i["url"]), chosen))
    fetched, failed = 0, []
    for item, (status, html) in zip(chosen, pages):
        if status != 200:
            failed.append(f"{item['id']}: {'unreachable' if status == 0 else status} {item['url']}")
            continue
        title, blocks = text.extract(html)
        size = sum(len(t.split()) for k, t in blocks if k == "p")
        if size < 50:
            failed.append(f"{item['id']}: no readable text found ({size} words) {item['url']}")
            continue
        text.write_cache(item, title, blocks, _today())
        item["retrieved"] = _today()
        fetched += 1
    storage.save(cat)
    click.echo(f"Fetched {fetched}")
    for line in failed:
        click.echo(f"  not fetched {line}")


def _fetch_subtitles(cat: dict, chosen: list):
    """Two at a time, each saved as it arrives, so a run cut short keeps what it got."""
    from concurrent.futures import ThreadPoolExecutor
    from . import text, youtube
    click.echo(f"Fetching subtitles for {len(chosen)} video(s)...")
    got, missing, failed = 0, [], []
    with ThreadPoolExecutor(2) as pool:
        for n, (item, result) in enumerate(zip(chosen, pool.map(
                lambda i: youtube.subtitles(i["youtubeId"]), chosen)), 1):
            if result["status"] == "ok":
                text.write_subtitles(item, result["events"], _today())
                item["retrieved"] = _today()
                if "en" not in item.get("subtitles", []):
                    item["subtitles"] = item.get("subtitles", []) + ["en"]
                got += 1
            elif result["status"] == "none":
                missing.append(f"{item['id']}: {result['reason']}")
            else:
                failed.append(f"{item['id']}: {result['reason']}")
            if n % 25 == 0:
                click.echo(f"  {n}/{len(chosen)}")
    storage.save(cat)
    click.echo(f"Subtitles fetched: {got}; without English subtitles: {len(missing)}; "
               f"failed, try again: {len(failed)}")
    for line in missing + failed:
        click.echo(f"  {line}")


def _topic_context(topic: str) -> dict:
    """The topic's title, class, week, joined topics and ages, from the site's lists."""
    from . import packs, topics as site
    return packs.context(topic, site.load(), site.coverage(), curriculum.placement(),
                         curriculum.plan_notes())


@cli.command()
@click.argument("topic")
@click.option("-n", "--top", default=5, show_default=True, help="Paragraphs from each list.")
@click.option("-w", "--words", "extra", default="", help="More words to search for.")
@click.option("--all", "whole", is_flag=True, help="Print the hinted chapter in full.")
def shortlist(topic, top, extra, whole):
    """The paragraphs to read for a topic (S6-5, or the old 18:5): from the chapter or book
    its hint names, then from everything else that suits the topic's class. Prints a ready
    `where` for each."""
    from . import packs, search
    ctx = _topic_context(_topic(topic))
    cat = storage.load()
    resources = {r["id"]: r for r in cat["resources"]}
    codes = set(ctx["codes"])
    hints = [h for h in cat["topicHints"] if curriculum.key_of(h) in codes]
    where_taught = (f"{curriculum.class_info(ctx['class'])['name']}, week {ctx['week']}"
                    if ctx["class"] else "not in a class yet")
    click.echo(f"{ctx['code']}  {ctx['title']}  ({where_taught}; coverage: {ctx['cover']})")
    if len(ctx["codes"]) > 1:
        click.echo(f"  researched with: {', '.join(ctx['codes'][1:])}")
    if ctx["science"]:
        click.echo(f"  science: {ctx['science']}")
    for h in hints:
        click.echo(f"  hint: {h['hint']}")
    for p in cat["passages"]:
        if any(curriculum.key_of(x) in codes for x in p["topics"]):
            click.echo(f"  already: {p['id']} {p['use']} @ {p['where']}")

    def fits(item):
        return packs.suits(item, resources.get(item["resourceId"], {}), ctx)

    query = " ".join([ctx["title"], ctx["science"], extra] + list(ctx["joined_titles"].values())
                     + [h["hint"] for h in hints])
    hinted_titles = {h["hint"].replace(" (related reading)", "") for h in hints}
    hinted_books = {h["catalogueId"] for h in hints if h.get("catalogueId")}
    hinted = [i for i in cat["items"] if fits(i) and (
        i["title"] in hinted_titles
        or resources.get(i["resourceId"], {}).get("catalogueId") in hinted_books)]

    def show(item, where, body):
        role = resources.get(item["resourceId"], {}).get("role", "?")
        click.echo(f"\n[{item['id']} | {role} | {where}]  {item['title']}\n{body}")

    for item in hinted:
        rows = list(search.readable_units([item], resources))
        if not rows:
            click.echo(f"\n{item['id']} has no text yet: py -m cli fetch -I {item['id']}")
            continue
        book = bool(resources.get(item["resourceId"], {}).get("catalogueId"))
        click.echo(f"\n=== From the hinted {'book' if book else 'chapter'}: {item['title']} "
                   f"({len(rows)} {'pages' if book else 'paragraphs'})")
        if whole and not book:
            chosen = list(range(len(rows)))
        else:
            index = search.Index([(pos, body) for pos, (_, _, _, body) in enumerate(rows)])
            chosen = [pos for _, pos in index.rank(query)[:top]]
            # Few matching words is common in a weak topic; a chapter was still chosen for it,
            # so what it opens with fills the rest. A book is too long for that to help.
            for pos in range(len(rows)):
                if len(chosen) >= top or book:
                    break
                if pos not in chosen:
                    chosen.append(pos)
        for pos in sorted(chosen):
            _, where, _, body = rows[pos]
            show(item, where, body)

    others = [i for i in cat["items"] if i not in hinted and i.get("kind") != "video" and fits(i)]
    rows = list(search.readable_units(others, resources))
    if rows:
        click.echo(f"\n=== Elsewhere ({len(rows)} paragraphs and pages searched)")
        index = search.Index([(pos, body) for pos, (_, _, _, body) in enumerate(rows)])
        for _, pos in index.rank(query)[:top]:
            item, where, _, body = rows[pos]
            show(item, where, body)


_YOUTUBE_LIST = ("youtube.com/@", "youtube.com/channel/", "youtube.com/c/", "youtube.com/user/",
                 "youtube.com/playlist")
_CANNOT_LIST = ("instagram.com", "facebook.com", "tiktok.com", "spotify.com", "apple.com",
                "soundcloud.com", "spreaker.com")
WHOLE_LIMIT = 200


@cli.command()
@click.argument("resource_ids", nargs=-1)
@click.option("--to-verify", "every", is_flag=True,
              help="Every website and channel still to verify, instead of naming them.")
@click.option("-q", "--query", help="Words that must all be in a page's or video's title.")
@click.option("-n", "--limit", type=int, help="Add at most this many per resource.")
@click.option("--count", is_flag=True, help="Only say how many there are and how many match.")
def discover(resource_ids, every, query, limit, count):
    """Add what is inside a website (from its sitemap) or a channel (its video list) as
    items, keeping only titles that hold the --query words. A source with more than
    200 entries needs --query or --limit, so the catalogue holds what was looked for."""
    from . import importers, text, youtube
    from .names import normalise
    cat = storage.load()
    if every:
        chosen = [r for r in cat["resources"] if r["status"] == "to_verify" and r.get("url")
                  and r["kind"] in ("website", "channel", "course", "app") and not r.get("catalogueId")]
    else:
        chosen = [_require(cat, rid, "resources") for rid in resource_ids]
    if not chosen:
        _fail("name resources, or give --to-verify")
    words = normalise(query).split() if query else []
    blocked = storage.load_blocked()
    changed = []
    for r in chosen:
        url = r["url"]
        if any(host in url for host in _CANNOT_LIST):
            click.echo(f"{r['id']}: this platform cannot be listed; add its items by hand")
            continue
        if any(marker in url for marker in _YOUTUBE_LIST):
            found = youtube.channel_videos(url)
            if found["status"] != "ok":
                click.echo(f"{r['id']}: could not list the channel: {found['reason']}")
                continue
            entries = [{"url": youtube.watch_url(v["id"]), "title": v["title"], "kind": "video",
                        "youtubeId": v["id"], "minutes": v["minutes"]} for v in found["videos"]]
        else:
            entries = [{"url": page, "title": text.title_from_url(page), "kind": "article"}
                       for page in text.sitemap(url)]
            if not entries:
                click.echo(f"{r['id']}: no sitemap; add its items by hand")
                continue
        matching = [e for e in entries if not words or all(
            " " + w in " " + normalise(f"{e['title']} {e['url']}") + " " for w in words)]
        if count:
            click.echo(f"{r['id']}: {len(entries)} listed, {len(matching)} match  {r['title']}")
            continue
        if not words and len(entries) > WHOLE_LIMIT and limit is None:
            click.echo(f"{r['id']}: {len(entries)} listed; give --query or --limit  {r['title']}")
            continue
        added, skipped = importers.discover(cat, r, matching, [], _today(), blocked, limit)
        changed += added
        click.echo(f"{r['id']}: {len(added)} added of {len(matching)} matching"
                   + (f", {skipped} skipped for their titles" if skipped else "") + f"  {r['title']}")
    if changed:
        _save_many(cat, changed)
        click.echo(f"Items added: {len(changed)}. Next: fetch, or fetch --videos.")


# --- what comes out for people ---------------------------------------------------------------

def _slug(title: str) -> str:
    from .names import normalise
    return "-".join(normalise(title).split()[:6])


def _pack_name(code: str, title: str) -> str:
    """S6-05-the-heart-and-mind-connection.md: named by the sheet code, as the site asks."""
    if "#" in code:
        track, week = code.split("#")
        return f"{track}-w{int(week):02d}-{_slug(title)}.md"
    sheet, number = code.split("-")
    return f"{sheet}-{int(number):02d}-{_slug(title)}.md"


@cli.command()
@click.option("-c", "--class", "class_id", type=_vocab(vocab.CLASS_IDS), help="Every week of this class.")
@click.option("-T", "--topic", help="One topic: S6-5 (or the old 18:5).")
@click.option("--not-written", is_flag=True, help="Skip the weeks already written on the site.")
@click.option("-o", "--out", type=click.Path(file_okay=False), help="Folder (default: exports/packs).")
def pack(class_id, topic, not_written, out):
    """Write a source pack per topic: hint, passages, video moments, what to read next.
    Topics joined into one week share one pack."""
    from pathlib import Path
    from . import packs, sift, topics as site
    if (class_id is None) == (topic is None):
        _fail("give --class or --topic")
    listed, coverage = site.load(), site.coverage()
    placement, notes = curriculum.placement(), curriculum.plan_notes()
    if topic:
        codes = [_topic(topic)]
    else:
        weeks = curriculum.tracks().get(class_id, [])
        if not weeks:
            _fail(f"{class_id} has no weeks listed yet in the site's track files")
        codes = [w["from"] for w in weeks]
    contexts = [packs.context(c, listed, coverage, placement, notes) for c in codes]
    if not_written:
        contexts = [ctx for ctx in contexts if not ctx["written"]]
    cat = storage.load()
    usable = sift.usable_ids(cat, storage.load_blocked(), _today())
    click.echo("Indexing what has been read...")
    corpus = packs.Corpus(cat)
    root = Path(out) if out else storage.root() / "exports" / "packs"
    written = []
    for ctx in contexts:
        path = root / (ctx["class"] or "unplaced") / _pack_name(ctx["code"], ctx["title"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(packs.build(cat, ctx, usable, corpus), encoding="utf-8")
        written.append((ctx, path.name))
    if class_id:
        name = curriculum.class_info(class_id)["name"]
        index = [f"# Source packs: {name}", ""] + [
            f"{ctx['week']}. [{ctx['code']} {ctx['title']}]({file})"
            + (f" + {', '.join(ctx['codes'][1:])}" if len(ctx["codes"]) > 1 else "")
            + (" · written" if ctx["written"] else "")
            for ctx, file in written]
        (root / class_id / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    click.echo(f"Wrote {len(written)} pack(s) to {root}")


@cli.group()
def review():
    """The owner's review sheet in Excel: export it, then read the decisions back."""


@review.command("export")
@click.option("-c", "--class", "class_id", type=_vocab(vocab.CLASS_IDS),
              help="Only this class's passages, and the videos that suit it.")
@click.option("-o", "--out", type=click.Path(dir_okay=False), help="File (default: exports/review/).")
def review_export(class_id, out):
    """Proposed passages and unwatched videos, with columns for a person's decisions."""
    from pathlib import Path
    from . import review as sheet, topics as site
    path = Path(out) if out else (storage.root() / "exports" / "review" /
                                  f"review-{class_id or 'all'}-{_today()}.xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)
    passages, videos = sheet.write(path, storage.load(), site.load(), class_id, curriculum.placement())
    click.echo(f"Wrote {passages} passages and {videos} videos to review: {path}")


@review.command("import")
@click.argument("xlsx", type=click.Path(exists=True, dir_okay=False))
def review_import(xlsx):
    """Read a filled-in review sheet: accepted and rejected passages, watched videos.
    Only rows that name the person are applied."""
    from . import review as sheet
    cat = storage.load()
    try:
        changed, report = sheet.read(xlsx, cat, _today())
    except ValueError as e:
        _fail(str(e))
    _save_many(cat, changed)
    click.echo(f"Applied {len(changed)} decision(s)")
    for line in report:
        click.echo(f"  {line}")


@cli.command()
@click.option("--port", default=8000, show_default=True)
def ui(port):
    """Open the screens in a browser: http://127.0.0.1:PORT (this machine only)."""
    from .web import serve
    click.echo(f"http://127.0.0.1:{port}  (Ctrl+C to stop)")
    serve(port)


# --- correcting and removing -----------------------------------------------------------------

@cli.command("set")
@click.argument("record_id")
@click.argument("assignments", nargs=-1, required=True)
def set_fields(record_id, assignments):
    """Correct fields: set ID title="New title" ages=15-18 strands=ahlak,akaid

    Lists are comma-separated; topics are like 18:5,18:6:story.
    """
    cat = storage.load()
    record = _require(cat, record_id)
    for assignment in assignments:
        key, sep, value = assignment.partition("=")
        if not sep:
            _fail(f"'{assignment}' is not key=value")
        if key == "id":
            _fail("ids do not change; remove the record and add it again")
        if key in PERSON_FIELDS or (key == "status" and value in PERSON_STATUSES):
            _fail("only a person verifies or accepts; use `verify`, `watched` or `accept`")
        record[key] = _parse(key, value)
        if key == "status":
            record.pop("verifiedBy", None)
            record.pop("acceptedBy", None)
    _save(cat, record_id, "Saved")


@cli.command()
@click.argument("record_id")
@click.argument("fields", nargs=-1, required=True)
def unset(record_id, fields):
    """Remove optional fields from a record: unset ID notes priority"""
    cat = storage.load()
    record = _require(cat, record_id)
    for key in fields:
        if key == "id":
            _fail("a record cannot lose its id")
        if key not in record:
            _fail(f"{record_id} has no '{key}'")
        del record[key]
    _save(cat, record_id, "Saved")


@cli.command()
@click.argument("record_id")
@click.option("--with-children", is_flag=True,
              help="Also remove a resource's items and their passages, or an item's passages.")
def remove(record_id, with_children):
    """Remove a record."""
    cat = storage.load()
    collection, _ = storage.find(cat, record_id)
    if collection is None:
        _fail(f"no record {record_id}")
    items = {i["id"] for i in cat["items"] if i.get("resourceId") == record_id}
    if collection == "items":
        items = {record_id}
    passages = {p["id"] for p in cat["passages"] if p.get("itemId") in items}
    children = (items - {record_id}) | passages
    if children and not with_children:
        _fail(f"{record_id} still has {len(children)} record(s) under it: "
              f"{', '.join(sorted(children))}. Use --with-children to remove them too.")
    gone = children | {record_id}
    for c in storage.COLLECTIONS:
        cat[c] = [r for r in cat[c] if r.get("id") not in gone]
    storage.save(cat)
    click.echo(f"Removed {', '.join(sorted(gone))}")


# --- a person's decisions (rule 3) -----------------------------------------------------------

def _person_option(f):
    return click.option("--by", required=True, help="Your name. Never a script or an AI.")(f)


@cli.command()
@click.argument("resource_id")
@_person_option
def verify(resource_id, by):
    """A person marks a resource verified. Undo with: set ID status=to_verify"""
    cat = storage.load()
    record = _require(cat, resource_id, "resources")
    record["status"] = "verified"
    record["verifiedBy"] = {"by": by, "on": _today()}
    _save(cat, resource_id, "Verified")


@cli.command()
@click.argument("item_id")
@_person_option
def watched(item_id, by):
    """A person records watching a whole video. Undo with: unset ID watchedBy"""
    cat = storage.load()
    record = _require(cat, item_id, "items")
    if record.get("kind") != "video":
        _fail(f"{item_id} is not a video")
    record["watchedBy"] = {"by": by, "on": _today()}
    _save(cat, item_id, "Watched")


@cli.command()
@click.argument("passage_id")
@_person_option
def accept(passage_id, by):
    """A person accepts a proposed passage. Undo with: set ID status=proposed"""
    cat = storage.load()
    record = _require(cat, passage_id, "passages")
    record["status"] = "accepted"
    record["acceptedBy"] = {"by": by, "on": _today()}
    _save(cat, passage_id, "Accepted")


# --- reading ---------------------------------------------------------------------------------

@cli.command()
@click.argument("record_id")
def show(record_id):
    """Print one record in full."""
    record = _require(storage.load(), record_id)
    click.echo(json.dumps(record, indent=2, ensure_ascii=False))


@cli.command("filter")
@click.argument("what", type=click.Choice(WHAT), default="resources")
@click.option("-k", "--kind")
@click.option("-l", "--lang", type=_vocab(vocab.LANGUAGES),
              help="Spoken or written in it, or subtitled in it.")
@click.option("-a", "--age", type=click.IntRange(vocab.AGE_MIN, vocab.AGE_MAX),
              help="Records whose age range includes this age.")
@click.option("-s", "--strand", type=_vocab(vocab.STRANDS))
@click.option("--lens", type=_vocab(vocab.LENSES))
@click.option("-r", "--role", type=_vocab(vocab.ROLES))
@click.option("--rights", type=_vocab(vocab.RIGHTS))
@click.option("--status")
@click.option("-c", "--class", "class_id", type=_vocab(vocab.CLASS_IDS),
              help="Suits this class; for passages and hints, belongs to its topics.")
@click.option("-T", "--topic", help="Reaches this topic through a passage: S6-5 (or 18:5).")
@click.option("--use", type=_vocab(vocab.USES))
@click.option("-q", "--query", help="Words that must all appear: in titles, notes, quotes, "
                                    "and the fetched text of articles and chapters.")
@click.option("--minutes", help="Video length, like 5-20, 5- or -20.")
@click.option("--subtitles", type=_vocab(vocab.LANGUAGES), help="Videos subtitled in it.")
@click.option("--without", help="Videos recorded as free of these: " + ",".join(vocab.VIDEO_CONTENT))
@click.option("--watched/--unwatched", default=None, help="Videos a person has, or has not, watched.")
@click.option("--all", "everything", is_flag=True,
              help="Also show what cannot reach the site: archived, restricted, named in the URL.")
@click.option("-n", "--limit", type=int, help="Show at most this many.")
@click.option("--count", is_flag=True, help="Only say how many match.")
@click.option("--json", "as_json", is_flag=True, help="Print the full records as JSON.")
def filter_records(what, kind, lang, age, strand, lens, role, rights, status, class_id, topic, use,
                   query, minutes, subtitles, without, watched, everything, limit, count, as_json):
    """List resources, items, passages or hints that meet every condition given.

    Only what could reach the site is shown unless --all is given. Video conditions
    (--minutes, --subtitles, --without, --watched) apply to items and passages.
    """
    from . import sift, text
    collection = "topicHints" if what == "hints" else what
    if collection == "topicHints" and any(v is not None for v in (
            kind, lang, strand, lens, role, rights, status, use, minutes, subtitles, without, watched)):
        _fail("hints can only be filtered by --class, --topic and --query")
    if use and collection != "passages":
        _fail("--use filters passages")
    if collection == "resources" and any(v is not None for v in (minutes, subtitles, without, watched)):
        _fail("video conditions filter items and passages: filter items -k video ...")
    conditions = {"kind": kind, "lang": lang, "age": age, "strand": strand, "lens": lens,
                  "role": role, "rights": rights, "status": status, "use": use, "query": query,
                  "subtitles": subtitles, "watched": watched}
    if topic:
        conditions["topic"] = _topic(topic)
    if class_id:
        conditions["class"] = class_id
        conditions["class_ages"] = curriculum.class_info(class_id)["ages"]
        conditions["class_topics"] = {t for t, p in curriculum.placement().items() if p["class"] == class_id}
    if minutes:
        try:
            conditions["minutes"] = sift.parse_range(minutes)
        except ValueError as e:
            raise click.BadParameter(str(e))
    if without:
        conditions["without"] = _csv(without)
        unknown = [v for v in conditions["without"] if v not in vocab.VIDEO_CONTENT]
        if unknown:
            raise click.BadParameter(f"{', '.join(unknown)}: expected {', '.join(vocab.VIDEO_CONTENT)}")

    cat = storage.load()
    # Asking for archived records is asking to see them.
    show_all = everything or status == "archived"
    usable = None if show_all else sift.usable_ids(cat, storage.load_blocked(), _today())

    items = {i["id"]: i for i in cat["items"]}
    resources = {r["id"]: r for r in cat["resources"]}

    def read_text(item_id):
        item = items[item_id]
        found = text.units(item, resources.get(item["resourceId"]))
        return [body for _, _, body in found] if found else None

    results, notes = sift.sift(cat, collection, conditions, usable, read_text)
    total = len(results)
    if count:
        click.echo(f"{total} {what}")
    elif as_json:
        click.echo(json.dumps([r for r, _ in results[:limit]], indent=2, ensure_ascii=False))
    elif not results:
        click.echo(f"No {what} match.")
    else:
        for record, snippet in results[:limit]:
            click.echo(_line(collection, record))
            if snippet:
                click.echo(f"      in the text: {snippet}")
        shown = f"{min(limit, total)} of {total}" if limit and limit < total else str(total)
        click.echo(f"\n{shown} {what}")
    for note in notes:
        click.echo(note, err=True)


@cli.command()
@click.option("-c", "--class", "class_id", type=_vocab(vocab.CLASS_IDS),
              help="One class's weeks, in order. Without it: every class, one line each.")
@click.option("--cover", type=click.Choice(["weak", "fair", "good"]),
              help="Coverage by the books, from the site's report.")
@click.option("--no-passages", is_flag=True, help="Weeks with no passage yet.")
@click.option("--not-written", is_flag=True, help="Weeks not yet written on the site.")
def topics(class_id, cover, no_passages, not_written):
    """The site's classes and weeks, and what the catalogue holds for each topic.
    A week counts the topics joined into it."""
    from . import sift
    from . import topics as site
    rows = sift.week_status(storage.load(), curriculum.tracks(), site.load(), site.coverage(),
                            curriculum.plan_notes())
    if not rows:
        _fail(f"the site's track files were not found under {storage.site_dir()}")
    if class_id is None:
        for cid, name, lo, hi in vocab.CLASSES:
            mine = [r for r in rows if r["class"] == cid]
            if not mine:
                click.echo(f"{cid:<26} {name} ({lo}-{hi}): no weeks listed yet")
                continue
            click.echo(f"{cid:<26} {len(mine):>2} weeks, {sum(1 for r in mine if r['passages'])} with "
                       f"passages, {sum(1 for r in mine if r['written'])} written, "
                       f"{sum(1 for r in mine if r['cover'] == 'weak')} weak")
        return
    rows = [r for r in rows if r["class"] == class_id
            and (cover is None or r["cover"] == cover)
            and (not no_passages or r["passages"] == 0)
            and (not not_written or not r["written"])]
    for r in rows:
        joined = f" + {', '.join(r['joined'])}" if r["joined"] else ""
        written = "  written" if r["written"] else ""
        click.echo(f"{r['week']:>2}. {r['code']:<6} {r['cover']:<5} hints {r['hints']}  "
                   f"passages {r['passages']:<3} {r['title']}{joined}{written}")
    click.echo(f"\n{len(rows)} weeks, {sum(1 for r in rows if r['passages'])} with passages")


def _line(collection, r):
    def ages(a):
        return f"{a.get('min')}-{a.get('max')}" if isinstance(a, dict) else "?"
    if collection == "passages":
        topics = ",".join(curriculum.key_of(t) for t in r.get("topics", []))
        quote = f'  "{r["quote"]}"' if r.get("quote") else ""
        return f"{r['id']}  {r.get('status')}  {r.get('use')}  topics {topics}  @ {r.get('where')}{quote}"
    if collection == "topicHints":
        return f"{r['id']}  {curriculum.key_of(r)}  {r.get('hint')}"
    status = r.get("status", "")
    return (f"{r['id']}  {r.get('kind')}  {r.get('title')}  ages {ages(r.get('ages'))}  "
            f"{','.join(r.get('languages', []))}  {status}").rstrip()


@cli.command()
def stats():
    """Counts by kind, status, role and rights, and passages per topic."""
    cat = storage.load()
    click.echo(f"Resources {len(cat['resources'])}  items {len(cat['items'])}  "
               f"passages {len(cat['passages'])}  topic hints {len(cat['topicHints'])}")
    for collection, keys in (("resources", ("kind", "status", "role", "rights")),
                             ("items", ("kind",)), ("passages", ("status", "use"))):
        for key in keys:
            counts = {}
            for r in cat[collection]:
                counts[r.get(key, "-")] = counts.get(r.get(key, "-"), 0) + 1
            if counts:
                listed = "  ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: str(kv[0])))
                click.echo(f"{collection} by {key}: {listed}")
    per_topic = {}
    for p in cat["passages"]:
        for t in p.get("topics", []):
            k = curriculum.key_of(t)
            per_topic[k] = per_topic.get(k, 0) + 1
    if per_topic:
        listed = "  ".join(f"{k} {c}" for k, c in sorted(per_topic.items(),
                                                          key=lambda kc: curriculum.sort_key(kc[0])))
        click.echo(f"passages per topic: {listed}")


# --- checking and exporting ------------------------------------------------------------------

@cli.command()
def validate():
    """Check the whole catalogue against the site's rules."""
    cat = storage.load()
    blocked = storage.load_blocked()
    quote_problems, unchecked = _quote_checks(cat)
    problems = model.check(cat, blocked) + quote_problems
    for rid, message in problems:
        click.echo(f"{rid}: {message}")
    if unchecked:
        click.echo(f"{len(unchecked)} quote(s) not checked: their items are not fetched.", err=True)
    total = sum(len(cat[c]) for c in storage.COLLECTIONS)
    if blocked is None:
        click.echo("Warning: no research/blocked-names.json, so names were not checked. "
                   "Run `sync-names`.", err=True)
    click.echo(f"{total} records, {len(problems)} problem(s)")
    if problems:
        sys.exit(1)


@cli.command()
@click.option("-p", "--project", type=click.Choice(["online-curriculum"]),
              default="online-curriculum", show_default=True)
def export(project):
    """Write exports/<project>/resources.json for the site. Nothing is written if a check fails."""
    cat = storage.load()
    blocked = storage.load_blocked()
    if blocked is None:
        _fail("research/blocked-names.json is missing, so names cannot be checked. Run `sync-names`.")
    doc, left_out = model.build_export(cat, _today(), blocked)
    problems = model.check(doc, blocked, export=True)
    quote_problems, unchecked = _quote_checks(doc)
    problems += quote_problems
    if unchecked:
        click.echo(f"Warning: {len(unchecked)} quote(s) not checked against their text. "
                   f"Run `fetch` first.", err=True)
    if problems:
        click.echo("Nothing exported. The site would refuse the file:", err=True)
        for rid, message in problems:
            click.echo(f"  {rid}: {message}", err=True)
        sys.exit(1)
    # An id is only this system's handle on a hint; the site's format has none.
    doc["topicHints"] = [{k: v for k, v in h.items() if k != "id"} for h in doc["topicHints"]]
    path = storage.write_export(project, doc)
    click.echo(f"Exported {len(doc['resources'])} resources, {len(doc['items'])} items, "
               f"{len(doc['passages'])} passages, {len(doc['topicHints'])} topic hints")
    click.echo(f"  {path}")
    for rid, reason in left_out:
        click.echo(f"  left out {rid}: {reason}")


if __name__ == "__main__":
    cli()
