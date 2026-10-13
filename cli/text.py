"""The readable text of a page, kept on this machine so it is read from the web only once.

cache/text/<item id>.md holds the headings and paragraphs of one item, nothing else. It is
the full text of somebody else's work, so it never goes into git (rule 5): what the
catalogue keeps is where a passage is and a quote of 5 to 40 words. The cache is what a
quote is checked against, the way the site checks a draft's quotes against its pages.
"""

import json
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

from . import storage
from .names import normalise

_SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg",
         "button", "iframe", "select", "template", "figure"}
_VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "area", "col", "embed"}
_HEADINGS = {"h1", "h2", "h3", "h4"}
_BLOCKS = {"p", "li", "blockquote"} | _HEADINGS
# A <p> ends where any of these begins, written </p> or not (HTML's own rule; some sites
# never close their paragraphs). The same holds for one <li> and the next.
_CLOSES_P = {"p", "div", "ul", "ol", "dl", "table", "blockquote", "pre", "section", "article",
             "hr", "h1", "h2", "h3", "h4", "h5", "h6"}
_CONTAINERS = {"div", "section", "article", "td", "th", "li", "blockquote", "body", "main"}
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_SPACE = re.compile(r"\s+")


class _Node:
    __slots__ = ("tag", "children", "parent")

    def __init__(self, tag, parent):
        self.tag, self.children, self.parent = tag, [], parent


class _Tree(HTMLParser):
    """Just enough of the DOM: elements and their text, without what is never content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", None)
        self.at = self.root
        self.skipping = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if self.skipping or tag in _SKIP:
            if tag not in _VOID:
                self.skipping += 1
            return
        if tag in _CLOSES_P:
            self._close_open("p", _CONTAINERS)
        elif tag == "li":
            self._close_open("li", {"ul", "ol"})
        if tag in _VOID:
            if tag == "br":
                self.at.children.append("\n")
            return
        node = _Node(tag, self.at)
        self.at.children.append(node)
        self.at = node

    def _close_open(self, tag, stop_at):
        node = self.at
        while node is not self.root and node.tag not in stop_at:
            if node.tag == tag:
                self.at = node.parent
                return
            node = node.parent

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if self.skipping:
            if tag not in _VOID:
                self.skipping -= 1
            return
        node = self.at
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.at = node.parent

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self.skipping:
            self.at.children.append(data)


def _text(node) -> str:
    parts = []
    for child in node.children:
        parts.append(child if isinstance(child, str) else _text(child))
    return "".join(parts)


def _clean(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def _paragraph_weight(node, weights):
    """Each paragraph's length counts for its parent, and half for the grandparent."""
    for child in node.children:
        if isinstance(child, str):
            continue
        if child.tag == "p":
            length = len(_clean(_text(child)))
            if child.parent:
                weights[id(child.parent)] = weights.get(id(child.parent), 0) + length
                if child.parent.parent:
                    gp = id(child.parent.parent)
                    weights[gp] = weights.get(gp, 0) + length / 2
        _paragraph_weight(child, weights)


def _all_nodes(node):
    for child in node.children:
        if not isinstance(child, str):
            yield child
            yield from _all_nodes(child)


def _blocks(node, out):
    for child in node.children:
        if isinstance(child, str):
            # Text sitting straight in a container, as in pages laid out with <br>.
            for line in child.split("\n"):
                if len(_clean(line)) >= 80:
                    out.append(("p", _clean(line)))
            continue
        if child.tag in _HEADINGS:
            text = _clean(_text(child))
            if text:
                out.append(("h", text))
        elif child.tag in _BLOCKS:
            if any(not isinstance(c, str) and c.tag in ("p", "li") for c in _all_nodes(child)):
                _blocks(child, out)  # a quote or list item that holds paragraphs of its own
                continue
            for line in _text(child).split("\n"):
                if _clean(line):
                    out.append(("p", _clean(line)))
        else:
            _blocks(child, out)


def extract(html: str) -> tuple[str, list[tuple[str, str]]]:
    """(page title, [("h", heading) | ("p", paragraph)]) for the page's main text."""
    # A site built with Next.js sends its article as data and draws it with script.
    data = _NEXT_DATA.search(html)
    if data:
        try:
            post = json.loads(data[1])["props"]["pageProps"]["post"]
            if isinstance(post.get("content"), str) and len(post["content"]) > 200:
                _, blocks = extract(post["content"])
                return _clean(post.get("title") or ""), blocks
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
    tree = _Tree()
    tree.feed(html)
    tree.close()
    weights = {}
    _paragraph_weight(tree.root, weights)
    nodes = {id(n): n for n in _all_nodes(tree.root)}
    main = nodes.get(max(weights, key=weights.get)) if weights else tree.root
    blocks = []
    _blocks(main or tree.root, blocks)
    return _clean(tree.title), blocks


# --- the cache -------------------------------------------------------------------------------

def cache_path(item_id: str):
    return storage.root() / "cache" / "text" / f"{item_id}.md"


def write_cache(item: dict, title: str, blocks, fetched: str):
    lines = ["---", f"item: {item['id']}", f"url: {item['url']}", f"fetched: {fetched}",
             f"title: {title}", "---", ""]
    for kind, text in blocks:
        lines += [f"## {text}" if kind == "h" else text, ""]
    path = cache_path(item["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def read_cache(item_id: str) -> list[tuple[str, str]] | None:
    """The item's blocks, or None if it has not been fetched."""
    path = cache_path(item_id)
    if not path.exists():
        return None
    body = path.read_text(encoding="utf-8").split("\n---\n", 1)[-1]
    blocks = []
    for chunk in body.split("\n\n"):
        chunk = chunk.strip()
        if chunk.startswith("## "):
            blocks.append(("h", chunk[3:]))
        elif chunk:
            blocks.append(("p", chunk))
    return blocks


def paragraphs(blocks):
    """(number, heading above it, text) for each paragraph, numbered from 1."""
    heading, n = None, 0
    for kind, text in blocks:
        if kind == "h":
            heading = text
        else:
            n += 1
            yield n, heading, text


def quote_found(item_id: str, quote: str) -> bool | None:
    """Whether the quote is in the item's text, compared as the site compares (case, accents
    and punctuation aside). None when the item has not been fetched yet."""
    blocks = read_cache(item_id)
    if blocks is None:
        return None
    haystack = " " + normalise(" ".join(text for _, text in blocks)) + " "
    return " " + normalise(quote) + " " in haystack


def fetch(url: str, attempts: int = 3) -> tuple[int, str]:
    """(status, html); status 0 when the site could not be reached."""
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept-Language": "en,tr;q=0.8"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.status, response.read().decode(charset, "replace")
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404, 410):
                return e.code, ""
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        import time
        time.sleep(3 + 4 * attempt)
    return 0, ""
