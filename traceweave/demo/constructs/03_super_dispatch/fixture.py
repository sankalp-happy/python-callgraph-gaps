"""super() dispatch: the callee is chosen by the MRO, not by name.

Measured in click: every one of the 38 super() call edges the test suite
exercised was absent from PyCG's graph (100%), including
click.core.Option.__init__ -> click.core.Parameter.__init__ at
src/click/core.py:2968.
"""

META = {
    "construct": "super-dispatch",
    "title": "super() call",
    "blurb": "Resolved through the MRO at runtime; the callee is never named.",
    "citation": "click/src/click/core.py:2968 -- Option.__init__ calls super().__init__",
    "citation_url": "https://github.com/pallets/click/blob/main/src/click/core.py",
    "expect_missing": [["fixture.Option.__init__", "fixture.Parameter.__init__"]],
    "is_control": False,
}


class Parameter:
    def __init__(self, name):
        self.name = name


class Option(Parameter):
    def __init__(self, name):
        super().__init__(name)


def main():
    return Option("--verbose").name
