import { describe, expect, it } from "vitest";
import {
  barPct,
  constructLabel,
  edgeKey,
  moduleEdges,
  moduleOf,
  replayOrder,
  shortLabel,
  type RuntimeEdgeFull,
} from "@/lib/realDemo";

const MODULES = ["click", "click.core", "click.types", "click.shell_completion"];

const edge = (
  caller: string,
  callee: string,
  ts: number,
  module = "click.core",
): RuntimeEdgeFull => ({
  caller,
  callee,
  ts,
  module,
  call_module: module,
  call_line: 1,
  def_line: 1,
});

describe("moduleOf", () => {
  it("picks the LONGEST matching module, not the first", () => {
    // `click` also prefixes `click.core.Command.invoke`; taking the first
    // match would file every function under the top-level package.
    expect(moduleOf("click.core.Command.invoke", MODULES)).toBe("click.core");
  });

  it("does not invent a module from the last dot", () => {
    // The naive `everything before the last dot` gives `click.core.Command`,
    // which is a class, not a module, and would split one module into many.
    expect(moduleOf("click.core.Command.invoke", MODULES)).not.toBe("click.core.Command");
  });

  it("maps a package-level function to the package itself", () => {
    expect(moduleOf("click.__getattr__", MODULES)).toBe("click");
  });

  it("does not treat a prefix that is not a dot boundary as a match", () => {
    // `click.types` must not swallow `click.typesetting.x`.
    expect(moduleOf("click.typesetting.x", [...MODULES, "click.typesetting"])).toBe(
      "click.typesetting",
    );
  });

  it("falls back without throwing on an unknown module", () => {
    expect(moduleOf("foo.bar.baz", MODULES)).toBe("foo.bar");
  });
});

describe("shortLabel", () => {
  it("strips the module prefix", () => {
    expect(shortLabel("click.core.Command.invoke", MODULES)).toBe("Command.invoke");
  });

  it("keeps the whole name when the node IS the module", () => {
    expect(shortLabel("click", MODULES)).toBe("click");
  });
});

describe("moduleEdges", () => {
  const edges = [
    edge("click.core.a", "click.types.b", 1),
    edge("click.core.c", "click.types.d", 2),
    edge("click.core.e", "click.core.f", 3),
  ];
  const missing = new Set([edgeKey(edges[0])]);

  it("aggregates function edges into one arc per module pair", () => {
    const arcs = moduleEdges(edges, missing, MODULES);
    expect(arcs).toHaveLength(1);
    expect(arcs[0]).toMatchObject({
      source: "click.core",
      target: "click.types",
      total: 2,
      missing: 1,
    });
  });

  it("drops within-module edges rather than drawing self-loops", () => {
    const arcs = moduleEdges(edges, missing, MODULES);
    expect(arcs.some((a) => a.source === a.target)).toBe(false);
  });

  it("counts nothing as missing when the missing set is empty", () => {
    expect(moduleEdges(edges, new Set(), MODULES)[0].missing).toBe(0);
  });
});

describe("replayOrder", () => {
  it("orders by first-observed timestamp", () => {
    const out = replayOrder([edge("a", "c", 5), edge("a", "b", 1)]);
    expect(out.map((e) => e.callee)).toEqual(["b", "c"]);
  });

  it("is stable for equal timestamps", () => {
    // time.time() is coarser than the gap between consecutive calls, so ties
    // are common; an unstable sort would reshuffle the replay every render.
    const input = [edge("a", "x", 1), edge("a", "y", 1), edge("a", "z", 1)];
    expect(replayOrder(input).map((e) => e.callee)).toEqual(["x", "y", "z"]);
    expect(replayOrder(replayOrder(input)).map((e) => e.callee)).toEqual(["x", "y", "z"]);
  });

  it("does not mutate its input", () => {
    const input = [edge("a", "c", 5), edge("a", "b", 1)];
    replayOrder(input);
    expect(input.map((e) => e.callee)).toEqual(["c", "b"]);
  });
});

describe("barPct", () => {
  it("keeps a nonzero value visible", () => {
    expect(barPct(1, 10000)).toBeGreaterThanOrEqual(1.5);
  });

  it("renders exact zero as zero width", () => {
    expect(barPct(0, 100)).toBe(0);
  });

  it("returns 0 rather than NaN or Infinity when max is 0", () => {
    expect(barPct(0, 0)).toBe(0);
    expect(barPct(5, 0)).toBe(0);
  });

  it("is 100 at the maximum", () => {
    expect(barPct(50, 50)).toBe(100);
  });
});

describe("constructLabel", () => {
  it("maps a known slug to prose", () => {
    expect(constructLabel("super-dispatch")).toBe("super() through the MRO");
  });

  it("passes an unknown slug through instead of blanking the row", () => {
    expect(constructLabel("some-new-bucket")).toBe("some-new-bucket");
  });
});
