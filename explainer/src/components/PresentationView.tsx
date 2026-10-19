import { useCallback, useState } from "react";
import { RealGraph } from "@/components/RealGraph";
import { edgeKey, type RealRuntime, type RealStatic, type RealSummary } from "@/lib/realDemo";

interface PresentationViewProps {
  summary: RealSummary;
  staticFile: RealStatic;
  runtime: RealRuntime;
}

/**
 * The jury-facing view. Everything here is aimed at someone who has never
 * heard of a call graph and will see this once, for a couple of minutes,
 * from the back of a room.
 *
 * Two rules it follows, both of which the detailed panel breaks on purpose:
 *   1. One idea per screen, and the graph is the idea.
 *   2. No number appears without the plain-English sentence that says what
 *      it means. A bare "54.3%" invites the wrong question ("of what?").
 */
export function PresentationView({ summary, staticFile, runtime }: PresentationViewProps) {
  const [progress, setProgress] = useState({ shown: 0, total: 0, missing: 0 });

  const missingKeys = new Set(summary.missing_edges.map(edgeKey));
  const staticPairs = new Set(
    Object.entries(staticFile.graph).flatMap(([caller, callees]) =>
      callees.map((callee) => `${caller} ${callee}`),
    ),
  );
  const internal = runtime.edges.filter((e) => e.caller !== "<entry>");

  // useCallback: RealGraph reports progress from an effect keyed on this
  // function, so a fresh identity every render would loop.
  const onProgress = useCallback(
    (shown: number, total: number, missing: number) => setProgress({ shown, total, missing }),
    [],
  );

  const found = progress.shown - progress.missing;

  // Derived, not typed in: the control bucket's success rate is the sentence
  // "the map is not broken" rests on, and a hardcoded 97% would quietly go
  // stale the next time run_real.sh is run.
  const control = summary.by_construct.find((r) => r.construct === "bare-call");
  const controlPct = control && control.total
    ? Math.round(((control.total - control.missing) / control.total) * 100)
    : null;

  return (
    <div className="wrap stack gap-3">
      {/* The headline and the premise now live in the masthead, so the graph
          is the first thing on screen rather than the fourth. All that is
          left here is the one sentence that has to be read against it. */}
      <p className="pres-caption">
        <span>
          Each box is one file of the program. Each line is the calls running between two files.
        </span>
      </p>

      <div className="pres-stage">
        <RealGraph
          edges={internal}
          missingKeys={missingKeys}
          modules={summary.analysed_modules}
          staticPairs={staticPairs}
          simple
          autoPlay
          height={520}
          onProgress={onProgress}
        />
      </div>

      {/* Key first, then the count. A line carries every call between two
          files at once, so it can be partly right, and the orange case was
          the most common thing on screen with nothing explaining it. */}
      <div className="pres-legend">
        <span className="pres-key">
          <span className="pres-swatch pres-swatch-box" /> one file of the program
        </span>
        <span className="pres-key">
          <span className="pres-swatch pres-swatch-found" /> the map had all these calls
        </span>
        <span className="pres-key">
          <span className="pres-swatch pres-swatch-mixed" /> it had some of them
        </span>
        <span className="pres-key">
          <span className="pres-swatch pres-swatch-missing" /> it had none of them
        </span>
      </div>

      <div className="pres-tally">
        <div className="pres-stat">
          <span className="pres-stat-num tnum">{progress.shown}</span>
          <span className="micro">calls the program actually made</span>
        </div>
        <div className="pres-stat pres-stat-ok">
          <span className="pres-stat-num tnum">{found}</span>
          <span className="micro">the map had these</span>
        </div>
        <div className="pres-stat pres-stat-bad">
          <span className="pres-stat-num tnum">{progress.missing}</span>
          <span className="micro">the map missed these</span>
        </div>
      </div>

      <div className="pres-points">
        <div className="pres-point">
          <p className="pres-point-num tnum">
            {(summary.conservative_ratio * 100).toFixed(0)}%
          </p>
          <p className="note">
            of the calls this program made were missing from its map. Nothing unusual was going
            on. This is the library doing its ordinary job, running its own tests.
          </p>
        </div>
        <div className="pres-point">
          <p className="pres-point-num tnum">{controlPct ?? "—"}%</p>
          <p className="note">
            of the straightforward calls were on the map. So the tool is not broken, and we are
            not testing it unfairly. It only loses track when the program decides which function
            to run while it is already running.
          </p>
        </div>
        <div className="pres-point">
          <p className="pres-point-num tnum">1</p>
          <p className="note">
            program measured so far. The method works and we have checked it. Measuring enough
            programs to say something about Python in general is the next stage of the project.
          </p>
        </div>
      </div>

      <p className="note note-faint">
        The library is <code className="mono">click</code>. A great many Python command line tools
        are built with it. We ran the 1,939 tests its own authors wrote, not tests we wrote to
        prove a point, and recorded every call that happened.
      </p>
    </div>
  );
}
