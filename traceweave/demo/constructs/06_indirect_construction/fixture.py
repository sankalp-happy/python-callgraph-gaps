"""Indirect construction: the class comes out of a lookup table.

Measured in click: 39/47 missed, e.g. click.decorators.option.decorator ->
click.core.Option.__init__ from `_param_memo(f, cls(param_decls, **attrs))`
at src/click/decorators.py:374 -- `cls` is a parameter, not a literal name.

This fixture was originally written expecting PyCG to miss it. It does not:
PyCG reads the dict literal and resolves BOTH classes, even chosen by a
runtime key. The expectation was wrong and has been corrected rather than
the fixture made harder until it failed -- a fixture tuned until it breaks
measures the tuning, not the tool.

So the honest result is a contrast, and it is the more useful one: this
construct is resolvable in twenty lines and missed 39 times out of 47 in
click. What defeats the analysis is not the syntax but the scale it has to
resolve it at. Any fixture-only benchmark -- including this page's -- will
therefore understate the problem, which is why the click measurement, not
this grid, carries the claim.
"""

META = {
    "construct": "indirect-construction",
    "title": "Construction through a lookup table",
    "blurb": "The class is chosen from a dict by a runtime key.",
    "citation": "click/src/click/decorators.py:374 -- `_param_memo(f, cls(param_decls, **attrs))`",
    "citation_url": "https://github.com/pallets/click/blob/main/src/click/decorators.py",
    "expect_missing": [],
    "expect_found": [["fixture.make", "fixture.Option.__init__"],
                     ["fixture.make", "fixture.Argument.__init__"]],
    "outcome": "resolved-in-small",
    "click_evidence": "39/47 missed in click (83%)",
    "is_control": False,
}


class Option:
    def __init__(self, decls):
        self.decls = decls


class Argument:
    def __init__(self, decls):
        self.decls = decls


PARAM_TYPES = {"option": Option, "argument": Argument}


def make(kind, decls):
    cls = PARAM_TYPES[kind]
    return cls(decls)


def main():
    return [make("option", ["--verbose"]), make("argument", ["src"])]
