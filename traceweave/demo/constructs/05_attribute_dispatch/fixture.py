"""Attribute dispatch: `item.method()` where item's concrete type is unknown.

The name is at the call site, but which implementation runs depends on what
the list happens to hold. Measured in click: 112/121 missed, e.g.
click.core.Command.make_parser -> click.core.Argument.add_to_parser from
`param.add_to_parser(parser, ctx)`.
"""

META = {
    "construct": "attribute-dispatch",
    "title": "Call on an unresolved receiver",
    "blurb": "The method name is visible; the receiver's type is not.",
    "citation": "click/src/click/core.py -- `param.add_to_parser(parser, ctx)`",
    "citation_url": "https://github.com/pallets/click/blob/main/src/click/core.py",
    "expect_missing": [["fixture.build", "fixture.Argument.add_to_parser"],
                       ["fixture.build", "fixture.Option.add_to_parser"]],
    "is_control": False,
}


class Argument:
    def add_to_parser(self, parser):
        parser.append("arg")


class Option:
    def add_to_parser(self, parser):
        parser.append("opt")


def build(params):
    parser = []
    for param in params:
        param.add_to_parser(parser)
    return parser


def main():
    return build([Argument(), Option()])
