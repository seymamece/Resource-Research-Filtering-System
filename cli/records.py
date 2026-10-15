"""Writing to the catalogue, the same way from the command line and from the screen.

Every change goes through problems_for() before it is saved: the site's rules from model.py
and, for a passage, its quote against the text it says it comes from. There is one set of
rules, and neither door has a way around it.
"""

from . import model, storage, text


def quote_checks(cat: dict, only=None) -> tuple[list, list]:
    """(problems, unchecked) for passage quotes against their item's text."""
    items = {i["id"]: i for i in cat["items"]}
    resources = {r["id"]: r for r in cat["resources"]}
    problems, unchecked = [], []
    for p in cat["passages"]:
        if not p.get("quote") or (only is not None and p["id"] not in only):
            continue
        item = items.get(p.get("itemId"))
        if item is None:
            continue  # reported by the record checks
        found = text.quote_found(item, resources.get(item["resourceId"]), p["quote"], p.get("where"))
        if found is False:
            problems.append((p["id"], "the quote is not in the item's text where it says; "
                                      "copy it exactly"))
        elif found is None:
            unchecked.append(p["id"])
    return problems, unchecked


def problems_for(cat: dict, ids, blocked) -> list[tuple[str, str]]:
    """Everything the site would refuse about these records, quotes included."""
    ids = set(ids)
    found = [(rid, m) for rid, m in model.check(cat, blocked) if rid in ids]
    return found + quote_checks(cat, ids)[0]


def make_passage(item_id: str, where: str, quote: str | None, topics: list, use: str,
                 qref: str | None = None, href: str | None = None) -> dict:
    """A new passage, proposed: only a person moves it on."""
    record = {"id": storage.make_id("passages", item_id, where, quote or ""), "itemId": item_id,
              "where": where}
    if quote:
        record["quote"] = quote
    if qref:
        record["qref"] = qref
    if href:
        record["href"] = href
    record.update({"topics": topics, "use": use, "status": "proposed"})
    return record


def decide(cat: dict, passage_id: str, decision: str, who: str, today: str) -> str:
    """A person accepts or rejects a passage (rule 3: never without a name).
    Returns what was done; raises ValueError if it cannot be."""
    who = (who or "").strip()
    if not who:
        raise ValueError("a decision needs the name of the person making it")
    passage = next((p for p in cat["passages"] if p["id"] == passage_id), None)
    if passage is None:
        raise ValueError(f"no passage {passage_id}")
    if decision == "accept":
        passage["status"] = "accepted"
        passage["acceptedBy"] = {"by": who, "on": today}
        return "accepted"
    if decision == "reject":
        cat["passages"] = [p for p in cat["passages"] if p["id"] != passage_id]
        return "removed"
    if decision == "undo":
        passage["status"] = "proposed"
        passage.pop("acceptedBy", None)
        return "proposed"
    raise ValueError(f"'{decision}' is not accept, reject or undo")
