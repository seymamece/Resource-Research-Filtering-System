"""Blocked names (rule 2): no school or institution name in anything the site shows.

The list itself never comes here. The site keeps a fingerprint of each name in
research/blocked-names.json, and this module reads that file in the site's own format and
compares texts the way the site does (src/lib/names.ts and normalise() in src/lib/extract.ts).
If the two drifted apart, a name this system passed would be refused by the site, or worse,
one the site would catch could slip through here first.
"""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

_LETTER = r"[^\W\d_]"
_HYPHEN_BREAK = re.compile(rf"({_LETTER})-\s+({_LETTER})")
_NOT_LETTER_OR_NUMBER = re.compile(r"[\W_]+")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def normalise(text: str) -> str:
    """The form texts are compared in: case, accents and punctuation do not matter."""
    # A word broken across a line ("institu- tion") is joined, but only before a lower-case letter.
    text = _HYPHEN_BREAK.sub(lambda m: m[1] + m[2] if m[2].islower() else m[0], text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.category(c).startswith("M"))
    text = text.lower().replace("ı", "i")
    return _NOT_LETTER_OR_NUMBER.sub(" ", text).strip()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class BlockedNames:
    def __init__(self, data: dict):
        names = data.get("names") if isinstance(data, dict) else None
        if not isinstance(names, list) or data.get("version") != 1:
            raise ValueError("not a blocked-names file: expected {\"version\": 1, \"names\": [...]}")
        for name in names:
            if not (isinstance(name.get("words"), int) and name["words"] >= 1
                    and isinstance(name.get("sha256"), str) and _SHA256.match(name["sha256"])):
                raise ValueError(f"not a fingerprint: {name!r}")
        self.count = len(names)
        self._wanted = {name["sha256"] for name in names}
        self._lengths = sorted({name["words"] for name in names})

    @classmethod
    def load(cls, path: Path) -> "BlockedNames | None":
        if not path.exists():
            return None
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def found_in(self, text: str) -> list[str]:
        """The blocked names in a text, in their normalised form."""
        words = [w for w in normalise(text).split(" ") if w]
        found = []
        for length in self._lengths:
            for i in range(len(words) - length + 1):
                phrase = " ".join(words[i:i + length])
                if _sha(phrase) in self._wanted:
                    found.append(phrase)
        return found
