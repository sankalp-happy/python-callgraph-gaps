"""Test-only fixture: exists purely to pin PyCG's qualified-name scheme for a
nested function, which traceweave/demo/fixture.py doesn't have. Not part of
the live demo.
"""


def outer():
    def inner():
        return 1

    return inner()
