"""The site's shared vocabulary (ONLINE-CURRICULUM-REQUIREMENTS.md section 3).

These are the site's ids, spelled exactly as the site spells them. Nothing here is ours to
rename: the site's import rejects the whole export if one value is off.
"""

AGE_MIN, AGE_MAX = 5, 18
TOPICS_PER_AGE = 36

# The site's eight classes (section 3.1, changed 2026-10-15) and their approximate ages. A
# secondary level is chosen by the leader for the group, not by age, so the ages are a guide.
CLASSES = (
    ("lower-primary", "Lower Primary", 5, 8),
    ("upper-primary", "Upper Primary", 9, 12),
    ("lower-secondary-beginner", "Lower Secondary · Beginner", 13, 15),
    ("lower-secondary-middle", "Lower Secondary · Middle", 13, 15),
    ("lower-secondary-advanced", "Lower Secondary · Advanced", 13, 15),
    ("upper-secondary-beginner", "Upper Secondary · Beginner", 16, 18),
    ("upper-secondary-middle", "Upper Secondary · Middle", 16, 18),
    ("upper-secondary-advanced", "Upper Secondary · Advanced", 16, 18),
)
CLASS_IDS = tuple(c[0] for c in CLASSES)
PRIMARY_CLASSES = ("lower-primary", "upper-primary")

# The owner's sheets, which name every secondary topic ("S6-5"), and the site's old ages.
SHEETS = {"S1": 13, "S2": 14, "S3": 15, "S4": 16, "S5": 17, "S6": 18}

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
