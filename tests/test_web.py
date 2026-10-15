"""The screens, driven the way a browser drives them, on a throwaway catalogue."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cli import storage, text
from cli.web import _corpus, create_app

PAGE = "<html><body><div><p>Worship seems to be a strenuous demand, but in reality gives " \
       "indescribable peace and comfort.</p><p>The heavy load and weapon are worship and piety, " \
       "and a believer carries them gladly on the road.</p></div></body></html>"


class ScreensTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        site = root / "site" / "curriculum"
        (site / "proposals").mkdir(parents=True)
        (site / "scope-and-sequence.md").write_text(
            "### Age 18\n\n| Topics 1–12 |\n|---|\n| 4 Daily Worship as a Source of Strength |\n",
            encoding="utf-8")
        (site / "proposals" / "coverage.md").write_text(
            "## Age 18\n\n| # | Topic | Cover | a | b |\n|---|---|---|---|---|\n"
            "| 4 | Daily Worship as a Source of Strength | weak | x | y |\n", encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"RRFS_ROOT": str(root), "SITE_DIR": str(root / "site")})
        self.env.start()
        cat = storage.empty()
        cat["resources"] = [{
            "id": "r-w", "kind": "website", "title": "Works (English)", "url": "https://example.org/",
            "languages": ["en"], "ages": {"min": 13, "max": 18}, "strands": [], "lenses": [],
            "role": "religious", "rights": "pending", "status": "to_verify", "retrieved": "2026-10-15"}]
        self.item = {"id": "i-w", "resourceId": "r-w", "kind": "chapter", "title": "The Third Word",
                     "url": "https://example.org/third", "languages": ["en"], "ages": {"min": 18, "max": 18},
                     "strands": [], "lenses": [], "retrieved": "2026-10-15"}
        cat["items"] = [self.item]
        cat["passages"] = [{"id": "p-1", "itemId": "i-w", "where": "paragraph 1",
                            "quote": "Worship seems to be a strenuous demand",
                            "topics": [{"age": 18, "topic": 4}], "use": "faith", "status": "proposed"}]
        storage.save(cat)
        text.write_cache(self.item, "Third", text.extract(PAGE)[1], "2026-10-15")
        _corpus.clear()
        self.client = create_app().test_client()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
        _corpus.clear()

    def passages(self):
        return {p["id"]: p for p in storage.load()["passages"]}

    def test_the_topic_list_and_the_language(self):
        page = self.client.get("/topics/18").get_data(as_text=True)
        self.assertIn("Daily Worship as a Source of Strength", page)
        self.assertIn("zayıf", page)                       # Turkish unless chosen otherwise
        self.client.get("/lang/en")
        self.assertIn("weak", self.client.get("/topics/18").get_data(as_text=True))

    def test_the_topic_screen_shows_the_passage_and_what_to_read(self):
        page = self.client.get("/topic/18/4").get_data(as_text=True)
        self.assertIn("Worship seems to be a strenuous demand", page)
        self.assertIn("The heavy load and weapon are worship and piety", page)
        self.assertEqual(self.client.get("/topic/18/99").status_code, 404)

    def test_no_decision_without_a_name(self):
        self.client.post("/topic/18/4/decide", data={"passage": "p-1", "decision": "accept", "who": " "})
        self.assertEqual(self.passages()["p-1"]["status"], "proposed")
        self.client.post("/topic/18/4/decide", data={"passage": "p-1", "decision": "accept", "who": "Ayse"})
        self.assertEqual(self.passages()["p-1"]["acceptedBy"]["by"], "Ayse")
        self.client.post("/topic/18/4/decide", data={"passage": "p-1", "decision": "undo", "who": "Ayse"})
        self.assertNotIn("acceptedBy", self.passages()["p-1"])
        self.client.post("/topic/18/4/decide", data={"passage": "p-1", "decision": "reject", "who": "Ayse"})
        self.assertNotIn("p-1", self.passages())

    def test_a_wrong_quote_comes_back_where_it_was_typed_and_a_right_one_is_saved(self):
        form = {"item": "i-w", "where": "paragraph 2", "use": "faith",
                "quote": "The heavy load and weapon are prayer and fasting"}
        bad = self.client.post("/topic/18/4/add", data=form)
        self.assertEqual(bad.status_code, 422)
        page = bad.get_data(as_text=True)
        self.assertIn("not in the item&#39;s text", page)
        self.assertIn(">The heavy load and weapon are prayer and fasting</textarea>", page)
        self.assertEqual(len(self.passages()), 1)
        form["quote"] = "The heavy load and weapon are worship and piety"
        good = self.client.post("/topic/18/4/add", data=form)
        self.assertEqual(good.status_code, 302)
        added = [p for p in self.passages().values() if p["where"] == "paragraph 2"]
        self.assertEqual((len(added), added[0]["status"]), (1, "proposed"))


if __name__ == "__main__":
    unittest.main()
