"""The screens: a small web app that runs on this machine only.

It adds no rule of its own. Every write goes through records.py, the same checks the
command line runs, and is refused with the same messages. It listens on 127.0.0.1 alone:
the catalogue holds real names in its private fields and the cache holds other people's
texts in full, so nothing here is for the network.

The way in is the site's own: classes, their weeks, and each week's topic by its sheet code.
"""

import os
import threading
from datetime import date

from flask import Flask, abort, flash, redirect, render_template, request, url_for

from .. import curriculum, packs, records, sift, storage, vocab
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

    def class_name(cid):
        return translate(f"class_{cid}", lang())

    @app.context_processor
    def helpers():
        current = lang()
        return {"t": lambda key, **v: translate(key, current, **v), "lang": current,
                "reviewer": request.cookies.get("reviewer", ""), "uses": vocab.USES,
                "link": packs.link, "excerpt": packs.excerpt, "class_name": class_name}

    @app.get("/lang/<code>")
    def set_lang(code):
        response = redirect(request.referrer or url_for("class_list"))
        if code in LANGUAGES:
            response.set_cookie("lang", code, max_age=3600 * 24 * 365, samesite="Lax")
        return response

    def weeks():
        return sift.week_status(storage.load(), curriculum.tracks(), site.load(), site.coverage(),
                                curriculum.plan_notes())

    @app.get("/")
    def class_list():
        rows = weeks()
        summary = []
        for cid, _, lo, hi in vocab.CLASSES:
            mine = [r for r in rows if r["class"] == cid]
            summary.append({"id": cid, "ages": f"{lo}–{hi}", "weeks": len(mine),
                            "with_passages": sum(1 for r in mine if r["passages"]),
                            "written": sum(1 for r in mine if r["written"]),
                            "weak": sum(1 for r in mine if r["cover"] == "weak")})
        return render_template("classes.html", classes=summary)

    @app.get("/class/<class_id>")
    def class_weeks(class_id):
        if class_id not in vocab.CLASS_IDS:
            abort(404)
        show = request.args.get("show", "all")
        rows = [r for r in weeks() if r["class"] == class_id]
        total = len(rows)
        if show == "weak":
            rows = [r for r in rows if r["cover"] == "weak"]
        elif show == "empty":
            rows = [r for r in rows if not r["passages"]]
        elif show == "unwritten":
            rows = [r for r in rows if not r["written"]]
        ages = curriculum.class_info(class_id)["ages"]
        return render_template("class.html", class_id=class_id, rows=rows, show=show, total=total,
                               ages=f"{ages['min']}–{ages['max']}",
                               with_passages=sum(1 for r in rows if r["passages"]))

    def topic_or_404(code):
        try:
            return curriculum.parse(code)
        except ValueError:
            abort(404)

    def gathered(code):
        ctx = packs.context(code, site.load(), site.coverage(), curriculum.placement(),
                            curriculum.plan_notes())
        if ctx["title"] == code and not ctx["class"]:
            abort(404)
        cat = storage.load()
        usable = sift.usable_ids(cat, storage.load_blocked(), _today())
        return packs.gather(cat, ctx, usable, corpus(cat))

    @app.get("/topic/<code>")
    def topic(code):
        code = topic_or_404(code)
        return render_template("topic.html", g=gathered(code), code=code)

    def remember(response, who):
        if who:
            response.set_cookie("reviewer", who, max_age=3600 * 24 * 365, samesite="Lax")
        return response

    @app.post("/topic/<code>/decide")
    def decide(code):
        code = topic_or_404(code)
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
        return remember(redirect(url_for("topic", code=code) + "#passages"), who)

    @app.post("/topic/<code>/add")
    def add(code):
        code = topic_or_404(code)
        f = request.form
        quote = " ".join(f.get("quote", "").split()) or None
        record = records.make_passage(f.get("item", ""), f.get("where", "").strip(), quote,
                                      [curriculum.entry(code)], f.get("use", ""),
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
            return redirect(url_for("topic", code=code) + "#passages")
        # Shown where it was typed, with what was typed, so a quote is corrected, not retyped.
        draft = {k: f.get(k, "") for k in ("item", "where", "quote", "use", "qref", "href")}
        draft["problems"] = problems
        return render_template("topic.html", g=gathered(code), code=code, draft=draft), 422

    return app


def serve(port: int = 8000):
    create_app().run(host="127.0.0.1", port=port, debug=False)
