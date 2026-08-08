import { useState } from "react";

/* ------------------------------------------------------------------ content */

type Status = "done" | "now" | "future";
type Chapter = { title: string; state?: "done" | "active" | "todo"; body: string[] };
type Phase = {
  n: string;
  title: string;
  weeks: string;
  status: Status;
  summary: string;
  chapters: Chapter[];
};

const PHASES: Phase[] = [
  {
    n: "0",
    title: "Write the rules down first",
    weeks: "Week 1",
    status: "done",
    summary:
      "Decide how we will measure, and lock it, before we have looked at a single result.",
    chapters: [
      {
        title: "Why the order matters so much",
        state: "done",
        body: [
          "Almost every definition in this study could be adjusted to make the final number bigger or smaller. Decide them afterwards and you are no longer measuring — you are hunting for the answer you wanted.",
          "So the three documents that define the measurement were written and locked before any of the code that uses them existed. Changing one now requires a new version number, a dated note explaining why, and re-running everything that depended on it. That is on purpose, and it is the main thing that will make a reviewer believe the result.",
        ],
      },
      {
        title: "Pinning every version",
        state: "done",
        body: [
          'Software is a moving target. Ask for "Python 3.12" today and next month you get a slightly different Python 3.12. Install a project\'s requirements twice, a week apart, and you get different versions of them.',
          "That would quietly ruin us. We compare a project's map against a recording of that same project running. If the two are made a week apart from different ingredients, we are comparing two different programs and the difference means nothing.",
          "So every ingredient is recorded by exact fingerprint, never by name. For each project we save the precise list of package versions used, plus a checksum of that list.",
        ],
      },
      {
        title: "Building and calibrating the sorting tool",
        state: "done",
        body: [
          "We need projects of varying difficulty, not all easy or all hard. So a tool reads each project and scores how much of the tricky behaviour it contains, sorting it into LOW, MEDIUM or HIGH.",
          "Its first version was useless — 10 of 14 test projects came out HIGH, which tells you nothing. Four separate causes were found and fixed, then the thresholds were locked. It now reproduces the same split every time: 6 HIGH, 4 MEDIUM, 3 LOW, 1 too small to use.",
          "It also corrected two of our own guesses. We expected one project to be LOW; it scored mid-range because it genuinely does the tricky thing we are studying. We wrote that down rather than quietly agreeing with ourselves.",
        ],
      },
      {
        title: "Rewriting the team instructions",
        state: "done",
        body: [
          "The original three instruction documents were good, but one whole task in them turned out to be pointless — a leftover from an earlier version of this research where the software was going to be in a different programming language. It is deleted, which returns roughly 30 person-days.",
          "Another task turned out to be something a script does perfectly, so it was automated. The people who were doing it moved to the task no script can do.",
        ],
      },
    ],
  },
  {
    n: "1",
    title: "Gather the projects, build the map-readers",
    weeks: "Weeks 2–4",
    status: "now",
    summary:
      "Find around 450 candidate projects, work out which still install and run, and build the tools that draw the map from the code.",
    chapters: [
      {
        title: "Finding the candidates",
        state: "active",
        body: [
          "A script searches for Python projects that are reasonably popular, still maintained, and have a test suite. For each one it records the exact version of the code as of the day the list was built — so the list cannot drift underneath us.",
          "It then clones each project, scores its difficulty, and deletes the copy. The result is a queue where LOW, MEDIUM and HIGH projects alternate. That ordering matters: if we only get through 60% of the list we still have all three difficulty levels. Sorted by difficulty instead, an unfinished run would leave us with no HIGH projects at all — and HIGH is the group the whole study depends on.",
          "This is running now, on a teammate's machine.",
        ],
      },
      {
        title: "Checking which projects actually run",
        state: "todo",
        body: [
          'Most old software no longer installs. That is expected, and a "no" is worth just as much to us as a "yes" as long as it is recorded properly — the collected reasons for failure become a published finding in their own right.',
          "Each project gets one of three verdicts. GREEN means it installs and all its tests pass. AMBER means it installs and runs but some tests fail. RED means it would not build at all.",
          "AMBER counts as usable, and that decision is worth understanding: we need software that runs, not software that passes. A failing test still executes code, and executing code is exactly what we watch. Throwing AMBER away would have discarded an estimated 20–40% of a perfectly good collection.",
        ],
      },
      {
        title: "The piece we are stuck on",
        state: "todo",
        body: [
          "Four things had to be finished before this phase could really get going. One is done. The remaining three: pin down the version of one analysis tool, install a second one and measure how often it fails to read modern code, and build the queue-runner that triages projects automatically and unattended.",
          "That last one is the real blocker, because it is what unblocks everyone else.",
        ],
      },
      {
        title: "Why one tool's failures are themselves a result",
        state: "todo",
        body: [
          "One of the two map-readers we compare against is the standard published tool in this field. It is several years old and may simply crash on code written with newer language features.",
          "We are not going to hide that or work around it. How often the field's own standard tool cannot read contemporary code is a genuine finding about the state of the art, so every failure gets logged and reported.",
        ],
      },
    ],
  },
  {
    n: "2",
    title: "Watch the programs run",
    weeks: "Weeks 3–6",
    status: "future",
    summary:
      "Record every connection that actually happens while each project runs, and store the recordings in a form we can search.",
    chapters: [
      {
        title: "How the watching works",
        body: [
          "Python has a built-in facility for reporting every function call as it happens. We switch it on, run the project, and write down every connection we see along with which run it came from.",
          "Newer Python has a fast version of this; older Python only has a slower one. Projects that had to be rescued onto an older version therefore carry a heavier slowdown, so we will report the cost separately for each version rather than as one blended figure that hides the difference.",
        ],
      },
      {
        title: "Running everything twice",
        body: [
          "Programs are not perfectly repeatable. Timing, randomness, and the order things happen in can all vary between two runs of the same thing.",
          "So every recording is made twice and the two are compared. A connection that only showed up once gets flagged as unreliable, and we report our results both with and without those. It is a cheap defence against building conclusions on noise.",
        ],
      },
      {
        title: "What we are careful not to claim",
        body: [
          "We only see connections that happen in the situations we knew how to run. There will always be parts of a program nothing we did touched.",
          'So we never say "this is everything the program does." We say it is a floor — at least this much happens — and that wording is required in every table and caption, not tucked away at the end. Overclaiming here is the single most likely way to get the paper rejected.',
        ],
      },
    ],
  },
  {
    n: "3",
    title: "Compare, and get the number",
    weeks: "Weeks 5–8",
    status: "future",
    summary:
      "Line the recordings up against the maps, produce the headline result, and decide honestly whether to continue.",
    chapters: [
      {
        title: "The actual comparison",
        body: [
          "For each project we now have two sets of connections: the ones a tool drew from reading the code, and the ones we saw while it ran. The headline number is simply how much of the second set is missing from the first.",
          "It gets reported broken down by difficulty level and by the kind of connection, never as a single average on its own. An average alone can hide the entire story.",
        ],
      },
      {
        title: "Three ways this could produce a fake number",
        body: [
          "Each of these was written down and ruled out in advance, before the code existed.",
          'First: connections into code that is not part of the project — built-in functions, other people\'s libraries. Tools never claimed to map those, so counting them as "missed" would invent an enormous number out of nothing. They are excluded by definition.',
          "Second: a common Python feature causes the recording to show two steps where the tool shows one. Naively subtracting would manufacture two fake misses for every single use of it. The rule for collapsing that back down was written before any recording was made.",
          'Third: a connection the tool drew but we never saw is not proof the tool was wrong — it may be real code our runs never reached. We refuse to call that an error, and we deliberately never use the word "precision" for it anywhere.',
        ],
      },
      {
        title: "The honest checkpoint",
        body: [
          "At the end of this phase there is a genuine stop-or-continue decision. If the answer turns out to be that these tools miss almost nothing, the follow-on work is pointless and we stop.",
          "That is not a bad outcome. It is a finding, it is publishable, and discovering it cheaply at week 8 rather than expensively at week 12 is exactly why the phase boundary sits here.",
        ],
      },
    ],
  },
  {
    n: "4",
    title: "Does it actually matter?",
    weeks: "Weeks 8–11",
    status: "future",
    summary:
      "Test whether giving an AI the missing connections changes what it can do — including a control group where we predict no change at all.",
    chapters: [
      {
        title: "The experiment",
        body: [
          "Knowing connections are missing is one thing. Showing it changes outcomes is another. So we give an AI the same task twice — once with the map alone, once with the map plus the connections we recorded — and compare.",
          "Everything else stays identical: same task, same instructions, same amount of information. The only difference is which connections exist. That is what makes the comparison mean something.",
        ],
      },
      {
        title: "The control group, and why it is the best part",
        body: [
          "We also run the same test on projects with almost no tricky behaviour, where we predict the extra connections make no difference whatsoever.",
          'If we are right and nothing improves there, that is far stronger evidence than the main result alone. "We added data and things got better" is weak — it could just be more information helping. "Things got better exactly where we predicted and nowhere else" identifies the actual cause.',
          "We write that prediction down before running the test, so we cannot quietly reinterpret the outcome afterwards.",
        ],
      },
      {
        title: "This phase is optional by design",
        body: [
          "Everything through Phase 3 is already a complete paper. Phase 4 adds to it rather than completing it.",
          "That is deliberate. If twelve weeks turns out to be optimistic, this is the first thing cut — and the order of cuts was agreed in advance, while nobody was under pressure, precisely so it is not argued about later.",
        ],
      },
    ],
  },
  {
    n: "5",
    title: "Release it and write it up",
    weeks: "Weeks 10–12",
    status: "future",
    summary:
      "Publish the collection so other researchers can re-run the measurement, and write the paper.",
    chapters: [
      {
        title: "What gets released",
        body: [
          "The project list with exact versions, the recipes for running each one, the recorded connections, and the tools. Anyone can take it and check our number, or measure something we did not think of.",
          "Benchmarks tend to outlive the methods that produced them. Of everything here, this is the part most likely to still be in use in five years.",
        ],
      },
      {
        title: "Including the failures",
        body: [
          "Projects that would not build, and projects we could not record, stay in the release with a status explaining why.",
          "Removing them would be tempting and would make the collection look cleaner. It would also make it a biased sample of only the cooperative software, quietly misleading everyone who used it afterwards.",
        ],
      },
    ],
  },
];

const ROLES: { who: string; task: string; note: string }[] = [
  {
    who: "Research partner",
    task: "Building the candidate list",
    note: "Running the search, scoring and queue-building on a 150 GB machine. Produces nothing that can conflict with anyone else's work, which is why it was safe to hand out first.",
  },
  {
    who: "Annotator — build checks",
    task: "Checking the automation by hand",
    note: "Triages a sample of projects manually so we can measure how often the automated verdict is right. Disagreeing with the script is the point, not a problem.",
  },
  {
    who: "Annotator — documentation",
    task: "Finding settings, then finding commands",
    note: "First: which configuration settings each project's documentation mentions. Then: which commands look like they would actually run each project. Browser work, no setup needed.",
  },
  {
    who: "Engineer",
    task: "The automatic queue-runner",
    note: "The piece everything else waits on. Until it exists, triage cannot run at scale and the workload-recording task stays blocked.",
  },
];

const GLOSSARY: { term: string; plain: string }[] = [
  {
    term: "Call graph",
    plain:
      "A map of which piece of code calls which other piece. The thing this whole study is about the quality of.",
  },
  {
    term: "Static",
    plain: "Worked out by reading the code without running it. Fast, and what almost everyone uses.",
  },
  {
    term: "Runtime / dynamic",
    plain:
      "Observed while the program is actually running. Slower and more work, but it sees things reading cannot.",
  },
  {
    term: "Triage",
    plain:
      "Checking whether a project still installs and runs today, and recording the verdict as GREEN, AMBER or RED.",
  },
  {
    term: "GREEN / AMBER / RED",
    plain:
      "Installs and passes / installs and runs but some tests fail / would not build. The first two are both usable.",
  },
  {
    term: "Difficulty level",
    plain:
      "LOW, MEDIUM or HIGH — how much of the tricky behaviour a project contains. Used to keep the collection balanced.",
  },
  {
    term: "Workload",
    plain:
      "A specific, written-down way of running a project — the exact command, verified to work twice. What we record connections from.",
  },
  {
    term: "Pinning",
    plain:
      "Recording an exact fingerprint of every ingredient instead of its name, so the same thing can be rebuilt later.",
  },
  {
    term: "The benchmark",
    plain:
      "The public release: projects, recipes, recorded connections and tools, packaged so anyone can re-run the measurement.",
  },
];

/* --------------------------------------------------------------- components */

/* viewBox is 600 units wide so it renders near 1:1 — SVG text scales with the
   viewBox, and a small one magnifies labels and strokes well past their size. */
const NODES = [
  { x: 104, y: 74, label: "login" },
  { x: 496, y: 74, label: "billing" },
  { x: 300, y: 200, label: "report" },
  { x: 112, y: 322, label: "email" },
  { x: 492, y: 322, label: "plugin" },
];
const DRAWN: [number, number][] = [
  [0, 2],
  [1, 2],
  [2, 3],
  [0, 3],
];
const MISSED: [number, number][] = [
  [2, 4],
  [4, 1],
];

function GraphPanel({ observed }: { observed: boolean }) {
  return (
    <svg
      viewBox="0 0 600 372"
      role="img"
      aria-label={
        observed
          ? "The same five pieces of code, now with two extra connections shown as dashed lines: report to plugin, and plugin to billing."
          : "Five pieces of code with four connections drawn between them."
      }
    >
      {DRAWN.map(([a, b], i) => (
        <line
          key={`d${i}`}
          x1={NODES[a].x}
          y1={NODES[a].y}
          x2={NODES[b].x}
          y2={NODES[b].y}
          stroke="var(--steel)"
          strokeWidth="2"
        />
      ))}
      {observed &&
        MISSED.map(([a, b], i) => (
          <line
            key={`m${i}`}
            x1={NODES[a].x}
            y1={NODES[a].y}
            x2={NODES[b].x}
            y2={NODES[b].y}
            stroke="var(--accent)"
            strokeWidth="2.75"
            strokeDasharray="10 6"
          />
        ))}
      {NODES.map((n, i) => (
        <g key={n.label}>
          <rect
            x={n.x - 6.5}
            y={n.y - 6.5}
            width="13"
            height="13"
            fill="var(--paper)"
            stroke={observed && (i === 1 || i === 2 || i === 4) ? "var(--accent)" : "var(--ink)"}
            strokeWidth="2.25"
          />
          <text
            x={n.x}
            y={n.y + 26}
            textAnchor="middle"
            fill="var(--ink-soft)"
            fontFamily="var(--font-mono)"
            fontSize="13.5"
            fontWeight="600"
          >
            {n.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

function PhaseBlock({
  phase,
  open,
  onToggle,
}: {
  phase: Phase;
  open: boolean;
  onToggle: () => void;
}) {
  const s = phase.status;
  const spine = s === "done" ? "spine-solid" : s === "now" ? "spine-now" : "spine-dashed";
  const node = s === "done" ? "node-done" : s === "now" ? "node-now" : "node-future";
  const num = s === "done" ? "phase-num-done" : s === "now" ? "phase-num-now" : "";
  const pill = s === "done" ? "pill-done" : s === "now" ? "pill-now" : "pill-future";
  const pillText = s === "done" ? "Complete" : s === "now" ? "We are here" : "Not started";

  return (
    <div className="phase-row">
      <div className={`spine ${spine}`}>
        <div className={`node ${node}`} />
      </div>

      <div>
        <button className="phase-head" onClick={onToggle} aria-expanded={open} aria-controls={`ch-${phase.n}`}>
          <span className={`phase-num ${num}`} aria-hidden="true">
            {phase.n}
          </span>
          <span className="stack gap-1" style={{ minWidth: 0 }}>
            <span className="micro faint">
              Phase {phase.n} · {phase.weeks}
            </span>
            <h3>{phase.title}</h3>
            <span className="small soft" style={{ maxWidth: "34rem" }}>
              {phase.summary}
            </span>
            <span style={{ marginTop: ".3rem" }}>
              <span className={`pill ${pill}`}>{pillText}</span>
            </span>
          </span>
          <span className="toggle" aria-hidden="true">
            {open ? "−" : "+"}
          </span>
        </button>

        {open && (
          <div className="chapters" id={`ch-${phase.n}`}>
            {phase.chapters.map((c) => (
              <div className="chapter" key={c.title}>
                <div className="chapter-title-row">
                  <span
                    className="tick"
                    style={{
                      color:
                        c.state === "done"
                          ? "var(--ok)"
                          : c.state === "active"
                          ? "var(--accent)"
                          : "var(--ink-faint)",
                    }}
                    aria-hidden="true"
                  >
                    {c.state === "done" ? "✓" : c.state === "active" ? "▸" : "·"}
                  </span>
                  <h4>{c.title}</h4>
                </div>
                <div className="chapter-body soft small">
                  {c.body.map((p, i) => (
                    <p key={i}>{p}</p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------- page */

export default function App() {
  const [open, setOpen] = useState<Record<string, boolean>>({ "1": true });
  const allOpen = PHASES.every((p) => open[p.n]);
  const toggle = (n: string) => setOpen((o) => ({ ...o, [n]: !o[n] }));
  const toggleAll = () => setOpen(allOpen ? {} : Object.fromEntries(PHASES.map((p) => [p.n, true])));

  return (
    <div className="page">
      <header className="masthead">
        <div className="wrap stack gap-4">
          <div className="stack gap-3">
            <div className="rule-heavy" style={{ maxWidth: "5rem" }} />
            <p className="eyebrow" style={{ margin: 0 }}>
              Empirical software-engineering study · twelve weeks
            </p>
            <h1>
              The map is
              <br />
              missing roads
            </h1>
            <p className="deck">
              We are measuring how many real connections inside a program the standard
              code-reading tools never draw — and whether the ones they miss follow a pattern.
            </p>
          </div>

          <dl className="facts">
            {[
              ["Project", "TraceWeave-Core"],
              ["Started", "27 Jul 2026"],
              ["Deadline", "26 Oct 2026"],
              ["Team", "1 engineer, 3 others"],
              ["Complete", "Phase 0"],
              ["In progress", "Phase 1"],
            ].map(([k, v]) => (
              <div className="fact" key={k}>
                <dt className="micro faint">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      </header>

      <section>
        <div className="wrap stack gap-4">
          <div className="stack gap-1">
            <p className="eyebrow" style={{ margin: 0 }}>
              The idea in one page
            </p>
            <h2>What we are actually doing</h2>
          </div>

          <div className="prose lead">
            <p>
              Software that has been running a business for twenty years is expensive to replace
              and risky to change. Before anyone can change it safely they need a map: which piece
              of the program calls which other piece.
            </p>
            <p>
              Tools exist that produce that map by <b>reading</b> the code, without ever running
              it. They are fast, and they are what almost everyone uses — including the AI tools
              now being pointed at old software.
            </p>
            <p>
              But some connections are not written down anywhere in the code. They only appear
              while the program is running: a piece of code decides <i>at that moment</i> which
              other piece to call, based on a setting in a file, or a plugin somebody installed, or
              a name assembled out of text. A tool that only reads the code cannot see those. They
              are real, they happen every day, and they are missing from the map.
            </p>
          </div>

          <div className="analogy prose">
            <p>
              <b>Think of a building's floor plan.</b> It shows every door and corridor. Now watch
              where people actually walk for a week. They cut through the unmarked service door.
              They use a shortcut between two offices that is not on the plan.
            </p>
            <p>Renovate from the plan alone and you will wall off a route the building depends on.</p>
            <p>
              The floor plan is what code-reading tools produce. Watching people walk is what we
              do. Renovating is what AI tools are increasingly being asked to do.
            </p>
          </div>

          <div className="prose lead">
            <p>
              So the question is simply this:{" "}
              <b>
                how many connections are missing, and are they scattered at random or clustered in
                a few specific, nameable situations?
              </b>
            </p>
          </div>
        </div>
      </section>

      <section>
        <div className="wrap stack gap-3">
          <div className="stack gap-1">
            <p className="eyebrow" style={{ margin: 0 }}>
              The same program, two ways
            </p>
            <h2>Where the gap shows up</h2>
          </div>

          <div className="diagram-pair">
            <div className="diagram-cell">
              <p className="micro faint" style={{ margin: 0 }}>
                What the tool draws
              </p>
              <GraphPanel observed={false} />
              <p className="small soft" style={{ margin: 0 }}>
                Four connections, all of them written plainly in the code.
              </p>
            </div>
            <div className="diagram-cell">
              <p className="micro" style={{ margin: 0, color: "var(--accent-ink)" }}>
                What actually happened
              </p>
              <GraphPanel observed />
              <p className="small soft" style={{ margin: 0 }}>
                The same four, plus two we only saw by running it. Nothing in the code says{" "}
                <span className="mono">report</span> will call <span className="mono">plugin</span>{" "}
                — that gets decided while it runs.
              </p>
            </div>
          </div>

          <div className="legend small soft">
            <span className="legend-item">
              <span
                className="legend-line"
                style={{ borderTopStyle: "solid", borderTopColor: "var(--steel)" }}
              />
              Found by reading the code
            </span>
            <span className="legend-item">
              <span
                className="legend-line"
                style={{ borderTopStyle: "dashed", borderTopColor: "var(--accent)" }}
              />
              Only visible while running
            </span>
          </div>

          <div className="card card-accent prose">
            <p className="small" style={{ margin: 0 }}>
              <b>Why anyone should care.</b> An AI asked to rewrite{" "}
              <span className="mono">plugin</span> works from the left-hand picture. It has no way
              to know <span className="mono">billing</span> depends on it. The rewrite passes its
              tests and quietly breaks billing in production — the kind of failure that never shows
              up until it is expensive.
            </p>
          </div>
        </div>
      </section>

      <section>
        <div className="wrap stack gap-4">
          <div className="stack gap-1">
            <p className="eyebrow" style={{ margin: 0 }}>
              The point of all this
            </p>
            <h2>What would count as success</h2>
          </div>

          <p className="lead" style={{ margin: 0, maxWidth: "40rem" }}>
            Three things — and notably, none of them is <i>getting a big number</i>.
          </p>

          <div className="grid-3">
            <div className="card stack gap-2">
              <span className="micro faint">First</span>
              <h3>A number we can defend</h3>
              <p className="small soft" style={{ margin: 0 }}>
                Whichever way it comes out, it is worth publishing. If tools miss 30% of
                connections, that is a significant finding. If they miss only 8%, that is{" "}
                <i>also</i> a finding — "these tools are more complete than the field assumes" is
                useful, and nobody has measured it properly.
              </p>
            </div>
            <div className="card stack gap-2">
              <span className="micro faint">Second</span>
              <h3>A named cause, not just a number</h3>
              <p className="small soft" style={{ margin: 0 }}>
                A 14% miss rate sitting almost entirely in one identifiable situation is a{" "}
                <b>better</b> result than a scattered 30%. The first tells you where to look; the
                second just says "this is hard". We are hoping for the concentrated answer.
              </p>
            </div>
            <div className="card stack gap-2">
              <span className="micro faint">Third</span>
              <h3>Something others reuse</h3>
              <p className="small soft" style={{ margin: 0 }}>
                We release the project list, the exact recipes for running them, and the recorded
                connections. Benchmarks tend to outlive the methods that produced them — this is
                the part most likely to still matter in five years.
              </p>
            </div>
          </div>

          <div className="card card-accent prose">
            <h3 style={{ marginBottom: ".5rem" }}>Why this study cannot come back empty</h3>
            <p className="small soft" style={{ margin: 0 }}>
              We are measuring a property of <b>programs</b>, not of AI models. Program behaviour
              does not change because a company shipped a new model or changed its prices. So there
              is a real result waiting at the end whichever way it goes. That was the deciding
              factor in choosing this study: the alternative plan on the table depended on
              comparing against a commercial AI model whose capability and cost would both have
              moved before we could publish.
            </p>
          </div>

          <div className="stack gap-2">
            <h3>And what would count as failure</h3>
            <p className="small soft" style={{ maxWidth: "38rem", margin: 0 }}>
              Not "the number was small". These three — each of which a written rule now guards
              against:
            </p>
            <ul className="checklist small soft" style={{ maxWidth: "40rem" }}>
              <li>
                <span className="marker marker-no">✗</span>
                <span>
                  <b>Adjusting a definition after seeing the results</b> to move the number. That
                  turns a measurement into a search for the answer we wanted.
                </span>
              </li>
              <li>
                <span className="marker marker-no">✗</span>
                <span>
                  <b>Quietly dropping projects that will not cooperate.</b> That would make the
                  released collection a sample of only the easy software, which misleads everybody
                  who uses it afterwards.
                </span>
              </li>
              <li>
                <span className="marker marker-no">✗</span>
                <span>
                  <b>Publishing speed measurements from a machine that cannot produce reliable
                  ones.</b>{" "}
                  Ours cannot, for reasons to do with how it runs containers, so we only ever
                  report ratios rather than raw times.
                </span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section>
        <div className="wrap stack gap-3">
          <div
            style={{
              display: "flex",
              alignItems: "flex-end",
              justifyContent: "space-between",
              gap: "1rem",
              flexWrap: "wrap",
            }}
          >
            <div className="stack gap-1">
              <p className="eyebrow" style={{ margin: 0 }}>
                Six phases (0–5) · twelve weeks
              </p>
              <h2>The plan, and where we are in it</h2>
            </div>
            <button
              onClick={toggleAll}
              className="micro"
              style={{
                background: "none",
                border: "1px solid var(--rule)",
                color: "var(--ink-soft)",
                padding: ".45rem .7rem",
                cursor: "pointer",
              }}
            >
              {allOpen ? "Collapse all" : "Expand all"}
            </button>
          </div>

          <p className="small soft" style={{ maxWidth: "38rem", margin: 0 }}>
            The line runs solid where the project has already been, and dashed where it has not.
            Open any phase for the detail.
          </p>

          <div style={{ marginTop: ".75rem" }}>
            {PHASES.map((p) => (
              <PhaseBlock key={p.n} phase={p} open={!!open[p.n]} onToggle={() => toggle(p.n)} />
            ))}
          </div>

          <div className="card card-accent prose" style={{ marginTop: "1.5rem" }}>
            <h3 style={{ marginBottom: ".5rem" }}>The week-8 seam is deliberate</h3>
            <p className="small soft" style={{ margin: 0 }}>
              Phases 0 to 3 already add up to a complete paper on their own. Phases 4 and 5 are
              additions to it. That was designed in from the start so that running out of time
              costs us extra findings rather than the whole result — and the order things get cut
              in was agreed while nobody was under pressure.
            </p>
          </div>
        </div>
      </section>

      <section>
        <div className="wrap stack gap-3">
          <div className="stack gap-1">
            <p className="eyebrow" style={{ margin: 0 }}>
              Right now
            </p>
            <h2>Who is doing what</h2>
          </div>
          <div className="rows">
            {ROLES.map((r) => (
              <div className="row-2col" key={r.who}>
                <div className="stack gap-1">
                  <span className="micro faint">{r.who}</span>
                  <h4>{r.task}</h4>
                </div>
                <p className="small soft" style={{ margin: 0 }}>
                  {r.note}
                </p>
              </div>
            ))}
          </div>
          <p className="small soft" style={{ maxWidth: "38rem", margin: 0 }}>
            Two tasks are blocked until the queue-runner exists: recording how each project is run,
            and reviewing the handful of licences a script could not identify.
          </p>
        </div>
      </section>

      <section>
        <div className="wrap stack gap-4">
          <div className="stack gap-1">
            <p className="eyebrow" style={{ margin: 0 }}>
              Team culture, stated plainly
            </p>
            <h2>Why we are strict about small things</h2>
          </div>

          <div className="grid-2">
            <div className="stack gap-2">
              <h3>A "no" is worth as much as a "yes"</h3>
              <p className="small soft" style={{ margin: 0 }}>
                Most of the software we look at will not install. Most projects will document no
                settings. Many will have no obvious way to run them. None of that is a bad day's
                work — every one of those is a recorded data point, and the collected failures
                become a published finding.
              </p>
              <p className="small soft" style={{ margin: 0 }}>
                Nobody is measured on how many projects come out well. Trying to make projects work
                in order to get better-looking results would actively damage the dataset.
              </p>
            </div>
            <div className="stack gap-2">
              <h3>The one thing that genuinely hurts</h3>
              <p className="small soft" style={{ margin: 0 }}>
                Recording something as verified when it was not. A command nobody actually ran, a
                setting nobody actually saw, an answer nudged to match what a script probably said.
              </p>
              <p className="small soft" style={{ margin: 0 }}>
                Everything else here is easy to fix later. That is not, because afterwards nobody
                knows which rows to distrust. When in doubt the honest answer — including "I am not
                sure" — is always the right one, and every form has a value that means exactly
                that.
              </p>
            </div>
          </div>

          <div className="stack gap-2">
            <h3>Three rules that protect the result</h3>
            <ul className="checklist small soft" style={{ maxWidth: "40rem" }}>
              <li>
                <span className="marker marker-yes">✓</span>
                <span>
                  <b>Never refer to an ingredient by name, only by fingerprint.</b> Names point at
                  different things over time. Fingerprints do not.
                </span>
              </li>
              <li>
                <span className="marker marker-yes">✓</span>
                <span>
                  <b>Never edit a locked definition to fit a result.</b> Changing one needs a new
                  version, a dated note, and re-running whatever relied on it.
                </span>
              </li>
              <li>
                <span className="marker marker-yes">✓</span>
                <span>
                  <b>Never remove a project silently.</b> Anything excluded is listed with a
                  reason, every time.
                </span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section>
        <div className="wrap stack gap-3">
          <div className="stack gap-1">
            <p className="eyebrow" style={{ margin: 0 }}>
              Reference
            </p>
            <h2>Words you will hear, in plain English</h2>
          </div>
          <div className="rows">
            {GLOSSARY.map((g) => (
              <div className="row-2col" key={g.term}>
                <h4>{g.term}</h4>
                <p className="small soft" style={{ margin: 0 }}>
                  {g.plain}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer>
        <div className="wrap stack gap-2">
          <p className="eyebrow" style={{ margin: 0 }}>
            TraceWeave-Core
          </p>
          <p className="small soft" style={{ maxWidth: "38rem", margin: 0 }}>
            Phase 0 complete. Phase 1 underway — the candidate list is being generated now, and
            three of its four blocking items remain. Phases 2 to 5 not started.
          </p>
          <p className="small faint" style={{ maxWidth: "38rem", margin: 0 }}>
            Questions about any of this are welcome and cheap. Guessing is expensive.
          </p>
        </div>
      </footer>
    </div>
  );
}
