import type { DeterminismFile, ScalingFile, ScalingStep } from "@/lib/realDemo";

interface ToolBehaviourPanelProps {
  scaling: ScalingFile | null;
  determinism: DeterminismFile | null;
}

const W = 720;
const H = 220;
const PAD = { top: 16, right: 16, bottom: 28, left: 44 };

/** Steps where adding a source file made the graph SMALLER. Monotonicity is
 *  not a nicety here: a call graph that shrinks when you show the analyser
 *  more of the program cannot be a sound over-approximation of it. */
function regressions(steps: ScalingStep[]): ScalingStep[] {
  const out: ScalingStep[] = [];
  let prev = 0;
  for (const s of steps) {
    if (s.status !== "ok" || s.nodes === undefined) continue;
    if (s.nodes < prev) out.push(s);
    prev = s.nodes;
  }
  return out;
}

function ScalingChart({ steps }: { steps: ScalingStep[] }) {
  const ok = steps.filter((s) => s.status === "ok" && s.nodes !== undefined);
  if (ok.length === 0) return null;
  const maxNodes = Math.max(...ok.map((s) => s.nodes!));
  const maxX = Math.max(...steps.map((s) => s.n_files));
  const x = (n: number) => PAD.left + ((n - 1) / Math.max(maxX - 1, 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => H - PAD.bottom - (v / maxNodes) * (H - PAD.top - PAD.bottom);

  const path = ok.map((s, i) => `${i === 0 ? "M" : "L"}${x(s.n_files)},${y(s.nodes!)}`).join(" ");
  const drops = new Set(regressions(steps).map((s) => s.n_files));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img"
         aria-label="PyCG node count as click modules are added">
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line x1={PAD.left} x2={W - PAD.right} y1={y(maxNodes * f)} y2={y(maxNodes * f)}
                stroke="var(--rule-soft)" strokeWidth={1} />
          <text x={PAD.left - 6} y={y(maxNodes * f) + 3} textAnchor="end"
                className="chart-tick">{Math.round(maxNodes * f)}</text>
        </g>
      ))}
      <path d={path} fill="none" stroke="var(--steel)" strokeWidth={1.5} />
      {ok.map((s) => (
        <circle key={s.n_files} cx={x(s.n_files)} cy={y(s.nodes!)} r={drops.has(s.n_files) ? 4 : 2.5}
                fill={drops.has(s.n_files) ? "var(--danger)" : "var(--steel)"}>
          <title>{`+${s.added}: ${s.nodes} nodes, ${s.edges} edges, ${s.seconds}s, ${s.peak_rss_mb}MB`}</title>
        </circle>
      ))}
      <text x={PAD.left} y={H - 8} className="chart-tick">1 module</text>
      <text x={W - PAD.right} y={H - 8} textAnchor="end" className="chart-tick">
        {maxX} modules
      </text>
    </svg>
  );
}

export function ToolBehaviourPanel({ scaling, determinism }: ToolBehaviourPanelProps) {
  const drops = scaling ? regressions(scaling.steps) : [];
  const failed = scaling ? scaling.steps.filter((s) => s.status !== "ok") : [];

  return (
    <div className="wrap stack gap-4">
      <div className="stack gap-1">
        <div className="rule-heavy" style={{ maxWidth: "5rem" }} />
        <p className="eyebrow" style={{ margin: 0 }}>
          The tool itself
        </p>
        <h2>Before asking what it misses, ask whether it returns the same answer twice</h2>
        <p className="deck">
          A miss rate assumes the graph is a function of the input. On click it is not. Both panels
          below were found while measuring something else, and both are reproducible with the
          scripts in <code className="mono">traceweave/scripts/</code>.
        </p>
      </div>

      {scaling && (
        <div className="row-2col">
          <div className="stack gap-1">
            <p className="micro faint">Nodes in the graph as modules are added</p>
            <p className="note note-faint">
              Cumulative: each point analyses one more of {scaling.repo}'s modules alongside all
              the previous ones, in a fresh container capped at {scaling.memory_cap}.
            </p>
          </div>
          <div className="stack gap-2">
            <ScalingChart steps={scaling.steps} />
            {drops.length > 0 && (
              <div className="notice notice-warn">
                <p className="note">
                  <strong>
                    {drops.length} of {scaling.steps.length} steps made the graph smaller.
                  </strong>{" "}
                  Adding{" "}
                  <code className="mono">{drops.map((d) => d.added).join(", ")}</code> reduced the
                  node count rather than increasing it. Showing the analyser more of the program
                  produced a smaller picture of it, so the graph is not a sound
                  over-approximation, and a subset of a repository can score better than the whole.
                </p>
              </div>
            )}
            {failed.length > 0 && (
              <p className="micro faint">
                {failed.length} step(s) did not complete:{" "}
                {failed.map((f) => `${f.added} (${f.status})`).join(", ")}
              </p>
            )}
          </div>
        </div>
      )}

      {determinism && (
        <div className="row-2col">
          <div className="stack gap-1">
            <p className="micro faint">The same input, {determinism.attempted} times</p>
            <p className="note note-faint">
              All {determinism.n_files} modules of {determinism.repo}, identical command, identical
              image, {determinism.memory_cap} cap.
            </p>
          </div>
          <div className="stack gap-2">
            <p>
              <strong className="tnum">
                {determinism.completed} of {determinism.attempted}
              </strong>{" "}
              runs returned a graph at all; the rest exhausted {determinism.memory_cap} and were
              killed. Which happens is decided by the hash seed, not by the input.
            </p>
            <div className="seed-rows">
              {[...new Set(determinism.trials.map((t) => t.seed))].map((seed) => {
                const runs = determinism.trials.filter((t) => t.seed === seed);
                return (
                  <div key={seed} className="seed-row">
                    <span className="micro mono">
                      PYTHONHASHSEED={seed}
                    </span>
                    <div className="trial-grid">
                      {runs.map((t, i) => (
                        <div
                          key={i}
                          className={`trial ${t.status === "ok" ? "trial-ok" : "trial-dead"}`}
                          title={
                            t.status === "ok"
                              ? `${t.nodes} nodes / ${t.edges} edges in ${t.seconds}s`
                              : t.detail ?? t.status
                          }
                        >
                          <span className="micro tnum">
                            {t.status === "ok" ? t.nodes : "OOM"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            {determinism.reproducible_per_seed && (
              <p className="note">
                Every seed was internally consistent across its repeats, and seeds disagreed with
                each other, which is the signature of hash-order dependence rather than noise.
                Pinning the seed makes PyCG reproducible; nothing in its documentation or CLI says
                you have to.
              </p>
            )}
            <p className="note note-faint">
              Each cell is one run; the number is the node count it returned. PyCG's fixpoint
              iterates over sets, so the seed, which is random per process unless pinned, changes the
              iteration order, and with it both which fixpoint is reached and whether one is
              reached before memory runs out. Runs with the seed left at its default have also
              returned 1137, 1160 and 1286 nodes on this same input.
            </p>
            <div className="notice notice-warn">
              <p className="note">
                <strong>This constrains our own result too.</strong> The{" "}
                {determinism.repo} miss rate on this page comes from one PyCG run, so it is one
                sample of that spread, not a fixed value. Any published figure needs a seed policy
                and repeated runs. That is a finding about the measurement protocol, and we reached it
                before relying on the protocol.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
