// Types and pure helpers for the real-repository measurement (click), the
// construct grid, and the two tool-behaviour panels. Kept framework-free so
// the layout maths and the graph shaping can be unit-tested without a DOM.
//
// Every file this reads is produced by traceweave/demo/{run_real.sh,
// build_constructs.py} and traceweave/scripts/{pycg_scaling,
// pycg_determinism}.py. Nothing here recomputes a measurement; if a number
// is on screen, a script measured it and wrote it down.

export interface RuntimeEdgeFull {
  caller: string;
  callee: string;
  ts: number;
  module: string;
  call_module: string | null;
  call_line: number | null;
  def_line: number;
  via_external_frames?: number;
  source?: string | null;
  construct?: string;
}

export interface ConstructRow {
  construct: string;
  missing: number;
  total: number;
  ratio: number;
  held_out: boolean;
}

export interface ModuleRow {
  module: string;
  missing: number;
  total: number;
  ratio: number;
}

export interface RealSummary {
  run_id: string;
  repo: string;
  sha: string;
  workload: string;
  counter: { missing: number; total: number; entry_excluded: number };
  missing_ratio: number;
  conservative_counter: { missing: number; total: number };
  conservative_ratio: number;
  held_out_constructs: string[];
  by_construct: ConstructRow[];
  by_module: ModuleRow[];
  missing_edges: RuntimeEdgeFull[];
  analysed_modules: string[];
  excluded_files: string[];
  static_nodes: number;
  /** The PYTHONHASHSEED the static graph was produced under. Part of the
   *  result, not metadata: PyCG returns a different graph under a different
   *  seed (see DeterminismFile). */
  hash_seed: string;
  static_cost: { seconds: number; peak_rss_mb: number; nodes: number; edges: number } | null;
  alias_merge: { aliased_nodes: number; nodes_before: number; nodes_after: number };
}

export interface RealStatic {
  run_id: string;
  graph: Record<string, string[]>;
  analysed_files: string[];
  excluded_files: string[];
}

export interface RealRuntime {
  run_id: string;
  edges: RuntimeEdgeFull[];
  analysed_modules: string[];
  workload: string;
}

export interface ConstructCard {
  construct: string;
  title: string;
  blurb: string;
  citation: string;
  citation_url: string;
  is_control: boolean;
  outcome: "found" | "missed" | "resolved-in-small";
  click_evidence?: string;
  dir: string;
  source: string;
  graph: Record<string, string[]>;
  runtime_edges: RuntimeEdgeFull[];
  missing_edges: RuntimeEdgeFull[];
  counter: { missing: number; total: number };
  expected_missing: string[][];
  expect_found: string[][];
  expectation_met: boolean;
}

export interface ConstructsFile {
  run_id: string;
  constructs: ConstructCard[];
  n_failed_predictions: number;
}

export interface ScalingStep {
  n_files: number;
  added: string;
  measured_last: boolean;
  status: "ok" | "timeout" | "killed" | "error";
  nodes?: number;
  edges?: number;
  seconds?: number;
  peak_rss_mb?: number;
  wall_seconds: number;
  detail?: string;
}

export interface ScalingFile {
  repo: string;
  sha: string;
  package: string;
  memory_cap: string;
  timeout_seconds: number;
  measured_last: string[];
  steps: ScalingStep[];
}

export interface DeterminismTrial {
  seed: string;
  repeat: number;
  status: "ok" | "timeout" | "killed" | "error";
  nodes?: number;
  edges?: number;
  seconds?: number;
  wall_seconds: number;
  detail?: string;
}

export interface DeterminismFile {
  repo: string;
  sha: string;
  n_files: number;
  memory_cap: string;
  trials: DeterminismTrial[];
  completed: number;
  attempted: number;
  distinct_results: { nodes: number; edges: number }[];
  reproducible_per_seed: boolean;
}

/** `click.core.Command.invoke` -> `click.core`. The module a node lives in is
 *  the longest analysed-module prefix, not everything before the last dot:
 *  splitting on the last dot would put `click.core.Command.invoke` in a
 *  module called `click.core.Command`, which does not exist. */
export function moduleOf(qualname: string, modules: string[]): string {
  let best = "";
  for (const m of modules) {
    if ((qualname === m || qualname.startsWith(m + ".")) && m.length > best.length) best = m;
  }
  return best || qualname.split(".").slice(0, -1).join(".") || qualname;
}

/** Trailing segment(s) below the module, for a readable node label. */
export function shortLabel(qualname: string, modules: string[]): string {
  const mod = moduleOf(qualname, modules);
  const rest = qualname.startsWith(mod + ".") ? qualname.slice(mod.length + 1) : qualname;
  return rest || qualname;
}

export interface ModuleEdge {
  source: string;
  target: string;
  missing: number;
  total: number;
}

/** Collapse a function-level edge set to module-level, which is the only
 *  altitude at which ~700 edges are legible at a glance. Self-edges (a call
 *  within one module) are kept out: they would draw ~15 loops that carry no
 *  information the module's own missing/total counter does not already give. */
export function moduleEdges(
  edges: RuntimeEdgeFull[],
  missing: Set<string>,
  modules: string[],
): ModuleEdge[] {
  const acc = new Map<string, ModuleEdge>();
  for (const e of edges) {
    const source = moduleOf(e.caller, modules);
    const target = moduleOf(e.callee, modules);
    if (source === target) continue;
    const key = `${source} ${target}`;
    let row = acc.get(key);
    if (!row) {
      row = { source, target, missing: 0, total: 0 };
      acc.set(key, row);
    }
    row.total += 1;
    if (missing.has(edgeKey(e))) row.missing += 1;
  }
  return [...acc.values()].sort((a, b) => b.missing - a.missing);
}

export const edgeKey = (e: { caller: string; callee: string }) => `${e.caller} ${e.callee}`;

/** Edges ordered by when they first ran, for the replay scrubber. Ties are
 *  broken by insertion order: the tracer's timestamps come from time.time(),
 *  whose resolution is coarser than the gap between consecutive calls, so
 *  sorting on ts alone would shuffle same-microsecond edges on every render. */
export function replayOrder(edges: RuntimeEdgeFull[]): RuntimeEdgeFull[] {
  return edges
    .map((e, i) => ({ e, i }))
    .sort((a, b) => a.e.ts - b.e.ts || a.i - b.i)
    .map(({ e }) => e);
}

/** Bar width as a percentage, floored so a nonzero value is never invisible. */
export function barPct(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max((value / max) * 100, value > 0 ? 1.5 : 0);
}

/** Human-readable construct names. The raw slugs are how the classifier tags
 *  edges and how the JSON stores them; these are what a reader should see. */
export const CONSTRUCT_LABELS: Record<string, string> = {
  "attribute-dispatch": "Call on an unresolved receiver",
  "self-dispatch": "self.method() override",
  "name-absent-callback": "Callback held in a slot",
  "indirect-construction": "Construction via a variable class",
  "super-dispatch": "super() through the MRO",
  "dunder-protocol": "Implicit protocol call",
  "synthetic-scope": "Comprehension / lambda scope",
  "property-getter": "Property getter",
  "bare-call": "Direct call (control)",
  "reflective-lookup": "getattr / importlib",
  "single-candidate-control": "Indirect construction, one candidate",
  "plugin-registry": "Decorator-built registry",
  "dynamic-import": "importlib by computed name",
  unattributed: "No call site recovered",
};

export const constructLabel = (slug: string) => CONSTRUCT_LABELS[slug] ?? slug;
