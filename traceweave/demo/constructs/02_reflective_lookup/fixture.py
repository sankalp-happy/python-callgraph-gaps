"""Reflective dispatch: the method name is computed, then looked up.

Same shape as Flask's own app-factory lookup (flask/src/flask/cli.py,
find_best_app): `getattr(module, attr_name, None)` against candidate names,
then called. PyCG resolves the getattr() call itself but not which attribute
it returns.
"""

META = {
    "construct": "reflective-lookup",
    "title": "getattr dispatch",
    "blurb": "The callee's name is built at runtime, so it appears nowhere in the source.",
    "citation": "flask/src/flask/cli.py -- find_best_app()",
    "citation_url": "https://github.com/pallets/flask/blob/main/src/flask/cli.py",
    "expect_missing": [["fixture.PluginRegistry.dispatch",
                        "fixture.PluginRegistry.handle_email"]],
    "is_control": False,
}


class PluginRegistry:
    def dispatch(self, name):
        handler = getattr(self, f"handle_{name}")
        return handler()

    def handle_email(self):
        return "sent email"


def main():
    return PluginRegistry().dispatch("email")
