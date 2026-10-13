"""The catalogue's rules, run against a throwaway data folder: py -m unittest"""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from click.testing import CliRunner

from cli import model
from cli.names import BlockedNames, normalise
from cli.resource_cli import cli

# A made-up institution, fingerprinted the way the site does it.
BLOCKED_NAME = "Example Academy"


def fingerprint(name):
    plain = normalise(name)
    return {"words": len(plain.split(" ")), "sha256": hashlib.sha256(plain.encode()).hexdigest()}


class CatalogueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {"RRFS_ROOT": str(self.root), "SITE_DIR": str(self.root / "no-site")}
        names = self.root / "research" / "blocked-names.json"
        names.parent.mkdir(parents=True)
        names.write_text(json.dumps({"version": 1, "names": [fingerprint(BLOCKED_NAME)]}))
        self.runner = CliRunner()
        self.ok("init")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return self.runner.invoke(cli, list(args), env=self.env)

    def ok(self, *args):
        result = self.run_cli(*args)
        self.assertEqual(result.exit_code, 0, result.output)
        return result.output

    def refused(self, *args):
        result = self.run_cli(*args)
        self.assertNotEqual(result.exit_code, 0, result.output)
        return result.output

    def catalogue(self):
        return json.loads((self.root / "storage" / "catalogue.json").read_text(encoding="utf-8"))

    def add_site(self, url="https://example.org/teens", **extra):
        args = ["add", "resource", "-t", "Teen articles (English)", "-k", "website", "-u", url,
                "-l", "en", "-a", "15-18", "-s", "ahlak", "--lenses", "science,daily-life",
                "-r", "method"]
        for key, value in extra.items():
            args += [f"--{key.replace('_', '-')}", value]
        out = self.ok(*args)
        return out.split()[-1]

    def add_article(self, rid):
        out = self.ok("add", "item", "-R", rid, "-k", "article", "-t", "Emotions and thinking",
                      "-u", "https://example.org/teens/emotions")
        return out.split()[-1]

    # --- adding --------------------------------------------------------------------------------

    def test_a_resource_is_added_as_to_verify_with_a_stable_id(self):
        rid = self.add_site()
        record = self.catalogue()["resources"][0]
        self.assertEqual(record["status"], "to_verify")
        self.assertTrue(rid.startswith("r-"))
        self.assertIn("already exists", self.refused(
            "add", "resource", "-t", "Again", "-k", "website", "-u", "https://example.org/teens",
            "-l", "en", "-a", "15-18", "-r", "method"))

    def test_a_web_resource_needs_a_url(self):
        out = self.refused("add", "resource", "-t", "No link", "-k", "website", "-l", "en",
                           "-a", "15-18", "-r", "method")
        self.assertIn("'url' is required", out)
        self.assertEqual(self.catalogue()["resources"], [])

    def test_wrong_vocabulary_is_refused(self):
        self.assertIn("'languages' has 'de'", self.refused(
            "add", "resource", "-t", "T", "-k", "website", "-u", "https://a.org", "-l", "de",
            "-a", "15-18", "-r", "method"))
        self.assertIn("not a range", self.refused(
            "add", "resource", "-t", "T", "-k", "website", "-u", "https://a.org", "-l", "en",
            "-a", "4-19", "-r", "method"))
        self.assertIn("'strands' has 'character'", self.refused(
            "add", "resource", "-t", "T", "-k", "website", "-u", "https://a.org", "-l", "en",
            "-a", "15-18", "-s", "character", "-r", "method"))

    def test_a_blocked_name_is_refused_in_a_title_but_kept_in_private_name(self):
        out = self.refused("add", "resource", "-t", "Example  ACADEMY's workshop", "-k", "website",
                           "-u", "https://a.org", "-l", "en", "-a", "15-18", "-r", "method")
        self.assertIn("blocked name", out)
        self.add_site(private_name=BLOCKED_NAME)
        self.assertEqual(self.catalogue()["resources"][0]["privateName"], BLOCKED_NAME)

    def test_an_item_inherits_and_may_only_narrow(self):
        rid = self.add_site()
        iid = self.add_article(rid)
        item = self.catalogue()["items"][0]
        self.assertEqual((item["id"], item["ages"], item["languages"]), (iid, {"min": 15, "max": 18}, ["en"]))
        self.assertIn("outside the resource", self.refused(
            "add", "item", "-R", rid, "-k", "article", "-t", "Kids", "-u", "https://example.org/k",
            "-a", "8-10"))

    def test_a_video_gets_its_youtube_id_and_a_drawn_prophet_is_never_exported(self):
        rid = self.ok("add", "resource", "-t", "Stories channel (English)", "-k", "channel",
                      "-u", "https://www.youtube.com/@x", "-l", "en", "-a", "8-12",
                      "-r", "religious-supporting", "--rights", "cleared").split()[-1]
        vid = self.ok("add", "item", "-R", rid, "-k", "video", "-t", "A story",
                      "-u", "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3", "--minutes", "12",
                      "--content", "animation,drawn-prophet").split()[-1]
        item = self.catalogue()["items"][0]
        self.assertEqual((item["youtubeId"], item["minutes"]), ("dQw4w9WgXcQ", 12))
        out = self.ok("export")
        self.assertIn(f"left out {vid}: shows a drawn prophet", out)

    # --- passages and the order of authority ----------------------------------------------------

    def test_a_quote_is_5_to_40_words(self):
        iid = self.add_article(self.add_site())
        self.assertIn("has 3 words", self.refused(
            "add", "passage", "-I", iid, "-w", "section 'Two systems'", "-q", "too short here",
            "-T", "18:5", "--use", "science"))
        pid = self.ok("add", "passage", "-I", iid, "-w", "section 'Two systems'",
                      "-q", "Feelings and reasoning work together when we decide",
                      "-T", "18:5", "--use", "science").split()[-1]
        self.assertEqual(self.catalogue()["passages"][0]["status"], "proposed")
        self.assertIn(pid, self.ok("filter", "passages", "-T", "18:5"))

    def test_a_method_resource_is_never_the_basis_for_faith(self):
        iid = self.add_article(self.add_site())
        self.assertIn("never the basis for a statement of faith", self.refused(
            "add", "passage", "-I", iid, "-w", "p. 3", "-q", "one two three four five six",
            "-T", "18:5", "--use", "faith"))

    def test_a_faith_statement_from_a_supporting_resource_carries_its_reference(self):
        rid = self.add_site(url="https://example.org/stories")
        self.ok("set", rid, "role=religious-supporting")
        iid = self.add_article(rid)
        args = ["add", "passage", "-I", iid, "-w", "p. 3", "-q", "one two three four five six",
                "-T", "18:5", "--use", "faith"]
        self.assertIn("must carry the qref or href", self.refused(*args))
        self.ok(*args, "--qref", "2:286")

    def test_a_video_passage_is_placed_by_time(self):
        rid = self.add_site(url="https://www.youtube.com/@y")
        vid = self.ok("add", "item", "-R", rid, "-k", "video", "-t", "Talk",
                      "-u", "https://youtu.be/dQw4w9WgXcQ").split()[-1]
        self.assertIn("mm:ss", self.refused("add", "passage", "-I", vid, "-w", "page 4",
                                            "-T", "18:5", "--use", "example"))
        self.ok("add", "passage", "-I", vid, "-w", "03:10-04:05", "-T", "18:5", "--use", "example")

    # --- only a person verifies ----------------------------------------------------------------

    def test_verified_and_accepted_cannot_be_set_directly(self):
        rid = self.add_site()
        self.assertIn("only a person", self.refused("set", rid, "status=verified"))
        self.assertIn("only a person", self.refused("set", rid, 'verifiedBy={"by":"x"}'))
        self.ok("verify", rid, "--by", "Ayse")
        record = self.catalogue()["resources"][0]
        self.assertEqual((record["status"], record["verifiedBy"]["by"]), ("verified", "Ayse"))
        self.ok("set", rid, "status=to_verify")
        self.assertNotIn("verifiedBy", self.catalogue()["resources"][0])

    def test_a_hand_edited_verified_without_a_person_fails_validation(self):
        rid = self.add_site()
        cat = self.catalogue()
        cat["resources"][0]["status"] = "verified"
        (self.root / "storage" / "catalogue.json").write_text(json.dumps(cat))
        self.assertIn(f"{rid}: 'verified' is set by a person", self.refused("validate"))
        self.assertIn("Nothing exported", self.refused("export"))
        self.assertFalse((self.root / "exports" / "online-curriculum" / "resources.json").exists())

    # --- correcting and removing ---------------------------------------------------------------

    def test_set_unset_and_remove(self):
        rid = self.add_site(notes="Short articles")
        self.ok("set", rid, "ages=16-18", "lenses=science", "priority=2")
        record = self.catalogue()["resources"][0]
        self.assertEqual((record["ages"], record["lenses"], record["priority"]),
                         ({"min": 16, "max": 18}, ["science"], 2))
        self.ok("unset", rid, "notes", "priority")
        self.assertIn("'role' is required", self.refused("unset", rid, "role"))
        iid = self.add_article(rid)
        self.assertIn(iid, self.refused("remove", rid))
        self.ok("remove", rid, "--with-children")
        self.assertEqual(self.catalogue()["items"], [])

    # --- filtering and exporting ---------------------------------------------------------------

    def test_filter_by_age_language_and_role(self):
        self.add_site()
        self.ok("add", "resource", "-t", "Kids workshop (Turkish)", "-k", "course",
                "-u", "https://example.org/kids", "-l", "tr", "-a", "7-10", "-r", "method")
        self.assertIn("Kids workshop", self.ok("filter", "-a", "8", "-l", "tr"))
        self.assertIn("No resources match", self.ok("filter", "-a", "8", "-l", "en"))
        self.assertIn("2 resources", self.ok("filter", "-r", "method"))

    def test_export_leaves_out_restricted_and_archived_and_strips_hint_ids(self):
        kept = self.add_site(rights="cleared")
        self.add_site(url="https://pirate.example/book", rights="restricted")
        archived = self.add_site(url="https://example.org/old")
        self.ok("set", archived, "status=archived")
        self.ok("add", "hint", "--age", "18", "--topic", "5", "--from-sheet", "S6 week 5",
                "--hint", "Key Concepts in the Practice of Sufism, the chapter on reason")
        out = self.ok("export")
        self.assertIn("rights are restricted", out)
        self.assertIn(f"left out {archived}: archived", out)
        doc = json.loads((self.root / "exports" / "online-curriculum" / "resources.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual([r["id"] for r in doc["resources"]], [kept])
        self.assertEqual(doc["topicHints"], [{"age": 18, "topic": 5, "fromSheet": "S6 week 5",
                                              "hint": "Key Concepts in the Practice of Sufism, "
                                                      "the chapter on reason",
                                              "catalogueId": None}])
        self.assertIn("id", self.catalogue()["topicHints"][0])

    def test_a_url_that_names_an_institution_stays_here_and_is_left_out_of_the_export(self):
        kept = self.add_site()
        named = self.add_site(url="https://example-academy.org/lessons")
        iid = self.ok("add", "item", "-R", named, "-k", "article", "-t", "A lesson",
                      "-u", "https://example-academy.org/lessons/1").split()[-1]
        self.ok("validate")
        out = self.ok("export")
        self.assertIn(f"left out {named}: its url carries a blocked name", out)
        self.assertIn(f"left out {iid}: its resource is left out", out)
        doc = json.loads((self.root / "exports" / "online-curriculum" / "resources.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual([r["id"] for r in doc["resources"]], [kept])
        self.assertNotIn("academy", json.dumps(doc).lower())

    def test_export_refuses_without_the_blocked_names(self):
        self.add_site()
        (self.root / "research" / "blocked-names.json").unlink()
        self.assertIn("blocked-names.json is missing", self.refused("export"))


class NamesTest(unittest.TestCase):
    def test_multi_word_names_are_found_across_case_accents_and_punctuation(self):
        blocked = BlockedNames({"version": 1, "names": [fingerprint("Işık Bilim Akademisi")]})
        self.assertEqual(blocked.found_in("Visit ISIK bilim-AKADEMİSİ today"), ["isik bilim akademisi"])
        self.assertEqual(blocked.found_in("Bilim and Akademisi apart"), [])

    def test_a_file_in_the_old_format_is_refused(self):
        with self.assertRaises(ValueError):
            BlockedNames({"blocked_hashes": []})


if __name__ == "__main__":
    unittest.main()
