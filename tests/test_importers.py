"""The spreadsheet importers, on small workbooks made here: py -m unittest"""

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import PatternFill

from cli import importers, model, storage

YELLOW = PatternFill(fill_type="solid", fgColor="00FFF2CC")


def site(rid, url, ages=(13, 18)):
    return {"id": rid, "kind": "website", "title": "A site", "url": url, "languages": ["en"],
            "ages": {"min": ages[0], "max": ages[1]}, "strands": [], "lenses": [],
            "role": "religious", "rights": "pending", "status": "to_verify",
            "retrieved": "2026-10-13"}


class TopicSheetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "topics.xlsx"
        wb = Workbook()
        wb.remove(wb.active)
        rows = {
            "S4 (Age 17-18)": [
                (1, "Introduction", "Said Nursi, The Words – The First Word (Bismillah) (risaleinur.com)",
                 "https://risaleinur.com/risale-i-nur-collection/75-words/3655-01.html", False),
            ],
            "S6 (Age 18-19)": [
                (5, "The Heart and Mind Connection",
                 "Gülen, Emerald Hills of the Heart (Key Concepts in Sufism) – 'Aql (Reason) (fgulen.com)",
                 "https://fgulen.com/en/fethullah-gulens-works/key-concepts-in-the-practice-of-sufism-3/reason", False),
                (6, "Patience", "Related reading: Gülen, Emerald Hills of the Heart (Key Concepts in Sufism) – Sabr (fgulen.com)",
                 "https://fgulen.com/en/fethullah-gulens-works/key-concepts-in-the-practice-of-sufism-1/sabr", True),
                (7, "Same chapter again", "Said Nursi, The Words – The First Word (Bismillah) (risaleinur.com)",
                 "https://risaleinur.com/risale-i-nur-collection/75-words/3655-01.html", False),
                (8, "Elsewhere", "Green Dome Foundation – A Story (greendome.org)",
                 "https://greendome.org/a-story/", False),
            ],
        }
        for title, entries in rows.items():
            ws = wb.create_sheet(title)
            ws.append(["Week", "Topic", "Source"])
            for week, topic, source, url, related in entries:
                ws.append([week, topic, source])
                cell = ws.cell(row=ws.max_row, column=3)
                cell.hyperlink = url
                if related:
                    cell.fill = YELLOW
            ws.append([None, "Click a source to open it.", None])
        wb.save(self.path)
        self.cat = storage.empty()
        self.cat["resources"] = [site("r-fg", "https://www.fgulen.com/en/"),
                                 site("r-rn", "https://risaleinur.com/risale-i-nur-collection.html")]

    def tearDown(self):
        self.tmp.cleanup()

    def run_import(self):
        return importers.import_topics(self.cat, importers.topic_rows(str(self.path)), "2026-10-13")

    def test_series_map_to_the_sites_ages(self):
        ages = sorted({r["age"] for r in importers.topic_rows(str(self.path))})
        self.assertEqual(ages, [16, 18])  # S4 is labelled 17-18 but is age 16

    def test_a_hint_names_the_book_not_the_author_publisher_or_site(self):
        self.run_import()
        hints = {(h["age"], h["topic"]): h for h in self.cat["topicHints"]}
        self.assertEqual(hints[(18, 5)]["hint"], "Emerald Hills of the Heart (Key Concepts in Sufism) – 'Aql (Reason)")
        self.assertEqual(hints[(18, 5)]["fromSheet"], "S6 week 5")
        self.assertEqual(hints[(18, 8)]["hint"], "A Story")
        self.assertEqual(hints[(18, 6)]["hint"],
                         "Emerald Hills of the Heart (Key Concepts in Sufism) – Sabr (related reading)")

    def test_only_a_catalogued_volume_gets_its_catalogue_id(self):
        self.run_import()
        ids = {h["topic"]: h["catalogueId"] for h in self.cat["topicHints"] if h["age"] == 18}
        self.assertIsNone(ids[5])            # volume 3 is not in the site's catalogue
        self.assertEqual(ids[6], "s-6b15280cee")

    def test_pages_become_items_of_their_site_and_widen_across_ages(self):
        changed, _, skipped = self.run_import()
        by_url = {i["url"]: i for i in self.cat["items"]}
        words = by_url["https://risaleinur.com/risale-i-nur-collection/75-words/3655-01.html"]
        self.assertEqual((words["resourceId"], words["kind"], words["ages"]),
                         ("r-rn", "chapter", {"min": 16, "max": 18}))
        self.assertEqual(by_url["https://fgulen.com/en/fethullah-gulens-works/key-concepts-in-the-practice-of-sufism-3/reason"]["resourceId"], "r-fg")
        self.assertEqual(skipped, ["S6 week 8: no resource for greendome.org yet"])
        self.assertEqual(model.check(self.cat), [])

    def test_running_it_again_changes_nothing(self):
        self.run_import()
        changed, _, _ = self.run_import()
        self.assertEqual(changed, [])
        self.assertEqual(len(self.cat["topicHints"]), 5)


if __name__ == "__main__":
    unittest.main()
