"""Dynamic import: the module is named by a runtime string.

Two files, because that is the only honest way to show it -- the imported
module has to actually be a separate module. Same shape as click's own
examples/complex/cli.py (ComplexCLI.get_command builds the module name from
a command string and imports it), and as Django's app-config loading.
"""

import importlib

META = {
    "construct": "dynamic-import",
    "title": "importlib by computed name",
    "blurb": "The module path is assembled from a string, then imported and called.",
    "citation": "click/examples/complex/complex/cli.py -- ComplexCLI.get_command()",
    "citation_url": "https://github.com/pallets/click/blob/main/examples/complex/complex/cli.py",
    "expect_missing": [["fixture.dispatch", "plugins.email.send"]],
    "is_control": False,
}


def dispatch(name):
    module = importlib.import_module(f"plugins.{name}")
    return module.send()


def main():
    return dispatch("email")
