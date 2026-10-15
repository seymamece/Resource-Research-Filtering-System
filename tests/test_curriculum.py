"""Classes, sheet codes, and bringing an older catalogue up to them."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cli import curriculum, importers, migrate, model, storage


class CodesTest(unittest.TestCase):
    def test_a_topic_has_one_name_however_it_is_written(self):
        for written in ("S6-5", "s6-05", " S6 - 5 ", "18:5"):
            self.assertEqual(curriculum.parse(written), "S6-5")
        self.assertEqual(curriculum.parse("16:1"), "S4-1")          # S4 was the site's age 16
        self.assertEqual(curriculum.parse("lower-primary#3"), "lower-primary#3")
        self.assertEqual(curriculum.parse("a10-01"), "A10-1")       # the age lists primary draws on
        self.assertEqual(curriculum.parse("5:1"), "A5-1")
        for wrong in ("S7-1", "S6-37", "A4-1", "A13-1", "19:5", "week 3", "nowhere#2"):
            with self.assertRaises(ValueError):
                curriculum.parse(wrong)

    def test_references_in_every_form(self):
        self.assertEqual(curriculum.entry("S6-5"), {"from": "S6-5"})
        self.assertEqual(curriculum.entry("lower-primary#3"), {"track": "lower-primary", "week": 3})
        self.assertEqual(curriculum.key_of({"age": 13, "topic": 35}), "S1-35")   # a topic hint
        self.assertEqual(curriculum.key_of({"from": "S1-35"}), "S1-35")

    def test_classes_from_an_age_range(self):
        self.assertEqual(curriculum.classes_for_ages({"min": 13, "max": 15}),
                         ["lower-secondary-beginner", "lower-secondary-middle", "lower-secondary-advanced"])
        self.assertEqual(len(curriculum.classes_for_ages({"min": 5, "max": 18})), 8)


class PassageTopicsTest(unittest.TestCase):
    def check(self, topics):
        cat = storage.empty()
        cat["passages"] = [{"id": "p-1", "itemId": "i-x", "where": "p. 1", "quote": "one two three four five",
                            "topics": topics, "use": "example", "status": "proposed"}]
        return [m for _, m in model.check(cat) if "topic" in m]

    def test_only_the_sites_forms_are_accepted(self):
        self.assertEqual(self.check([{"from": "S6-5"}, {"from": "A5-1"},
                                     {"track": "lower-primary", "week": 3}]), [])
        self.assertTrue(self.check([{"age": 18, "topic": 5}]))
        self.assertTrue(self.check([{"from": "18:5"}]))
        self.assertTrue(self.check([{"track": "upper-secondary-middle", "week": 3}]))  # has codes
        self.assertTrue(self.check([{"from": "S6-5"}, {"from": "S6-5"}]))


class UpgradeTest(unittest.TestCase):
    def test_version_1_becomes_version_2_once(self):
        cat = {"version": 1, "items": [], "topicHints": [],
               "resources": [{"id": "r-1", "ages": {"min": 13, "max": 15}}],
               "passages": [{"id": "p-1", "topics": [{"age": 18, "topic": 5}]}]}
        self.assertTrue(migrate.upgrade(cat))
        self.assertEqual(cat["resources"][0]["classes"],
                         ["lower-secondary-beginner", "lower-secondary-middle", "lower-secondary-advanced"])
        self.assertEqual(cat["resources"][0]["ages"], {"min": 13, "max": 15})  # kept as a note
        self.assertEqual(cat["passages"][0]["topics"], [{"from": "S6-5"}])
        self.assertFalse(migrate.upgrade(cat))


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tracks = Path(self.tmp.name) / "content" / "tracks"
        for cid, weeks in {"lower-secondary-advanced": [{"number": 25, "title": "Friends", "from": "S6-17"}],
                           "lower-secondary-beginner": [{"number": 12, "title": "Prayer", "from": "S1-4",
                                                         "joined": ["S1-35"]}]}.items():
            (tracks / cid).mkdir(parents=True)
            (tracks / cid / "track.json").write_text(json.dumps({"track": cid, "weeks": weeks}), encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"SITE_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_joined_topics_sit_in_their_main_topics_week(self):
        place = curriculum.placement()
        self.assertEqual(place["S1-35"], {"class": "lower-secondary-beginner", "week": 12, "main": "S1-4",
                                          "title": "Prayer"})
        self.assertEqual(curriculum.joined_with("S1-35"), ["S1-4", "S1-35"])

    def test_a_hinted_chapter_takes_the_ages_of_the_class_its_topic_moved_to(self):
        cat = storage.empty()
        cat["resources"] = [{"id": "r-w", "classes": ["lower-secondary-advanced"], "ages": {"min": 13, "max": 18}}]
        cat["items"] = [{"id": "i-k", "resourceId": "r-w", "kind": "chapter", "title": "Khulla",
                         "ages": {"min": 18, "max": 18}}]
        cat["topicHints"] = [{"id": "h-1", "age": 18, "topic": 17, "hint": "Khulla", "catalogueId": None}]
        changed, report = importers.adopt_plan(cat, curriculum.placement())
        self.assertEqual((changed, cat["items"][0]["ages"]), (["i-k"], {"min": 13, "max": 15}))
        self.assertEqual(report, [])
        self.assertEqual(importers.adopt_plan(cat, curriculum.placement())[0], [])


if __name__ == "__main__":
    unittest.main()
