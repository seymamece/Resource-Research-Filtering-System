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

from . import model, storage, vocab
from .names import BlockedNames

LIST_FIELDS = {"languages", "strands", "lenses", "subtitles", "content"}
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


def _topic(text: str) -> dict:
    """18:5 or 18:5:story"""
    parts = text.split(":")
    try:
        topic = {"age": int(parts[0]), "topic": int(parts[1])}
    except (ValueError, IndexError):
        raise click.BadParameter(f"'{text}' is not a topic like 18:5 or 18:5:story")
    if len(parts) > 2:
        topic["use"] = parts[2]
    return topic


def _minutes(text: str):
    value = float(text)
    return int(value) if value.is_integer() else value


def _parse(key: str, value: str):
    if key in LIST_FIELDS:
        return _csv(value)
    if key == "ages":
        return _ages(value)
    if key == "topics":
        return [_topic(t) for t in _csv(value)]
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
    """(problems, unchecked) for passage quotes against their item's cached text."""
    from . import text
    problems, unchecked = [], []
    for p in cat["passages"]:
        if not p.get("quote") or (only is not None and p["id"] not in only):
            continue
        found = text.quote_found(p.get("itemId", ""), p["quote"])
        if found is False:
            problems.append((p["id"], "the quote is not in the item's text; copy it exactly"))
        elif found is None:
            unchecked.append(p["id"])
    return problems, unchecked


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
@click.option("-a", "--ages", required=True, help="16 or 15-18")
@click.option("-s", "--strands", default="", help="Comma list: " + ",".join(vocab.STRANDS))
@click.option("--lenses", default="", help="Comma list: " + ",".join(vocab.LENSES))
@click.option("-r", "--role", required=True, type=_vocab(vocab.ROLES))
@click.option("--rights", default="pending", show_default=True, type=_vocab(vocab.RIGHTS))
@click.option("-p", "--priority", type=click.IntRange(1, 3))
@click.option("--private-name", help="The real name. Never shown by the site.")
@click.option("--notes", help="Our own words, no institution names.")
@click.option("--catalogue-id", help="The site's s-... id, for a book already in its catalogue.")
@click.option("--retrieved", help="Date last checked (default: today).")
def add_resource(title, kind, url, languages, ages, strands, lenses, role, rights, priority,
                 private_name, notes, catalogue_id, retrieved):
    """A site, channel, book, app or course."""
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
    record.update({"languages": _csv(languages), "ages": _ages(ages), "strands": _csv(strands),
                   "lenses": _csv(lenses), "role": role, "rights": rights})
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
        "ages": _ages(ages) if ages else dict(resource.get("ages", {})),
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
    record = {"id": storage.make_id("passages", item_id, where, quote or ""),
              "itemId": item_id, "where": where}
    if quote:
        record["quote"] = quote
    if qref:
        record["qref"] = qref
    if href:
        record["href"] = href
    record.update({"topics": [_topic(t) for t in topics], "use": use, "status": "proposed"})
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
def fetch(item_ids, age, resource_id, refresh):
    """Download the text of articles and chapters into cache/text, once each."""
    from concurrent.futures import ThreadPoolExecutor
    from . import text
    cat = storage.load()
    chosen = [i for i in cat["items"] if i.get("kind") != "video" and i.get("url")]
    if item_ids:
        chosen = [i for i in chosen if i["id"] in item_ids]
    if age is not None:
        chosen = [i for i in chosen if i["ages"]["min"] <= age <= i["ages"]["max"]]
    if resource_id:
        chosen = [i for i in chosen if i["resourceId"] == resource_id]
    if not refresh:
        chosen = [i for i in chosen if not text.cache_path(i["id"]).exists()]
    if not chosen:
        click.echo("Nothing to fetch.")
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


@cli.command()
@click.argument("topic")
@click.option("-n", "--top", default=5, show_default=True, help="Paragraphs from each list.")
@click.option("-w", "--words", "extra", default="", help="More words to search for.")
@click.option("--all", "whole", is_flag=True, help="Print the hinted chapter in full.")
def shortlist(topic, top, extra, whole):
    """The paragraphs to read for a topic (like 18:5): from the chapter its hint names,
    then from everything else fetched. Prints a ready `where` for each."""
    from . import search, topics
    t = _topic(topic)
    key = (t["age"], t["topic"])
    cat = storage.load()
    info = topics.load().get(key, {"title": "(topic list not found)", "science": ""})
    cover = topics.coverage().get(key, "?")
    hints = [h for h in cat["topicHints"] if (h["age"], h["topic"]) == key]
    resources = {r["id"]: r for r in cat["resources"]}
    click.echo(f"{key[0]}:{key[1]}  {info['title']}  (coverage: {cover})")
    if info["science"]:
        click.echo(f"  science: {info['science']}")
    for h in hints:
        click.echo(f"  hint: {h['hint']}")
    for p in cat["passages"]:
        if any((x["age"], x["topic"]) == key for x in p["topics"]):
            click.echo(f"  already: {p['id']} {p['use']} @ {p['where']}")

    query = " ".join([info["title"], info["science"], extra] + [h["hint"] for h in hints])
    hinted_titles = {h["hint"].replace(" (related reading)", "") for h in hints}
    hinted = [i for i in cat["items"] if i["title"] in hinted_titles
              and i["ages"]["min"] <= key[0] <= i["ages"]["max"]]

    def show(item, n, heading, body):
        role = resources.get(item["resourceId"], {}).get("role", "?")
        where = f"section '{heading}', paragraph {n}" if heading else f"paragraph {n}"
        click.echo(f"\n[{item['id']} | {role} | {where}]  {item['title']}\n{body}")

    for item in hinted:
        rows = list(search.cached_paragraphs([item]))
        if not rows:
            click.echo(f"\n{item['id']} is not fetched yet: py -m cli fetch -I {item['id']}")
            continue
        click.echo(f"\n=== From the hinted chapter: {item['title']} ({len(rows)} paragraphs)")
        if whole:
            chosen = [(n, heading, body) for _, n, heading, body in rows]
        else:
            index = search.Index([((n, heading, body), body) for _, n, heading, body in rows])
            chosen = [key for _, key in index.rank(query)[:top]]
            # Few matching words is common in a weak topic; the chapter was still chosen for it,
            # so what it opens with fills the rest.
            for _, n, heading, body in rows:
                if len(chosen) >= top:
                    break
                if (n, heading, body) not in chosen:
                    chosen.append((n, heading, body))
        for n, heading, body in sorted(chosen):
            show(item, n, heading, body)

    others = [i for i in cat["items"] if i not in hinted and i.get("kind") != "video"
              and i["ages"]["min"] <= key[0] <= i["ages"]["max"]]
    rows = list(search.cached_paragraphs(others))
    if rows:
        click.echo(f"\n=== Elsewhere ({len(rows)} paragraphs searched)")
        index = search.Index([((item, n, heading, body), body) for item, n, heading, body in rows])
        for _, (item, n, heading, body) in index.rank(query)[:top]:
            show(item, n, heading, body)


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
@click.option("-T", "--topic", help="Reaches this topic through a passage, like 18:5.")
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
def filter_records(what, kind, lang, age, strand, lens, role, rights, status, topic, use, query,
                   minutes, subtitles, without, watched, everything, limit, count, as_json):
    """List resources, items, passages or hints that meet every condition given.

    Only what could reach the site is shown unless --all is given. Video conditions
    (--minutes, --subtitles, --without, --watched) apply to items and passages.
    """
    from . import sift, text
    collection = "topicHints" if what == "hints" else what
    if collection == "topicHints" and any(v is not None for v in (
            kind, lang, strand, lens, role, rights, status, use, minutes, subtitles, without, watched)):
        _fail("hints can only be filtered by --age, --topic and --query")
    if use and collection != "passages":
        _fail("--use filters passages")
    if collection == "resources" and any(v is not None for v in (minutes, subtitles, without, watched)):
        _fail("video conditions filter items and passages: filter items -k video ...")
    conditions = {"kind": kind, "lang": lang, "age": age, "strand": strand, "lens": lens,
                  "role": role, "rights": rights, "status": status, "use": use, "query": query,
                  "subtitles": subtitles, "watched": watched}
    if topic:
        t = _topic(topic)
        conditions["topic"] = (t["age"], t["topic"])
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

    def read_text(item_id):
        blocks = text.read_cache(item_id)
        return [body for kind_, body in blocks if kind_ == "p"] if blocks else None

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
@click.option("-a", "--age", type=click.IntRange(vocab.AGE_MIN, vocab.AGE_MAX))
@click.option("--cover", type=click.Choice(["weak", "fair", "good"]),
              help="Coverage by the books, from the site's report.")
@click.option("--no-passages", is_flag=True, help="Topics with no passage yet.")
@click.option("--no-hint", is_flag=True, help="Topics with no source hint.")
def topics(age, cover, no_passages, no_hint):
    """The site's topics and what the catalogue holds for each: hints and passages."""
    from . import sift
    from . import topics as site
    listed = site.load()
    if not listed:
        _fail(f"the site's topic lists were not found under {storage.site_dir()}")
    rows = sift.topic_status(storage.load(), listed, site.coverage())
    rows = [r for r in rows if (age is None or r["age"] == age)
            and (cover is None or r["cover"] == cover)
            and (not no_passages or r["passages"] == 0)
            and (not no_hint or r["hints"] == 0)]
    for r in rows:
        click.echo(f"{r['age']}:{r['topic']:<3} {r['cover']:<5} hints {r['hints']}  "
                   f"passages {r['passages']:<3} {r['title']}")
    with_passages = sum(1 for r in rows if r["passages"])
    click.echo(f"\n{len(rows)} topics, {with_passages} with passages, "
               f"{sum(1 for r in rows if r['hints'])} with a hint")


def _line(collection, r):
    def ages(a):
        return f"{a.get('min')}-{a.get('max')}" if isinstance(a, dict) else "?"
    if collection == "passages":
        topics = ",".join(f"{t.get('age')}:{t.get('topic')}" for t in r.get("topics", []))
        quote = f'  "{r["quote"]}"' if r.get("quote") else ""
        return f"{r['id']}  {r.get('status')}  {r.get('use')}  topics {topics}  @ {r.get('where')}{quote}"
    if collection == "topicHints":
        return f"{r['id']}  {r.get('age')}:{r.get('topic')}  {r.get('hint')}"
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
            k = (t.get("age"), t.get("topic"))
            per_topic[k] = per_topic.get(k, 0) + 1
    if per_topic:
        listed = "  ".join(f"{a}:{n} {c}" for (a, n), c in sorted(per_topic.items()))
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
