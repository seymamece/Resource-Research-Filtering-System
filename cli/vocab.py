"""The site's shared vocabulary (ONLINE-CURRICULUM-REQUIREMENTS.md section 3).

These are the site's ids, spelled exactly as the site spells them. Nothing here is ours to
rename: the site's import rejects the whole export if one value is off.
"""

AGE_MIN, AGE_MAX = 5, 18
TOPICS_PER_AGE = 36

STRANDS = ("akaid", "quran", "siyer", "prophets", "ilmihal", "ahlak")
LENSES = ("nature", "science", "daily-life", "technology", "history",
          "companions-scholars", "hadith-sunnah")
ROLES = ("religious", "religious-supporting", "method", "planning")
RIGHTS = ("pending", "cleared", "restricted")
LANGUAGES = ("en", "tr", "sw", "lg", "ar")

RESOURCE_KINDS = ("website", "channel", "book", "app", "course")
ITEM_KINDS = ("article", "video", "chapter", "lesson-plan", "activity", "worksheet")
USES = ("faith", "story", "example", "activity", "science", "definition")
VIDEO_CONTENT = ("faces", "music", "animation", "talk", "nasheed", "drawn-prophet")

# A tool may set the first of each; only a person moves a record past it (rule 3).
RESOURCE_STATUSES = ("to_verify", "verified", "archived")
PASSAGE_STATUSES = ("proposed", "accepted")

# Everything except a book lives on the web, so it needs a working URL and a retrieved date.
WEB_RESOURCE_KINDS = ("website", "channel", "app", "course")
