#!/usr/bin/env python3
"""`S(r)` -- one static tool's edge set for one repo, in the shape §4.1 compares.

Shared by both baselines on purpose: `recall = |S ∩ R| / |R|` is only meaningful
if the two `S`s are the same kind of object, and the fastest way to lose that
property is to let each extractor invent its own container.

### Why there is no `edge_type` field here

§2.2 assigns edge type from the CALLER'S call site, and §4.1's per-type
breakdown is computed over `R`. So a static tool is never asked what kind of
edge it thinks it found -- it is only asked which (caller, callee) pairs it
believes in. That is what keeps "static misses X% of edges of type T"
non-circular, and it is why the types live in `callsites.py` instead.

### The universe (§2.1)

A pair is in-universe iff both endpoints map to in-repo, statically
representable nodes. Everything else is counted and reported on its own line:
callees in C/builtins, callees in third-party or stdlib code, and names the
tool emitted that correspond to no node in the source at all. Nothing is
dropped silently -- §2.1 calls including C calls "the single easiest way to
accidentally fabricate a headline number", and the mirror of that mistake is
discarding edges without a count.
"""

from __future__ import annotations

from dataclasses import dataclass, field

EXTERNAL_SENTINEL = "<external>"


@dataclass
class StaticEdgeSet:
    baseline: str
    in_universe: set[tuple[str, str]] = field(default_factory=set)
    external: set[tuple[str, str]] = field(default_factory=set)
    dropped: dict[str, int] = field(default_factory=dict)
    # Optional per-edge provenance: which resolver produced it. Only baseline 2
    # populates this (pyright vs. our own AST binding), and it is the number
    # that answers "what did Pyright actually add?".
    provenance: dict[str, int] = field(default_factory=dict)

    def _drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    def note_provenance(self, resolver: str) -> None:
        self.provenance[resolver] = self.provenance.get(resolver, 0) + 1

    def add_in_universe(self, caller: str, callee: str) -> None:
        self.in_universe.add((caller, callee))

    def add_external(self, caller: str, reason: str = "callee_external") -> None:
        self.external.add((caller, EXTERNAL_SENTINEL))
        self._drop(reason)

    def add_unmapped(self, reason: str) -> None:
        self._drop(reason)

    def counts(self) -> dict:
        return {
            "in_universe": len(self.in_universe),
            "callers_with_external_edges": len({a for a, _ in self.external}),
            "dropped": dict(sorted(self.dropped.items())),
            **({"provenance": dict(sorted(self.provenance.items()))} if self.provenance else {}),
        }

    def to_json(self, include_edges: bool = True) -> dict:
        out = {"baseline": self.baseline, "counts": self.counts()}
        if include_edges:
            out["in_universe_edges"] = sorted(f"{a}->{b}" for a, b in self.in_universe)
        return out
