"""CONTROL. A plain, direct function call -- the easiest edge there is.

This fixture is here to be FOUND, not missed. Without it, a wall of red
proves nothing: a pipeline with a naming bug also produces a wall of red.
The control is what separates "PyCG misses dynamic dispatch" from "our
harness cannot match names". In the click measurement its real-world
counterpart is the `bare-call` bucket, where PyCG found 164 of 169 edges.
"""

META = {
    "construct": "bare-call",
    "title": "Direct call (control)",
    "blurb": "A plain top-level call, named at the call site. Nothing dynamic.",
    "citation": "control fixture -- no dynamic construct",
    "citation_url": "",
    "expect_missing": [],
    "is_control": True,
}


def handle():
    return "handled"


def main():
    return handle()
