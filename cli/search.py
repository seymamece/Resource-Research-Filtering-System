"""Which paragraphs to read for a topic, so nobody reads a whole chapter to find three lines.

BM25 over the cached paragraphs, the same kind of word match the site's draft:context uses.
A word match is only a pointer: it narrows what a person or a model reads, and choosing the
passage stays theirs.
"""

import math
from collections import Counter

from . import text
from .names import normalise

_STOP = set("""a an and are as at be been but by for from has have he her his i in is it its
of on or our so than that the their them then there these they this to was we were what when
which who will with you your not no do does how into about can all one may more must
very also only own its upon them him she ve bir ve ile da de bu su o icin gibi""".split())


def words(s: str) -> list[str]:
    return [w for w in normalise(s).split() if len(w) > 2 and w not in _STOP]


class Index:
    def __init__(self, docs):
        """docs: [(key, text)]"""
        self.keys, self.tf, self.lengths = [], [], []
        df = Counter()
        for key, body in docs:
            terms = Counter(words(body))
            self.keys.append(key)
            self.tf.append(terms)
            self.lengths.append(sum(terms.values()))
            df.update(terms.keys())
        n = len(self.keys) or 1
        self.avg = (sum(self.lengths) / n) or 1
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def rank(self, query: str, k1=1.2, b=0.75):
        terms = set(words(query))
        scored = []
        for key, tf, length in zip(self.keys, self.tf, self.lengths):
            score = 0.0
            for t in terms:
                f = tf.get(t)
                if f:
                    score += self.idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * length / self.avg))
            if score > 0:
                scored.append((score, key))
        scored.sort(key=lambda s: -s[0])
        return scored


def readable_units(items, resources: dict):
    """(item, where, heading, text) for every unit of every item that has text: paragraphs
    of fetched pages, pages of catalogued books."""
    for item in items:
        for where, heading, body in text.units(item, resources.get(item["resourceId"])) or []:
            if len(body.split()) >= 8:  # footnotes and headings-as-paragraphs say little
                yield item, where, heading, body
