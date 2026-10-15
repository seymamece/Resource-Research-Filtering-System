"""The screens: a small web app that runs on this machine only.

It adds no rule of its own. Every write goes through records.py, the same checks the
command line runs, and is refused with the same messages. It listens on 127.0.0.1 alone:
the catalogue holds real names in its private fields and the cache holds other people's
texts in full, so nothing here is for the network.
"""

import os
import threading
from datetime import date

from flask import Flask, abort, flash, redirect, render_template, request, url_for

from .. import packs, records, sift, storage, vocab
from .. import topics as site
from .i18n import LANGUAGES, translate

_lock = threading.Lock()   # one write at a time
_corpus = {}                # the indexed texts, read once per run


def _today() -> str:
    return date.today().isoformat()


def corpus(cat: dict) -> packs.Corpus:
    with _lock:
        if "c" not in _corpus:
            _corpus["c"] = packs.Corpus(cat)
        return _corpus["c"]


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.urandom(24)  # only for the one-line notices after a save

    def lang() -> str:
        chosen = request.cookies.get("lang")
        return chosen if chosen in LANGUAGES else "tr"

    @app.context_processor
    def helpers():
        current = lang()
        return {"t": lambda key, **v: translate(key, current, **v), "lang": current,
                "reviewer": request.cookies.get("reviewer", ""), "uses": vocab.USES,
                "link": packs.link, "excerpt": packs.excerpt}

    @app.get("/lang/<code>")
    def set_lang(code):
        response = redirect(request.referrer or url_for("topic_list", age=18))
        if code in LANGUAGES:
            response.set_cookie("lang", code, max_age=3600 * 24 * 365, samesite="Lax")
        return response

    @app.get("/")
    def home():
        return redirect(url_for("topic_list", age=18))

    @app.get("/topics/<int:age>")
    def topic_list(age):
        if not vocab.AGE_MIN <= age <= vocab.AGE_MAX:
            abort(404)
        listed = site.load()
        cat = storage.load()
        rows = [r for r in sift.topic_status(cat, listed, site.coverage()) if r["age"] == age]
        accepted = {}
        for p in cat["passages"]:
            if p["status"] == "accepted":
                for t in p["topics"]:
                    accepted[(t["age"], t["topic"])] = accepted.get((t["age"], t["topic"]), 0) + 1
        show = request.args.get("show", "all")
        if show == "weak":
            rows = [r for r in rows if r["cover"] == "weak"]
        elif show == "empty":
            rows = [r for r in rows if not r["passages"]]
        for r in rows:
            r["accepted"] = accepted.get((r["age"], r["topic"]), 0)
        return render_template("topics.html", age=age, rows=rows, show=show,
                               ages=range(vocab.AGE_MIN, vocab.AGE_MAX + 1),
                               with_passages=sum(1 for r in rows if r["passages"]),
                               accepted=sum(r["accepted"] for r in rows))

    def gathered(age, number):
        listed = site.load()
        if (age, number) not in listed:
            abort(404)
        cat = storage.load()
        usable = sift.usable_ids(cat, storage.load_blocked(), _today())
        return packs.gather(cat, (age, number), listed[(age, number)],
                            site.coverage().get((age, number), "?"), usable, corpus(cat))

    @app.get("/topic/<int:age>/<int:number>")
    def topic(age, number):
        return render_template("topic.html", g=gathered(age, number), age=age, number=number)

    def remember(response, who):
        if who:
            response.set_cookie("reviewer", who, max_age=3600 * 24 * 365, samesite="Lax")
        return response

    @app.post("/topic/<int:age>/<int:number>/decide")
    def decide(age, number):
        who = request.form.get("who", "").strip()
        with _lock:
            cat = storage.load()
            try:
                done = records.decide(cat, request.form.get("passage", ""),
                                      request.form.get("decision", ""), who, _today())
            except ValueError as e:
                flash(("error", [str(e)]))
            else:
                storage.save(cat)
                flash(("ok", [translate(f"done_{done}", lang())]))
        back = redirect(url_for("topic", age=age, number=number) + "#passages")
        return remember(back, who)

    @app.post("/topic/<int:age>/<int:number>/add")
    def add(age, number):
        f = request.form
        quote = " ".join(f.get("quote", "").split()) or None
        record = records.make_passage(f.get("item", ""), f.get("where", "").strip(), quote,
                                      [{"age": age, "topic": number}], f.get("use", ""),
                                      f.get("qref", "").strip() or None, f.get("href", "").strip() or None)
        with _lock:
            cat = storage.load()
            if any(p["id"] == record["id"] for p in cat["passages"]):
                problems = [f"{record['id']} already exists"]
            else:
                cat["passages"].append(record)
                problems = [m for _, m in records.problems_for(cat, [record["id"]], storage.load_blocked())]
                if not problems:
                    storage.save(cat)
        if not problems:
            flash(("ok", [translate("saved", lang())]))
            return redirect(url_for("topic", age=age, number=number) + "#passages")
        # Shown where it was typed, with what was typed, so a quote is corrected, not retyped.
        draft = {k: f.get(k, "") for k in ("item", "where", "quote", "use", "qref", "href")}
        draft["problems"] = problems
        return render_template("topic.html", g=gathered(age, number), age=age, number=number,
                               draft=draft), 422

    return app


def serve(port: int = 8000):
    create_app().run(host="127.0.0.1", port=port, debug=False)
