"""Reading sources: text extraction, the cache, quote checks, search and the site's topics."""

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from cli import search, text, topics
from cli.resource_cli import cli

PAGE = """<html><head><title>Reason - A Site</title><script>var x = "<p>not text</p>";</script></head>
<body><nav><p>Home | About | Contact us and other links that are not the article</p></nav>
<div class="article">
<p><span class="dropcap">L</span>iterally meaning understanding, <i>'aql</i> is a Divine light.
<p>Another approach is that reason, the soul and the mind are three functions of one faculty.
<h3>Kinds of reason</h3>
<p>Reason has been called by different names according to its capacity for perception.
</div>
<footer><p>Copyright notice that should never be read as part of the article text.</p></footer>
</body></html>"""


class ExtractTest(unittest.TestCase):
    def test_unclosed_paragraphs_drop_caps_headings_and_chrome(self):
        title, blocks = text.extract(PAGE)
        self.assertEqual(title, "Reason - A Site")
        self.assertEqual(blocks, [
            ("p", "Literally meaning understanding, 'aql is a Divine light."),
            ("p", "Another approach is that reason, the soul and the mind are three functions of one faculty."),
            ("h", "Kinds of reason"),
            ("p", "Reason has been called by different names according to its capacity for perception."),
        ])

    def test_a_nextjs_page_reads_its_post_not_the_related_ones(self):
        data = {"props": {"pageProps": {
            "post": {"title": "Two Forms of Justice", "content": "<p>" + "Justice is balance. " * 20 + "</p>"},
            "relatedPosts": [{"content": "<p>" + "Something else entirely. " * 40 + "</p>"}]}}}
        html = f'<html><body><div class="x"></div><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'
        title, blocks = text.extract(html)
        self.assertEqual(title, "Two Forms of Justice")
        self.assertTrue(blocks[0][1].startswith("Justice is balance."))
        self.assertNotIn("Something else", " ".join(b for _, b in blocks))


class CacheAndQuoteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"RRFS_ROOT": self.tmp.name})
        self.env.start()
        self.item = {"id": "i-1", "url": "https://example.org/reason"}
        _, blocks = text.extract(PAGE)
        text.write_cache(self.item, "Reason", blocks, "2026-10-13")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_the_cache_reads_back_with_numbered_paragraphs_under_their_heading(self):
        rows = list(text.paragraphs(text.read_cache("i-1")))
        self.assertEqual([(n, h) for n, h, _ in rows], [(1, None), (2, None), (3, "Kinds of reason")])

    def test_a_quote_must_be_in_the_text_as_written(self):
        self.assertTrue(text.quote_found(self.item, None, "reason, the soul and the mind are three functions"))
        self.assertTrue(text.quote_found(self.item, None, "Reason, the Soul, and the Mind are three functions"))
        self.assertFalse(text.quote_found(self.item, None, "reason, the heart and the mind are three functions"))
        self.assertIsNone(text.quote_found({"id": "i-2"}, None, "anything at all here to check"))


class BookTest(unittest.TestCase):
    """A book the site has catalogued is read from the site's extraction, page by page."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        sources = Path(self.tmp.name)
        (sources / "_text").mkdir()
        (sources / "_text" / "s-0123456789.json").write_text(json.dumps({
            "version": 1, "id": "s-0123456789", "unit": "page", "pages": [
                {"n": 1, "label": "42", "text": "According to Muslim theologians, the essentials of\n"
                                                "Prophethood are truthfulness, trust-\nworthiness and"},
                {"n": 2, "label": "43", "text": "communicating God's messages, intelligence."}]}),
            encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"SOURCES_DIR": str(sources)})
        self.env.start()
        self.book = {"id": "s-0123456789", "catalogueId": "s-0123456789"}
        self.item = {"id": "i-b"}

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_pages_are_labelled_as_the_site_cites_them(self):
        self.assertEqual([w for w, _, _ in text.units(self.item, self.book)], ["p. 42", "p. 43"])

    def test_a_quote_must_be_on_its_page_or_run_on_to_the_next(self):
        quote = "Prophethood are truthfulness, trustworthiness and communicating God's messages"
        self.assertTrue(text.quote_found(self.item, self.book, quote, "p. 42"))
        self.assertFalse(text.quote_found(self.item, self.book, quote, "p. 43"))
        self.assertFalse(text.quote_found(self.item, self.book, quote, "p. 99"))

    def test_import_takes_role_and_rights_from_the_site_and_leaves_planning_out(self):
        from cli import importers, model, storage
        cat = storage.empty()
        catalogue = {"entries": [
            {"id": "s-0123456789", "title": "The Messenger of God", "language": "en",
             "role": "religious", "rights": "pending"},
            {"id": "s-aaaaaaaaaa", "title": "Time Management", "language": "en",
             "role": "method", "rights": "restricted"},
            {"id": "s-bbbbbbbbbb", "title": "A seminar file", "language": "tr", "role": "planning"}]}
        changed, skipped = importers.import_books(cat, catalogue, "2026-10-15")
        self.assertEqual([r["id"] for r in cat["resources"]], ["s-0123456789", "s-aaaaaaaaaa"])
        self.assertEqual(cat["resources"][1]["rights"], "restricted")
        self.assertEqual(skipped, ["s-bbbbbbbbbb: planning, cited for nothing"])
        self.assertEqual(model.check(cat), [])
        self.assertEqual(importers.import_books(cat, catalogue, "2026-10-15")[0], [])


class SearchTest(unittest.TestCase):
    def test_bm25_puts_the_paragraph_about_the_topic_first(self):
        index = search.Index([
            ("a", "The heart and the mind work together when a believer reflects."),
            ("b", "Prayer five times a day gives the day its shape."),
            ("c", "The mind alone cannot reach what the heart perceives of the Unseen; the heart leads."),
        ])
        ranked = [key for _, key in index.rank("heart mind connection")]
        self.assertEqual(ranked[0], "c")
        self.assertNotIn("b", ranked)


class SiteTopicsTest(unittest.TestCase):
    def test_both_topic_lists_and_the_coverage_report_are_read(self):
        with tempfile.TemporaryDirectory() as site:
            cur = Path(site) / "curriculum"
            (cur / "proposals").mkdir(parents=True)
            (cur / "scope-and-sequence.md").write_text(
                "### Age 18 — Into the world\n\n| Topics 1–12 | Topics 13–24 |\n|---|---|\n"
                "| 5 The Heart and Mind Connection | 13 Environmental Stewardship — sci [ecology, conservation] |\n"
                "\n## 3. Totals\n| 99 Not a topic |\n", encoding="utf-8")
            (cur / "lists-age-5-12.md").write_text(
                "## Age 5\n\n| # | Topic | Strand | Lenses | Core | People |\n|---|---|---|---|---|---|\n"
                "| 1 | Allah Made Everything Around Us | Akaid | nature | x | |\n", encoding="utf-8")
            (cur / "proposals" / "coverage.md").write_text(
                "## Age 18\n\n| # | Topic | Cover | a | b |\n|---|---|---|---|---|\n"
                "| 5 | The Heart and Mind Connection | good | x | y |\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"SITE_DIR": site}):
                found = topics.load()
                self.assertEqual(found[(18, 5)]["title"], "The Heart and Mind Connection")
                self.assertEqual(found[(18, 13)], {"title": "Environmental Stewardship",
                                                   "science": "ecology, conservation"})
                self.assertEqual(found[(5, 1)]["title"], "Allah Made Everything Around Us")
                self.assertNotIn((18, 99), found)
                self.assertEqual(topics.coverage(), {(18, 5): "good"})


class PassageQuoteCommandTest(unittest.TestCase):
    def test_add_passage_refuses_a_quote_that_is_not_in_the_fetched_text(self):
        with tempfile.TemporaryDirectory() as root:
            env = {"RRFS_ROOT": root, "SITE_DIR": str(Path(root) / "none")}
            run = lambda *a: CliRunner().invoke(cli, list(a), env=env)
            self.assertEqual(run("init").exit_code, 0)
            added = lambda result: re.search(r"Added (\S+)", result.output)[1]
            rid = added(run("add", "resource", "-t", "Works (English)", "-k", "website",
                            "-u", "https://example.org/", "-l", "en", "-a", "13-18", "-r", "religious"))
            iid = added(run("add", "item", "-R", rid, "-k", "chapter", "-t", "Reason",
                            "-u", "https://example.org/reason"))
            with mock.patch.dict(os.environ, {"RRFS_ROOT": root}):
                text.write_cache({"id": iid, "url": "https://example.org/reason"}, "Reason",
                                 text.extract(PAGE)[1], "2026-10-13")
            bad = run("add", "passage", "-I", iid, "-w", "paragraph 2", "-T", "18:5", "--use", "faith",
                      "-q", "reason and the heart are one and the same faculty")
            self.assertNotEqual(bad.exit_code, 0)
            self.assertIn("not in the item's text", bad.output)
            good = run("add", "passage", "-I", iid, "-w", "paragraph 2", "-T", "18:5", "--use", "faith",
                       "-q", "reason, the soul and the mind are three functions of one faculty")
            self.assertEqual(good.exit_code, 0, good.output)


if __name__ == "__main__":
    unittest.main()
