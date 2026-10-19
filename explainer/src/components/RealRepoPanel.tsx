import { useState } from "react";
import { RealGraph } from "@/components/RealGraph";
import {
  barPct,
  constructLabel,
  edgeKey,
  shortLabel,
  type RealRuntime,
  type RealStatic,
  type RealSummary,
} from "@/lib/realDemo";

interface RealRepoPanelProps {
  summary: RealSummary;
  staticFile: RealStatic;
  runtime: RealRuntime;
}

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

export function RealRepoPanel({ summary, staticFile, runtime }: RealRepoPanelProps) {
  const [showAllEdges, setShowAllEdges] = useState(false);

  const missingKeys = new Set(summary.missing_edges.map(edgeKey));
  const staticPairs = new Set(
    Object.entries(staticFile.graph).flatMap(([caller, callees]) =>
      callees.map((callee) => `${caller} ${callee}`),
    ),
  );
  const internal = runtime.edges.filter((e) => e.caller !== "<entry>");
  const maxConstruct = Math.max(...summary.by_construct.map((c) => c.total), 1);
  const maxModule = Math.max(...summary.by_module.map((m) => m.total), 1);
  const edgesShown = showAllEdges ? summary.missing_edges : summary.missing_edges.slice(0, 25);

  return (
    <div className="wrap stack gap-4">
      <div className="stack gap-1">
        <div className="rule-heavy" style={{ maxWidth: "5rem" }} />
        <p className="eyebrow" style={{ margin: 0 }}>
          The real repository
        </p>
        <h2>{summary.repo}, its own test suite, and the calls the map never drew</h2>
        <p className="deck">
          Not a fixture. {summary.analysed_modules.length} modules of{" "}
          <code className="mono">pallets/{summary.repo}</code> at{" "}
          <code className="mono">{summary.sha.slice(0, 12)}</code>, analysed by PyCG 0.0.8, then
          run for real under the library's own 1,939-test suite while every call was recorded.
        </p>
      </div>

      <div className="headline-row">
        <div className="headline-figure">
          <p className="headline-number tnum">{pct(summary.conservative_ratio)}</p>
          <p className="micro">
            of the {summary.conservative_counter.total} calls that ran are absent from the static
            call graph
          </p>
        </div>
        <div className="stack gap-2">
          <p>
            <strong className="tnum">
              {summary.conservative_counter.missing} of {summary.conservative_counter.total}
            </strong>{" "}
            observed call edges have no counterpart in PyCG's graph.
          </p>
          <p className="note note-faint">
            Held out of that fraction, on both sides: {summary.counter.entry_excluded} edges
            entering from outside the package (nothing static could match them), and the{" "}
            {summary.held_out_constructs.join(" and ")} buckets below, which are arguable. Counting
            everything gives {pct(summary.missing_ratio)} ({summary.counter.missing}/
            {summary.counter.total}); the smaller number is the one to quote.
          </p>
        </div>
      </div>

      <div className="notice">
        <p className="note">
          <strong>This is n = 1.</strong> One repository, one workload, one run. It is a working
          Phase-2 prototype, not the corpus result H2a asks for. That needs the sampled repo set
          and multiple workloads per repo. Nothing here licenses a claim about Python in general.
        </p>
      </div>

      <RealGraph
        edges={internal}
        missingKeys={missingKeys}
        modules={summary.analysed_modules}
        staticPairs={staticPairs}
      />

      <div className="row-2col">
        <div className="stack gap-1">
          <p className="micro faint">By construct</p>
          <p className="note note-faint">
            Each observed call is tagged by the language construct that produced it, from the
            call-site line. Bars are total calls; the filled part is what PyCG missed.
          </p>
        </div>
        <div className="stack gap-2">
          {summary.by_construct.map((row) => (
            <div key={row.construct} className="bar-row">
              <span className="micro">
                {constructLabel(row.construct)}
                {row.held_out && <span className="faint"> · held out</span>}
              </span>
              <div className="bar-track" title={`${row.missing} of ${row.total}`}>
                <div
                  className="bar-fill-total"
                  style={{ width: `${barPct(row.total, maxConstruct)}%` }}
                >
                  <div
                    className={`bar-fill-missing ${row.construct === "bare-call" ? "is-control" : ""}`}
                    style={{ width: `${row.total ? (row.missing / row.total) * 100 : 0}%` }}
                  />
                </div>
              </div>
              <span className="micro faint tnum">
                {row.missing}/{row.total}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="notice notice-ok">
        <p className="note">
          <strong>Read the control first.</strong> A plain <code className="mono">foo()</code> call
          is the easiest edge there is, and PyCG found{" "}
          {(() => {
            const c = summary.by_construct.find((r) => r.construct === "bare-call");
            return c ? `${c.total - c.missing} of ${c.total}` : "almost all";
          })()}{" "}
          of them. That is what makes the rest of this table evidence about PyCG rather than
          evidence about our name-matching: a pipeline that could not match names would have
          failed here too.
        </p>
      </div>

      <div className="row-2col">
        <p className="micro faint">By module</p>
        <div className="stack gap-1">
          {summary.by_module.map((row) => (
            <div key={row.module} className="bar-row">
              <span className="micro mono">{row.module.replace("click.", "")}</span>
              <div className="bar-track">
                <div className="bar-fill-total" style={{ width: `${barPct(row.total, maxModule)}%` }}>
                  <div
                    className="bar-fill-missing"
                    style={{ width: `${row.total ? (row.missing / row.total) * 100 : 0}%` }}
                  />
                </div>
              </div>
              <span className="micro faint tnum">
                {row.missing}/{row.total}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="stack gap-2">
        <p className="micro faint">
          Every missed edge, with the line of {summary.repo} that made the call
        </p>
        <div className="edge-table">
          {edgesShown.map((e) => (
            <div key={edgeKey(e)} className="edge-table-row">
              <span className="micro mono">
                {shortLabel(e.caller, summary.analysed_modules)} →{" "}
                {shortLabel(e.callee, summary.analysed_modules)}
              </span>
              <span className="micro faint">{constructLabel(e.construct ?? "")}</span>
              <code className="micro">
                <span className="faint">
                  {e.call_module?.replace("click.", "")}:{e.call_line}
                </span>{" "}
                {e.source}
              </code>
            </div>
          ))}
        </div>
        {summary.missing_edges.length > 25 && (
          <button type="button" onClick={() => setShowAllEdges((v) => !v)}>
            {showAllEdges
              ? "Show first 25"
              : `Show all ${summary.missing_edges.length} missed edges`}
          </button>
        )}
      </div>

      <div className="row-2col">
        <p className="micro faint">What was excluded, and why</p>
        <div className="stack gap-1">
          <p className="note">
            <code className="mono">{summary.excluded_files.join(", ")}</code> is excluded from both
            sides. Including it makes PyCG's behaviour unstable: identical runs have returned
            1137, 1160 and 1286 nodes, and others exhausted 8GB and were killed
            (<code className="mono">scripts/pycg_determinism.py</code>). Tracing a module the
            static side never saw would also score all of its edges as missed for free.
          </p>
          <p className="note note-faint">
            PyCG also emitted {summary.alias_merge.aliased_nodes} functions under two different
            names at once ({summary.alias_merge.nodes_before} nodes →{" "}
            {summary.alias_merge.nodes_after} after merging). Left unmerged, that alone would have
            inflated the miss rate by about 11 points.
          </p>
          <p className="note note-faint">
            This run pinned <code className="mono">PYTHONHASHSEED={summary.hash_seed}</code>. That
            makes it reproducible, not seed-independent. PyCG returns a different graph under a
            different seed, so the figure above is one point in a spread, and the seed is part of
            the result.
          </p>
        </div>
      </div>
    </div>
  );
}
