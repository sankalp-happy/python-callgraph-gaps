"""Caller module -- see pkgfixture/__init__.py."""

import threading

from pkgfixture import beta


def spawned():
    """Runs on a worker thread. Only visible with threading.setprofile."""
    return beta.on_thread()


def run_thread():
    t = threading.Thread(target=spawned)
    t.start()
    t.join()


def main():
    beta.direct()
    run_thread()
