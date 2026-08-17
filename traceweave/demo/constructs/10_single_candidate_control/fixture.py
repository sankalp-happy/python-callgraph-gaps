"""CONTROL PAIR for 06_indirect_construction: the same construct, one candidate.

Byte-for-byte the same shape as 06 -- a class passed as a value and called
to construct -- except that exactly one class in the file could be the
target. PyCG resolves this one. It misses 06.

The pair is the point. Reporting only the version that fails would let a
reader conclude the tool cannot do indirect construction at all, which is
false. What is true, and what the click measurement shows at scale, is that
resolution degrades as the number of candidate targets grows -- so a
benchmark built from single-candidate fixtures measures the easy case and
reports it as the general one.
"""

META = {
    "construct": "single-candidate-control",
    "title": "Indirect construction, one candidate (control)",
    "blurb": "The same construct as the lookup-table case, but only one class it could be. PyCG resolves it.",
    "citation": "control pair for 06_indirect_construction",
    "citation_url": "",
    "expect_missing": [],
    "is_control": True,
}


class Option:
    def __init__(self, decls):
        self.decls = decls


def make(cls, decls):
    return cls(decls)


def main():
    return make(Option, ["--verbose"]).decls
