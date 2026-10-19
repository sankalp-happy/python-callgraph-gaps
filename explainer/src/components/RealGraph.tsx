import type { Core, ElementDefinition, StylesheetJson } from "cytoscape";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CytoscapeComponent from "react-cytoscapejs";
import {
  edgeKey,
  moduleOf,
  replayOrder,
  shortLabel,
  type RuntimeEdgeFull,
} from "@/lib/realDemo";

interface RealGraphProps {
  edges: RuntimeEdgeFull[];
  missingKeys: Set<string>;
  modules: string[];
  staticPairs: Set<string>;
  /** Jury mode: drop the arc counters and the edge-count footer, which are
   *  precise and useless to someone seeing this for the first time. */
  simple?: boolean;
  autoPlay?: boolean;
  height?: number;
  /** Lets the caller show the running tally beside the graph instead of
   *  burying it in the toolbar. */
  onProgress?: (shown: number, total: number, missing: number) => void;
}

/** Aggregated arc between two rendered endpoints (module or function). */
interface Arc {
  source: string;
  target: string;
  missing: number;
  total: number;
  firstTs: number;
}

// A replay is only worth watching if it ENDS while people are still
// watching. 700 calls one-per-tick is over a minute of staring; instead the
// tick rate is fixed and the step size is derived so the whole trace plays
// out in about this long, whatever its length.
const PLAY_TICK_MS = 60;
const REPLAY_DURATION_MS = 20000;

// Whitespace left around the graph when it is fitted to its frame.
const FIT_PADDING = 28;
// Bounds on zoom. Without them a stray trackpad pinch in fullscreen can put
// the graph somewhere no button gets it back from, mid-presentation.
const MIN_ZOOM = 0.08;
const MAX_ZOOM = 3;

const TOKENS = [
  "--surface-2", "--rule", "--ink", "--ink-soft", "--ink-faint",
  "--steel", "--accent", "--danger", "--paper", "--font-mono",
] as const;
type Token = (typeof TOKENS)[number];

/**
 * Cytoscape paints to a <canvas>, and canvas has no CSS cascade -- a style
 * value of `var(--steel)` is not resolved, it is just an unparseable string,
 * and the graph renders invisible. So the tokens are read off the document
 * once and passed as literals, and re-read when the colour scheme changes so
 * the graph follows the rest of the page into dark mode.
 */
function useThemeTokens(): Record<Token, string> {
  const read = () => {
    const style = getComputedStyle(document.documentElement);
    return Object.fromEntries(
      TOKENS.map((t) => [t, style.getPropertyValue(t).trim()]),
    ) as Record<Token, string>;
  };
  const [tokens, setTokens] = useState(read);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const refresh = () => setTokens(read());
    media.addEventListener("change", refresh);
    const observer = new MutationObserver(refresh);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      media.removeEventListener("change", refresh);
      observer.disconnect();
    };
  }, []);
  return tokens;
}

/**
 * click's trace is ~700 function-level edges over 16 modules. Drawn flat that
 * is a hairball -- true, complete, and unreadable, which for a graph is the
 * same as wrong. So the default altitude is the module, and a module opens
 * into its functions on click.
 *
 * Endpoints are mapped through one function (`endpointFor`) rather than
 * branching per case, which is what makes a half-expanded graph correct:
 * an edge from an open module to a closed one resolves to function -> module
 * with no special handling.
 */
export function RealGraph({
  edges,
  missingKeys,
  modules,
  staticPairs,
  simple = false,
  autoPlay = false,
  height = 460,
  onProgress,
}: RealGraphProps) {
  const cyRef = useRef<Core | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const tk = useThemeTokens();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [cursor, setCursor] = useState<number | null>(null); // null = show all
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<Arc | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const ordered = useMemo(() => replayOrder(edges), [edges]);
  const shown = cursor === null ? ordered : ordered.slice(0, cursor);

  useEffect(() => {
    if (!autoPlay) return;
    setCursor(0);
    setPlaying(true);
  }, [autoPlay]);

  useEffect(() => {
    if (!playing) return;
    const step = Math.max(1, Math.ceil(ordered.length / (REPLAY_DURATION_MS / PLAY_TICK_MS)));
    const id = setInterval(() => {
      setCursor((c) => {
        const next = (c ?? 0) + step;
        if (next >= ordered.length) {
          setPlaying(false);
          return null; // settle on the complete graph rather than a frozen tail
        }
        return next;
      });
    }, PLAY_TICK_MS);
    return () => clearInterval(id);
  }, [playing, ordered.length]);

  const missingSoFar = shown.reduce(
    (n, e) => n + (missingKeys.has(edgeKey(e)) ? 1 : 0),
    0,
  );
  useEffect(() => {
    onProgress?.(shown.length, ordered.length, missingSoFar);
  }, [shown.length, ordered.length, missingSoFar, onProgress]);

  /** Frame the whole graph inside its box. The layout places nodes in graph
   *  coordinates that have nothing to do with the size of the frame -- click's
   *  15 modules lay out over ~1340x1350px, which at the default zoom of 1 left
   *  79% of the graph outside a 924x560 viewport with no scrollbar to reveal
   *  it. Nothing about that is visible as a bug; it just looks like a sparse
   *  graph, which is worse. */
  const fitView = useCallback(() => {
    const cy = cyRef.current;
    if (!cy || cy.destroyed() || cy.elements().empty()) return;
    cy.resize();
    cy.fit(undefined, FIT_PADDING);
  }, []);

  const endpointFor = useCallback(
    (qualname: string) => {
      const mod = moduleOf(qualname, modules);
      return expanded.has(mod) ? qualname : mod;
    },
    [expanded, modules],
  );

  const { elements, arcs } = useMemo(() => {
    const arcMap = new Map<string, Arc>();
    const nodeIds = new Set<string>();
    const parentOf = new Map<string, string>();

    // Module boxes come from the WHOLE trace, so the map is drawn up front
    // and the roads light up over it. Deriving them from `shown` would
    // re-run the layout on every tick as boxes appeared, and the opening
    // seconds would be a near-empty frame, because click's first calls are
    // all inside one module and self-arcs are not drawn.
    for (const e of edges) {
      for (const qual of [e.caller, e.callee]) nodeIds.add(moduleOf(qual, modules));
    }

    // Function dots are the opposite case: they come only from what has
    // actually been called. Opening click.core against the whole trace draws
    // 132 labelled nodes at once, and 132 labels do not fit in this frame at
    // any zoom a layout can reach -- fitting them lands at 0.08, where every
    // label is under a pixel and the module resolves into dust. Showing the
    // functions that have run keeps a drilled-in module readable, and says
    // something true rather than merely complete.
    for (const e of shown) {
      for (const qual of [e.caller, e.callee]) {
        const id = endpointFor(qual);
        const mod = moduleOf(qual, modules);
        if (id !== mod) {
          parentOf.set(id, mod);
          nodeIds.add(id);
        }
      }
    }

    for (const e of shown) {
      const source = endpointFor(e.caller);
      const target = endpointFor(e.callee);
      if (source === target) continue;
      const key = `${source} ${target}`;
      let arc = arcMap.get(key);
      if (!arc) {
        arc = { source, target, missing: 0, total: 0, firstTs: e.ts };
        arcMap.set(key, arc);
      }
      arc.total += 1;
      if (missingKeys.has(edgeKey(e))) arc.missing += 1;
    }

    const els: ElementDefinition[] = [];
    for (const id of nodeIds) {
      const parent = parentOf.get(id);
      els.push({
        data: {
          id,
          parent,
          label: parent ? shortLabel(id, modules) : id.replace(/^click\.?/, "") || "click",
          kind: parent ? "fn" : "mod",
        },
        classes: parent ? "fn" : expanded.has(id) ? "mod open" : "mod",
      });
    }
    for (const arc of arcMap.values()) {
      const allMissing = arc.missing === arc.total;
      els.push({
        data: {
          id: `a:${arc.source}>${arc.target}`,
          source: arc.source,
          target: arc.target,
          label: simple || arc.total <= 1 ? "" : `${arc.missing}/${arc.total}`,
          weight: Math.min(1 + Math.log2(arc.total + 1) * 1.6, 9),
        },
        classes: arc.missing === 0 ? "found" : allMissing ? "missing" : "mixed",
      });
    }
    return { elements: els, arcs: arcMap };
  }, [edges, shown, endpointFor, expanded, missingKeys, modules, simple]);

  // The cytoscape event handlers are bound once, against the first cy
  // instance, so anything they close over is frozen at first render. `arcs` is
  // rebuilt on every replay tick, so reading it through a ref is what makes a
  // click on an arc late in the replay resolve against the current map.
  const arcsRef = useRef(arcs);
  arcsRef.current = arcs;

  // Number of module/function boxes -- the only thing that should trigger a
  // re-layout and a re-fit. Arcs arriving on every replay tick must not.
  const nodeCount = useMemo(() => elements.filter((el) => !el.data.source).length, [elements]);

  // Re-fit whenever the frame changes size: entering fullscreen, leaving it,
  // a window resize, or the mobile reflow.
  useEffect(() => {
    const frame = shellRef.current;
    if (!frame || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => fitView());
    ro.observe(frame);
    return () => ro.disconnect();
  }, [fitView]);

  // A ResizeObserver on its own is not enough. If the graph mounts into a
  // container that is not laid out yet -- a hidden tab, a display:none
  // parent, a window that has not been sized -- cytoscape caches a width of
  // 0, every fit computes against a zero-width viewport, and no later resize
  // event necessarily arrives to correct it. Two frames after any change to
  // the node set, re-measure and re-frame unconditionally.
  useEffect(() => {
    const a = requestAnimationFrame(() => {
      fitView();
      // Second pass: fonts and the frame border settle a frame later, which
      // shifts the measured bounding box slightly.
      requestAnimationFrame(fitView);
    });
    return () => cancelAnimationFrame(a);
  }, [nodeCount, isFullscreen, height, fitView]);

  useEffect(() => {
    const onChange = () => {
      const active = document.fullscreenElement === shellRef.current;
      setIsFullscreen(active);
      // The frame has not been re-laid-out at the moment this fires.
      requestAnimationFrame(fitView);
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, [fitView]);

  const toggleFullscreen = useCallback(() => {
    const el = shellRef.current;
    if (!el) return;
    if (document.fullscreenElement === el) void document.exitFullscreen();
    else void el.requestFullscreen?.().catch(() => setIsFullscreen(false));
  }, []);

  const layout = useMemo(
    () => ({
      name: expanded.size ? "cose" : "circle",
      animate: false,
      padding: 24,
      nodeDimensionsIncludeLabels: true,
      // Tighter than cose's defaults: an expanded module is a handful of
      // called functions, and cose spreads disconnected ones across a strip
      // far wider than the frame if left to itself.
      idealEdgeLength: 55,
      nodeRepulsion: 5000,
      nodeOverlap: 4,
      componentSpacing: 45,
      gravity: 80,
    }),
    // Keyed on the NODE count, not the element count: a new layout object is
    // what makes cytoscape re-lay-out, and that must happen when a module is
    // expanded (or its functions stack on one point) but must NOT happen on
    // every replay tick, which would shuffle the whole graph mid-sentence.
    // nodeCount is therefore a deliberate key, not a value the body reads --
    // which is exactly what the exhaustive-deps rule cannot tell apart.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [expanded.size, nodeCount],
  );

  const stylesheet: StylesheetJson = [
    {
      selector: "node.mod",
      style: {
        "background-color": tk["--surface-2"],
        "background-opacity": 0.55,
        "border-width": 1,
        "border-color": tk["--rule"],
        shape: "round-rectangle",
        label: "data(label)",
        color: tk["--ink"],
        "font-family": tk["--font-mono"],
        "font-size": simple ? 15 : 11,
        "text-valign": "top",
        "text-margin-y": simple ? -7 : -4,
        padding: simple ? "20px" : "14px",
      },
    },
    {
      selector: "node.fn",
      style: {
        "background-color": tk["--steel"],
        shape: "ellipse",
        width: 9,
        height: 9,
        label: "data(label)",
        color: tk["--ink-soft"],
        "font-family": tk["--font-mono"],
        "font-size": 8,
        "text-valign": "bottom",
        "text-margin-y": 3,
        "min-zoomed-font-size": 7,
      },
    },
    {
      selector: "edge",
      style: {
        width: "data(weight)",
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.7,
        opacity: 0.85,
        label: "data(label)",
        "font-family": tk["--font-mono"],
        "font-size": 8,
        color: tk["--ink-faint"],
        "text-background-color": tk["--paper"],
        "text-background-opacity": 0.85,
        "text-background-padding": "1px",
      },
    },
    {
      selector: "edge.found",
      style: { "line-color": tk["--steel"], "target-arrow-color": tk["--steel"] },
    },
    {
      selector: "edge.mixed",
      style: {
        "line-color": tk["--accent"],
        "target-arrow-color": tk["--accent"],
      },
    },
    {
      selector: "edge.missing",
      style: {
        "line-color": tk["--danger"],
        "target-arrow-color": tk["--danger"],
        "line-style": "dashed",
      },
    },
    { selector: ".dim", style: { opacity: 0.12 } },
  ];

  // Opening a module is an inspection action, so it stops the replay. While
  // expanded, each tick that calls a new function adds a node, and a new node
  // re-runs the layout -- left playing, a drilled-in module would reshuffle
  // itself under the cursor of the person trying to read it.
  const toggle = (id: string) => {
    setPlaying(false);
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectedEdges = selected
    ? shown.filter(
        (e) =>
          endpointFor(e.caller) === selected.source && endpointFor(e.callee) === selected.target,
      )
    : [];

  return (
    <div className={`graph-shell stack gap-2${isFullscreen ? " is-fullscreen" : ""}`} ref={shellRef}>
      <div className="graph-toolbar">
        <button type="button" onClick={() => { setPlaying((p) => !p); if (cursor === null) setCursor(0); }}>
          {playing ? "Pause" : "Replay execution"}
        </button>
        <input
          type="range"
          min={0}
          max={ordered.length}
          value={cursor ?? ordered.length}
          onChange={(ev) => {
            setPlaying(false);
            const v = Number(ev.target.value);
            setCursor(v >= ordered.length ? null : v);
          }}
          aria-label="Execution position"
          style={{ flex: 1, minWidth: "8rem" }}
        />
        {!simple && (
          <span className="micro faint tnum">
            {shown.length} / {ordered.length} calls
          </span>
        )}
        {expanded.size > 0 && (
          <button type="button" onClick={() => setExpanded(new Set())}>
            Collapse all
          </button>
        )}
        <button type="button" onClick={fitView} title="Frame the whole graph again">
          Fit
        </button>
        <button
          type="button"
          className="graph-fs-btn"
          onClick={toggleFullscreen}
          aria-pressed={isFullscreen}
          title={isFullscreen ? "Exit full screen (Esc)" : "Full screen"}
        >
          {isFullscreen ? "Exit full screen" : "Full screen"}
        </button>
      </div>

      {!simple && (
        <p className="note note-faint">
          Each box is a module; click one to open it into its functions. Arc labels are
          missing/total. Dashed red = every call on that arc is absent from PyCG's graph.
        </p>
      )}

      <div className="graph-frame">
        <CytoscapeComponent
          elements={elements}
          stylesheet={stylesheet}
          layout={layout}
          style={{ width: "100%", height: isFullscreen ? "100%" : `${height}px` }}
          minZoom={MIN_ZOOM}
          maxZoom={MAX_ZOOM}
          // The graph is 560px of a ~720px viewport, so if it captures the
          // wheel there is no room left to scroll the page past it -- the
          // reader is trapped zooming a graph they were trying to scroll by.
          // Panning by drag stays on; box selection is off so a drag pans
          // instead of drawing a marquee nobody asked for.
          userZoomingEnabled={isFullscreen}
          boxSelectionEnabled={false}
          autounselectify
          cy={(cy) => {
            if (cyRef.current === cy) return;
            cyRef.current = cy;
            cy.on("tap", "node.mod", (ev) => toggle(ev.target.id()));
            cy.on("tap", "edge", (ev) => {
              const [source, target] = ev.target.id().slice(2).split(">");
              setSelected(arcsRef.current.get(`${source} ${target}`) ?? null);
            });
            cy.on("tap", (ev) => {
              if (ev.target === cy) setSelected(null);
            });
            // Fit once the layout has actually placed the nodes. Firing on
            // every layoutstop also covers expanding a module, which re-runs
            // the layout and would otherwise push the graph out of frame.
            // fitView, not cy.fit, because it re-measures the container first.
            cy.on("layoutstop", fitView);
          }}
        />
      </div>

      {selected && (
        <div className="edge-detail">
          <div className="stack-row" style={{ display: "flex", justifyContent: "space-between" }}>
            <p className="micro mono">
              {selected.source} → {selected.target} · {selected.missing} of {selected.total} missing
            </p>
            <button type="button" className="micro" onClick={() => setSelected(null)}>
              close
            </button>
          </div>
          <div className="edge-detail-list">
            {selectedEdges.slice(0, 40).map((e) => {
              const isMissing = missingKeys.has(edgeKey(e));
              return (
                <div key={edgeKey(e)} className={`edge-row ${isMissing ? "is-missing" : ""}`}>
                  <span className="marker">{isMissing ? "✕" : "✓"}</span>
                  <span className="mono micro">
                    {shortLabel(e.caller, modules)} → {shortLabel(e.callee, modules)}
                  </span>
                  <code className="micro faint">
                    {e.call_module}:{e.call_line} {e.source ?? ""}
                  </code>
                </div>
              );
            })}
            {selectedEdges.length > 40 && (
              <p className="micro faint">…and {selectedEdges.length - 40} more</p>
            )}
          </div>
        </div>
      )}

      {!simple && (
        <p className="micro faint">
          {staticPairs.size} edges in PyCG's graph · {ordered.length} distinct calls observed
        </p>
      )}
    </div>
  );
}
