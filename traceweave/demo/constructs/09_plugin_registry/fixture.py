"""Decorator-built registry, dispatched by string key.

The decorator populates a dict at import time; the call site indexes that
dict with a runtime string. Neither half names the callee. This is the
plugin/DI registration class H2a calls out by name, and the pattern behind
click's own Group.add_command / pytest's plugin manager.
"""

META = {
    "construct": "plugin-registry",
    "title": "Registry populated by decorator",
    "blurb": "Registered at import time, dispatched by string key at call time.",
    "citation": "click/src/click/core.py -- Group.add_command / commands dict",
    "citation_url": "https://github.com/pallets/click/blob/main/src/click/core.py",
    "expect_missing": [["fixture.dispatch", "fixture.deploy"]],
    "is_control": False,
}

COMMANDS = {}


def command(name):
    def register(fn):
        COMMANDS[name] = fn
        return fn
    return register


@command("deploy")
def deploy():
    return "deploying"


def dispatch(name):
    return COMMANDS[name]()


def main():
    return dispatch("deploy")
