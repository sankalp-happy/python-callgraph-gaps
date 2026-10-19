import type { Core, ElementDefinition, StylesheetJson } from "cytoscape";
import { useEffect, useRef } from "react";
import CytoscapeComponent from "react-cytoscapejs";
import type { RuntimeEdge } from "@/lib/liveDemo";

interface CytoscapeGraphProps {
  graph: Record<string, string[]>;
  runtimeEdges: RuntimeEdge[];
  missingEdges: RuntimeEdge[];
}

const missingKey = (e: RuntimeEdge) => `${e.caller} ${e.callee}`;

export function CytoscapeGraph({ graph, runtimeEdges, missingEdges }: CytoscapeGraphProps) {
  const cyRef = useRef<Core | null>(null);
  const missingSet = new Set(missingEdges.map(missingKey));

  // Cytoscape renders to <canvas> -- a CSS filter/animation on the container
  // glows the WHOLE graph, not one edge. Pulsing a specific edge has to go
  // through cytoscape's own animate() on that edge's collection.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || missingEdges.length === 0) return;
    const targets = cy.elements(".missing");
    if (targets.empty()) return;

    let cancelled = false;
    const pulse = () => {
      if (cancelled) return;
      targets
        .animate({ style: { opacity: 0.35, width: 3 } }, { duration: 650 })
        .animate({ style: { opacity: 1, width: 5 } }, { duration: 650, complete: pulse });
    };
    pulse();
    return () => {
      cancelled = true;
      targets.stop();
    };
  }, [missingEdges.length]);

  const nodeIds = new Set<string>();
  Object.entries(graph).forEach(([caller, callees]) => {
    nodeIds.add(caller);
    callees.forEach((c) => nodeIds.add(c));
  });
  runtimeEdges.forEach((e) => {
    nodeIds.add(e.caller);
    nodeIds.add(e.callee);
  });

  const elements: ElementDefinition[] = [];
  nodeIds.forEach((id) => {
    elements.push({ data: { id, label: id.split(".").slice(-1)[0] } });
  });

  const staticPairs = new Set<string>();
  Object.entries(graph).forEach(([caller, callees]) => {
    callees.forEach((callee) => {
      const key = `${caller} ${callee}`;
      staticPairs.add(key);
      elements.push({
        data: { id: `static:${key}`, source: caller, target: callee },
        classes: "static",
      });
    });
  });

  missingEdges.forEach((e) => {
    const key = missingKey(e);
    if (staticPairs.has(key)) return;
    elements.push({
      data: { id: `missing:${key}`, source: e.caller, target: e.callee },
      classes: "missing",
    });
  });

  runtimeEdges.forEach((e) => {
    const key = missingKey(e);
    if (missingSet.has(key) || staticPairs.has(key)) return;
    elements.push({
      data: { id: `runtime:${key}`, source: e.caller, target: e.callee },
      classes: "ran",
    });
  });

  const stylesheet: StylesheetJson = [
    {
      selector: "node",
      style: {
        "background-color": "#1f2933",
        label: "data(label)",
        color: "#e4e7eb",
        "font-size": 11,
        "text-valign": "bottom",
        "text-margin-y": 6,
      },
    },
    {
      selector: "edge",
      style: {
        width: 2,
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        "line-color": "#7b8794",
        "target-arrow-color": "#7b8794",
      },
    },
    {
      selector: "edge.ran",
      style: { "line-color": "#2dbe6c", "target-arrow-color": "#2dbe6c" },
    },
    {
      selector: "edge.missing",
      style: {
        "line-color": "#e12d39",
        "target-arrow-color": "#e12d39",
        width: 4,
        "line-style": "dashed",
      },
    },
  ];

  return (
    <CytoscapeComponent
      elements={elements}
      stylesheet={stylesheet}
      layout={{ name: "breadthfirst", directed: true, padding: 20 }}
      style={{ width: "100%", height: "360px" }}
      cy={(cy) => {
        cyRef.current = cy;
      }}
    />
  );
}
