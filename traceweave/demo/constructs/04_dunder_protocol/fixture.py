"""Protocol dispatch: `with obj:` calls __enter__/__exit__ with no call site.

The method names never appear in the source -- the interpreter invokes them
for the `with` statement. Measured in click: 38/38 of these edges missed,
e.g. click.core.Context.__enter__ reached from `with self as rv:`.
"""

META = {
    "construct": "dunder-protocol",
    "title": "with-statement protocol",
    "blurb": "The interpreter calls __enter__/__exit__; no call site names them.",
    "citation": "click/src/click/core.py -- `with self.make_context(...) as ctx:`",
    "citation_url": "https://github.com/pallets/click/blob/main/src/click/core.py",
    "expect_missing": [["fixture.main", "fixture.Context.__enter__"],
                       ["fixture.main", "fixture.Context.__exit__"]],
    "is_control": False,
}


class Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def main():
    with Context() as ctx:
        return ctx
