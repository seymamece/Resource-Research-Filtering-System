"""Where the catalogue lives on disk.

One file, storage/catalogue.json, holding the four lists the export has: resources, items,
passages and topicHints. Records are stored in the export's own shape, so exporting is
choosing which records go, never translating them.

RRFS_ROOT moves the whole data folder (the tests use it); SITE_DIR names the site project
when it is not next to this one.
"""

import hashlib
import json
import os
from pathlib import Path

from .names import BlockedNames

COLLECTIONS = ("resources", "items", "passages", "topicHints")
PREFIX = {"resources": "r-", "items": "i-", "passages": "p-", "topicHints": "h-"}


def root() -> Path:
    return Path(os.environ.get("RRFS_ROOT") or Path(__file__).resolve().parent.parent)


def catalogue_path() -> Path:
    return root() / "storage" / "catalogue.json"


def blocked_names_path() -> Path:
    return root() / "research" / "blocked-names.json"


def export_path(project: str) -> Path:
    return root() / "exports" / project / "resources.json"


def site_dir() -> Path:
    return Path(os.environ.get("SITE_DIR") or root().parent / "online-curriculum-")


def sources_dir() -> Path:
    """The site's SOURCES_DIR: its catalogue of books and their extracted page texts."""
    return Path(os.environ.get("SOURCES_DIR") or "G:/My Drive/Sources")


def empty() -> dict:
    from .migrate import VERSION
    return {"version": VERSION, **{c: [] for c in COLLECTIONS}}


def load() -> dict:
    path = catalogue_path()
    if not path.exists():
        return empty()
    cat = json.loads(path.read_text(encoding="utf-8"))
    for c in COLLECTIONS:
        cat.setdefault(c, [])
    from .migrate import upgrade
    upgrade(cat)  # an older catalogue is read in today's shape and saved that way
    return cat


def _write_json(path: Path, data: dict):
    # Written beside the target and moved over it, so a crash never leaves half a file.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def save(cat: dict):
    _write_json(catalogue_path(), cat)


def write_export(project: str, doc: dict) -> Path:
    path = export_path(project)
    _write_json(path, doc)
    return path


def load_blocked() -> BlockedNames | None:
    return BlockedNames.load(blocked_names_path())


def make_id(collection: str, *parts: str) -> str:
    """Stable ids: the same URL (or the same place in the same item) always gets the same id."""
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return PREFIX[collection] + digest[:8]


def find(cat: dict, record_id: str) -> tuple[str, dict] | tuple[None, None]:
    for c in COLLECTIONS:
        for record in cat[c]:
            if record.get("id") == record_id:
                return c, record
    return None, None
