import pytest
def test_add(monkeypatch):
    obj = object()
    for n in ("a","b","c","d","e"):
        getattr(obj, n, None)
