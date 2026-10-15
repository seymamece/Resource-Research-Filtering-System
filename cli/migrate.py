"""Bringing an older catalogue up to the shape the site asks for now.

Version 2 (2026-10-15): the site has eight classes instead of fourteen ages.
- A resource lists the classes it suits. They are worked out from its old age range - every
  class whose approximate ages meet it - and the ages stay beside them as a note.
- A passage names its topics by sheet code: {"age": 18, "topic": 5} becomes {"from": "S6-5"}.
Topic hints keep their {age, topic} form: the requirements still show them that way.
"""

from . import curriculum, vocab

VERSION = 2


def upgrade(cat: dict) -> bool:
    """Upgrades in place; True if anything changed."""
    if cat.get("version", 1) >= VERSION:
        return False
    for r in cat.get("resources", []):
        if "classes" not in r:
            r["classes"] = (curriculum.classes_for_ages(r["ages"]) if isinstance(r.get("ages"), dict)
                            else list(vocab.CLASS_IDS))
    for p in cat.get("passages", []):
        p["topics"] = [curriculum.entry(curriculum.key_of(t)) for t in p.get("topics", [])]
    cat["version"] = VERSION
    return True
