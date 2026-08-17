"""Live-demo toy fixture: one plugin, dispatched by name through getattr().

Same computed-attribute-name shape as Flask's own app-factory lookup
(flask/src/flask/cli.py, find_best_app(): `getattr(module, attr_name, None)`
tried against a small set of candidate names, then called). PyCG 0.0.8
resolves the getattr() call itself but not which attribute it returns, so
"dispatch -> handle_email" is present at runtime and absent from PyCG's
static call graph -- confirmed by running PyCG directly against this file.
"""


class PluginRegistry:
    def dispatch(self, name):
        handler = getattr(self, f"handle_{name}")
        return handler()

    def handle_email(self):
        return "sent email"


def main():
    registry = PluginRegistry()
    return registry.dispatch("email")


if __name__ == "__main__":
    main()
