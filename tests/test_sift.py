"""Sifting by conditions: py -m unittest"""

import unittest

from cli import sift, storage


def resource(rid, **extra):
    r = {"id": rid, "kind": "channel", "title": "Talks (Turkish)", "url": f"https://example.org/{rid}",
         "languages": ["tr"], "ages": {"min": 13, "max": 18}, "strands": [], "lenses": [],
         "role": "religious-supporting", "rights": "pending", "status": "to_verify",
         "retrieved": "2026-10-15"}
    r.update(extra)
    return r


def video(iid, rid, minutes, **extra):
    i = {"id": iid, "resourceId": rid, "kind": "video", "title": f"Talk {iid}",
         "url": f"https://www.youtube.com/watch?v={iid}", "languages": ["tr"],
         "ages": {"min": 13, "max": 18}, "strands": [], "lenses": [], "retrieved": "2026-10-15",
         "minutes": minutes, "subtitles": ["en"]}
    i.update(extra)
    return i


class SiftTest(unittest.TestCase):
    def setUp(self):
        self.cat = storage.empty()
        self.cat["resources"] = [resource("r-a"), resource("r-old", status="archived")]
        self.cat["items"] = [
            video("v1", "r-a", 12),
            video("v2", "r-a", 45),
            video("v3", "r-a", 8, content=["talk"]),
            video("v4", "r-a", 9, content=["talk", "music"], watchedBy={"by": "Ayse", "on": "2026-10-15"}),
            video("v5", "r-old", 10),
            {"id": "c1", "resourceId": "r-a", "kind": "chapter", "title": "Sabr", "url": "https://example.org/sabr",
             "languages": ["en"], "ages": {"min": 13, "max": 13}, "strands": [], "lenses": [],
             "retrieved": "2026-10-15"},
        ]
        self.usable = sift.usable_ids(self.cat, None, "2026-10-15")
        self.texts = {"c1": ["Patience is the key to relief.",
                             "Resisting temptations with patience is counted as a form of worship."]}

    def ids(self, collection="items", usable="default", **c):
        found, notes = sift.sift(self.cat, collection, c, self.usable if usable == "default" else usable,
                                 self.texts.get)
        return [r["id"] for r, _ in found], notes

    def test_ranges(self):
        self.assertEqual(sift.parse_range("5-20"), (5, 20))
        self.assertEqual(sift.parse_range("5-"), (5, float("inf")))
        self.assertEqual(sift.parse_range("-20"), (0, 20))
        with self.assertRaises(ValueError):
            sift.parse_range("five")

    def test_only_what_can_reach_the_site_unless_asked(self):
        ids, notes = self.ids()
        self.assertNotIn("v5", ids)
        self.assertIn("1 not shown", notes[0])
        self.assertIn("v5", self.ids(usable=None)[0])

    def test_a_language_matches_subtitles_too(self):
        self.assertEqual(self.ids(lang="en", kind="video")[0], ["v1", "v2", "v3", "v4"])

    def test_video_length_watched_and_subtitles(self):
        self.assertEqual(self.ids(minutes=(5, 20))[0], ["v1", "v3", "v4"])
        self.assertEqual(self.ids(watched=True)[0], ["v4"])
        self.assertEqual(self.ids(watched=False, minutes=(5, 20))[0], ["v1", "v3"])
        self.assertEqual(self.ids(subtitles="tr")[0], [])

    def test_without_needs_someone_to_have_recorded_the_content(self):
        ids, notes = self.ids(without=["music"])
        self.assertEqual(ids, ["v3"])
        self.assertIn("2 video(s) left out: nobody has recorded", notes[-1])

    def test_words_are_found_in_titles_and_in_fetched_text_with_a_snippet(self):
        found, _ = sift.sift(self.cat, "items", {"query": "temptations patience"}, self.usable, self.texts.get)
        self.assertEqual([r["id"] for r, _ in found], ["c1"])
        self.assertIn("Resisting temptations with patience", found[0][1])
        self.assertEqual(self.ids(query="SABR")[0], ["c1"])        # title, any case
        self.assertEqual(self.ids(query="talk v3")[0], ["v3"])

    def test_topic_status(self):
        self.cat["topicHints"] = [{"id": "h-1", "age": 13, "topic": 1, "hint": "x", "catalogueId": None}]
        rows = sift.topic_status(self.cat, {(13, 1): {"title": "Intro"}, (13, 2): {"title": "Love"}},
                                 {(13, 1): "weak"})
        self.assertEqual([(r["topic"], r["cover"], r["hints"], r["passages"]) for r in rows],
                         [(1, "weak", 1, 0), (2, "?", 0, 0)])


if __name__ == "__main__":
    unittest.main()
