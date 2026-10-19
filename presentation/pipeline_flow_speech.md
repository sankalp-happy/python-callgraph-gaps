# Speaker Script — The Measurement Pipeline Flowchart

### One diagram, ~3 minutes. Same audience as `speaker_script.md`: CS faculty who know graphs and functions but not software-engineering tooling. Don't read it word for word — learn the shape and say it in your own voice.

---

**Opening — what the picture is (~20 sec)**

This one diagram is our entire method. Read it like a paragraph: left to right along the top, then it wraps like a line of text and comes back along the middle row, then wraps again to the bottom. Six numbered stages, two decision points, and one number at the end.

---

**Top row — getting to a corpus we can trust (~55 sec)**

Stage one, *discover*. We search GitHub for real Python projects — with one filter: the project has to carry a build file, meaning somebody intended it to be installable. That got us 558 candidates. Not toy examples. Working software.

Stage two, *score density*. We need to know how much of the tricky "decide at the last second" behaviour each project actually has, so we don't accidentally test only easy code. So we count those constructs and divide by size — that's what "per KLOC" means, per thousand source lines of code. It's a rate, not a total, so a large project doesn't look dynamic just for being large. And we count source only; we throw the test files out, because if you score tests too, every project that uses `pytest` looks maximally dynamic and the number tells you nothing. Out comes a label: LOW, MED or HIGH.

Stage three, *triage*, is duller than it sounds and matters more than anything else here. We take each project into a sealed container and ask a very boring question: does this thing install, and do its tests run? One repo, one Python version, one attempt — no retrying until it works, because retrying until it works is how you end up with a corpus that flatters you. Out comes GREEN, AMBER or RED, plus a lockfile that records the exact version of every package we installed.

Then the diamond: is it admitted? GREEN and AMBER go forward. RED does not get quietly deleted — and I want to be clear about that, because it's the honest part. A project we cannot run is itself a finding. Those get reported in the feasibility survey.

---

**Middle row — the two graphs (~50 sec)**

Notice the arrow wraps here, and the middle row reads *right to left*.

Stage four, *capture workloads*. For every admitted project, an annotator records at least three realistic ways of actually using it — the kind of thing a real user would run. Each one is verified twice, by two people. This is the part with no shortcut, and it's the most important thing on the diagram, because it becomes our oracle: the ground truth about what the software really does when it runs.

Stage five, *extract both graphs*, and here the path splits. On one side, the static route: we read the code without running it, using two published tools — PyCG and Pyright. That gives us the graph we call **S**. On the other side, the dynamic route: we actually execute the software, replaying exactly those recorded workloads, and watch every function call happen live. That gives us **R**.

And the crucial detail — both of those run inside the *same* sealed image. Same versions, same interpreter, same everything. Which means when S and R disagree, that disagreement is a fact about the code. It is not a fact about somebody's laptop.

---

**Bottom row — the number, and what we do with it (~40 sec)**

Wrap again, bottom row, stage six: *fuse and measure*. We overlay the two graphs and ask one question — of all the calls we actually watched happen, what fraction did reading the code alone manage to find? That's the fraction on the diagram: S intersect R, over R. And we only count the calls where a fair comparison is possible — both ends inside the project, both ends written in Python.

That fraction is our result. We call it H2a.

Then the last diamond, the Phase 3 decision. And I want to point at something on the right-hand side. There are two boxes there, and *both of them are outcomes we can publish*. If the miss rate is high, that's a warning to every AI tool that reads code for a living. If it's low, that's the more interesting result — because it means the misses are concentrated in a handful of specific constructs, and we can name them. Either way, we ship the benchmark.

---

**Closing — the line at the bottom (~20 sec)**

Three sentences at the bottom of the diagram, and they're the reason any of this counts as a measurement rather than a demo.

The host machine never traces — it only schedules work and checks results, so nothing about our own laptops leaks into the number. R is a lower bound, always, conditional on the workloads we recorded: we can prove a call happened, we can never prove one never happens. And the RED projects are reported, not dropped.

Every threshold in that picture was frozen in writing before we wrote the code that consumes it. That's deliberate. It means we cannot go back and tune anything once we've seen how the number looks.

---

## If the panel asks

- **"Why not just use a better static tool?"** — That's the point of the comparison, not a workaround for it. We use the field's standard baseline precisely so the number describes the state of the art, not a tool we picked to look bad.
- **"Isn't three workloads too few?"** — It's a floor, not a target, and it's why R is stated as a lower bound. More workloads can only move the measured recall down, never up, so the direction of the error is known.
- **"Why exclude built-in and third-party calls?"** — Because static and runtime don't even mean the same thing at that boundary. Restricting to in-project, Python-level calls is what makes the two graphs comparable at all. It's declared in the frozen spec, not chosen afterwards.
- **"What is KLOC again?"** — Thousand source lines of code: the denominator that turns a raw count into a rate. Floored at a thousand lines, because below that the division amplifies instead of normalising — a 29-line test fixture scored 701 before we put the floor in.
