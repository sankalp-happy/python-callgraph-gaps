"""Callback invocation: the callee's name appears nowhere at the call site.

`self.callback(...)` runs a function stored on the instance, chosen from a
registry by a runtime key. There is no name for a static tool to resolve,
only a slot. Measured in click: 57/65 missed, e.g.
click.core.Parameter.handle_parse_result -> click.decorators.show_help from
`value = self.callback(ctx, self, value)`.

Like 06, this one is RESOLVED at fixture scale: PyCG tracks the function
objects through the registry dict and the attribute assignment. The
expectation was corrected to match the measurement instead of the fixture
being reshaped until it failed. The 57-of-65 miss rate in click is the
claim; this fixture only shows the shape.
"""

META = {
    "construct": "name-absent-callback",
    "title": "Callback held in a slot",
    "blurb": "The called function's name is not at the call site at all.",
    "citation": "click/src/click/core.py -- `value = self.callback(ctx, self, value)`",
    "citation_url": "https://github.com/pallets/click/blob/main/src/click/core.py",
    "expect_missing": [],
    "expect_found": [["fixture.Parameter.process", "fixture.show_help"],
                     ["fixture.Parameter.process", "fixture.show_version"]],
    "outcome": "resolved-in-small",
    "click_evidence": "57/65 missed in click (88%)",
    "is_control": False,
}


def show_help(value):
    return f"help:{value}"


def show_version(value):
    return f"version:{value}"


CALLBACKS = {"help": show_help, "version": show_version}


class Parameter:
    def __init__(self, key):
        self.callback = CALLBACKS[key]

    def process(self, value):
        return self.callback(value)


def main():
    return [Parameter("help").process("x"), Parameter("version").process("y")]
