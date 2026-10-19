import { useEffect, useRef, useState } from "react";
import { ConstructGrid } from "@/components/ConstructGrid";
import { PresentationView } from "@/components/PresentationView";
import { CytoscapeGraph } from "@/components/CytoscapeGraph";
import { EvidencePanel } from "@/components/EvidencePanel";
import { RealRepoPanel } from "@/components/RealRepoPanel";
import { ToolBehaviourPanel } from "@/components/ToolBehaviourPanel";
import {
  initialPollState,
  missingEdgesDiff,
  missingRatio,
  reduceLivePoll,
  type PollState,
  type RuntimeFile,
  type StaticFile,
} from "@/lib/liveDemo";
import type {
  ConstructsFile,
  DeterminismFile,
  RealRuntime,
  RealStatic,
  RealSummary,
  ScalingFile,
} from "@/lib/realDemo";

const POLL_INTERVAL_MS = 500;

function usePolledFile<T extends { run_id: string }>(
  url: string,
  minRunId: string | null,
  resetToken: number,
) {
  const [state, setState] = useState<PollState<T>>(() => initialPollState<T>());

  useEffect(() => {
    setState(initialPollState<T>());
    let cancelled = false;

    const tick = async () => {
      try {
        const res = await fetch(`${url}?t=${Date.now()}`, { cache: "no-store" });
        if (!res.ok || cancelled) return;
        const raw = await res.text();
        if (cancelled) return;
        setState((prev) => reduceLivePoll<T>(raw, minRunId, prev));
      } catch {
        // network hiccup or file not written yet -- retry next tick
      }
    };

    tick();
    const id = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
    // resetToken forces a fresh poll cycle (and fresh initial state) when
    // the presenter clicks "start new run", even if url/minRunId are equal
    // to their previous values.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, minRunId, resetToken]);

  return state;
}

/** Fetched once, not polled: these are measurements committed to the repo, not
 *  something a presenter re-runs on stage. A missing file yields null and its
 *  section is skipped, so a partial checkout degrades instead of blanking. */
function useStaticJson<T>(url: string): T | null {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(url)
      .then((res) => (res.ok ? res.json() : null))
      .then((json) => {
        if (!cancelled) setData(json as T);
      })
      .catch(() => setData(null));
    return () => {
      cancelled = true;
    };
  }, [url]);
  return data;
}

function useElapsedSeconds(resetToken: number, stop: boolean) {
  const startedAt = useRef(Date.now());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    startedAt.current = Date.now();
    setElapsed(0);
  }, [resetToken]);

  useEffect(() => {
    if (stop) return;
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, [stop, resetToken]);

  return elapsed;
}

export default function LiveDemo() {
  const [minRunId, setMinRunId] = useState<string | null>(null);
  const [resetToken, setResetToken] = useState(0);
  // Default to the jury view. The detailed panels are for answering a
  // sceptical follow-up, not for leading with.
  const [detailed, setDetailed] = useState(false);

  const staticState = usePolledFile<StaticFile>("/live/static.json", minRunId, resetToken);
  const runtimeState = usePolledFile<RuntimeFile>("/live/runtime.json", minRunId, resetToken);

  const realSummary = useStaticJson<RealSummary>("/live/real_summary.json");
  const realStatic = useStaticJson<RealStatic>("/live/real_static.json");
  const realRuntime = useStaticJson<RealRuntime>("/live/real_runtime.json");
  const constructs = useStaticJson<ConstructsFile>("/live/constructs.json");
  const scaling = useStaticJson<ScalingFile>("/live/scaling.json");
  const determinism = useStaticJson<DeterminismFile>("/live/determinism.json");

  const bothReady =
    staticState.status === "ok" &&
    runtimeState.status === "ok" &&
    staticState.data?.run_id === runtimeState.data?.run_id;

  const elapsed = useElapsedSeconds(resetToken, bothReady);

  const startNewRun = () => {
    const lastRunId = staticState.data?.run_id ?? runtimeState.data?.run_id ?? "0";
    setMinRunId(lastRunId);
    setResetToken((t) => t + 1);
  };

  const waitingForTerminal = !bothReady && minRunId !== null;

  const diff =
    bothReady && staticState.data && runtimeState.data
      ? missingEdgesDiff(staticState.data.graph, runtimeState.data.edges)
      : null;

  return (
    <div className="page">
      {/* In presentation mode the masthead is compressed so the graph clears
          the fold. In detail mode it can breathe -- nobody is reading that
          from the back of a room. */}
      <header className={`masthead${detailed ? "" : " masthead-compact"}`}>
        <div className="wrap stack gap-3">
          <div className="stack gap-2">
            <div className="rule-heavy" style={{ maxWidth: "5rem" }} />
            <p className="eyebrow" style={{ margin: 0 }}>
              Live demo
            </p>
            <h1>Watch the map miss a road</h1>
            <p className="deck">
              A big program is too large to hold in your head, so tools draw a map of which
              function calls which. They build that map by reading the code, never by running it.
              We took a real Python library, drew its map, then ran the library and wrote down
              every call it actually made. Here is what the two look like side by side.
            </p>
          </div>
          <div className="masthead-foot">
            <a href="#" className="micro faint">
              ← back to the full story
            </a>
            <button type="button" className="mode-switch" onClick={() => setDetailed((v) => !v)}>
              {detailed ? "Hide the detail" : "Show the detail"}
            </button>
          </div>
        </div>
      </header>

      {realSummary && realStatic && realRuntime && (
        <section className={detailed ? undefined : "section-flush"}>
          <PresentationView
            summary={realSummary}
            staticFile={realStatic}
            runtime={realRuntime}
          />
        </section>
      )}

      {detailed && (
        <>
      <section>
        <div className="wrap stack gap-4">
          <div className="row-2col">
            <p className="micro faint">Status</p>
            <div className="stack gap-1">
              {bothReady ? (
                <p>
                  <strong>run {staticState.data?.run_id}</strong>, both files matched and parsed
                </p>
              ) : (
                <p style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
                  <span className="live-spinner" aria-hidden="true" />
                  waiting for a fresh run… {elapsed}s
                </p>
              )}
              {waitingForTerminal && (
                <p className="note note-faint">
                  Nothing will appear until <code className="mono">./run_demo.sh</code> writes a
                  newer run id. This button only sets the floor, it does not start the run.
                  Warm runs land in about 3s; if nothing arrives by 15s, use{" "}
                  <code className="mono">./restore_fallback.sh</code>.
                </p>
              )}
              <button type="button" onClick={startNewRun} style={{ alignSelf: "flex-start" }}>
                Start new run
              </button>
            </div>
          </div>

          {diff && (
            <>
              <div className="row-2col">
                <p className="micro faint">Observed at runtime vs. present statically</p>
                <p className="live-counter">
                  {diff.counter.missing} / {diff.counter.total} edges missing (
                  {(missingRatio(diff.counter) * 100).toFixed(0)}%)
                </p>
              </div>
              <CytoscapeGraph
                graph={staticState.data!.graph}
                runtimeEdges={runtimeState.data!.edges}
                missingEdges={diff.missingEdges}
              />
            </>
          )}
        </div>
      </section>
      {realSummary && realStatic && realRuntime && (
        <section>
          <RealRepoPanel summary={realSummary} staticFile={realStatic} runtime={realRuntime} />
        </section>
      )}

      {constructs && (
        <section>
          <ConstructGrid data={constructs} clickConstructs={realSummary?.by_construct ?? []} />
        </section>
      )}

      {(scaling || determinism) && (
        <section>
          <ToolBehaviourPanel scaling={scaling} determinism={determinism} />
        </section>
      )}

      <section>
        <EvidencePanel />
      </section>
        </>
      )}
    </div>
  );
}
