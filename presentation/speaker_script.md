# Speaker Script — TraceWeave-Core Phase-II Interim
### Written for a review panel of CS faculty with basic knowledge of graphs and functions, not deep software engineering. ~1 minute per slide, ~16 minutes total.

A quick note before you rehearse this: don't read it word for word. Read it twice, pull out the shape of each slide's argument, and say it in your own voice. The jokes and asides are there so it doesn't sound like you're reciting — keep whichever ones feel natural to you and drop the rest.

---

## Slide 1 — Title
**~40 sec**

Good [morning/afternoon], everyone. Thanks for having us. I'm going to try to get you excited about something that sounds, on paper, incredibly dry: whether a piece of software analysis tool is lying to us, and by how much.

Here's the one-sentence version of this whole project. When you read code without running it, you miss things — and nobody has actually put a number on how much you miss, on real software. That's what we spent the last few weeks measuring. [Introduce team and guide from the slide.] Let's get into it.

---

## Slide 2 — Contents
**~30 sec**

Quick map of where we're going. First, the problem and why it actually matters — not just for us, but for anyone building AI tools that read code. Then how we measured it, which is honestly the part we're proudest of, because we were paranoid about doing it honestly. Then a live demo, the numbers Phase 0 actually produced, where our paper submission stands, an honest comparison of what we promised versus what we delivered, and who did what. Ten sections, should take about fifteen minutes.

---

## Slide 3 — Problem Statement & Objective
**~75 sec**

Let's start with something you already know: a graph is just dots and lines — nodes and edges. Now imagine the nodes are functions in a computer program, and an edge means "this function calls that one." That's called a call graph. It's basically a map of who talks to whom inside a piece of software.

Here's the catch. There are two ways to build that map. One is to *read* the code — never run it, just look at the text and guess what calls what. That's called static analysis, and it's fast and safe. The other is to actually *run* the program and watch, in real time, which functions genuinely get called. That's dynamic, or runtime, analysis.

Python — the language most of this software is written in — has a nasty habit of deciding, at the very last second, which function to call, based on data it's holding right then. Think of a mail sorter that doesn't have a printed route for every letter; instead it reads the name on the envelope the instant it arrives and decides where it goes on the spot. A tool that only reads code can't see that decision happening — it just sees "something gets called here" and has to guess.

Nobody has rigorously measured how often that guess is wrong on real, working software. That's our target. We call it H2a for short, and our four goals are: measure how much gets missed, figure out *which kinds* of code cause the misses, publish a reusable benchmark so others can check our work, and honestly report what it costs to even attempt this at scale.

---

## Slide 4 — Flow / Methodology — The Pipeline (1 of 2)
**~65 sec**

So how do you actually measure this without fooling yourself? Six steps.

First, we go find real Python projects on GitHub — not toy examples, actual working software. Second, we score each one for how much of that "last-second decision" behavior it has, so we're not accidentally testing only simple code. Third — and this is duller than it sounds but matters enormously — we check whether each project even *installs and runs* in the first place. A shocking number of real repositories don't, out of the box.

Fourth, for the ones that do run, we record real ways of actually using them — like scripts a real user would run. Fifth, we build both graphs: the static one, using an existing published tool, and the dynamic one, by actually executing the code and watching every function call happen live. Sixth, we compare them.

The one rule that ties all of this together: every single step runs inside a locked, frozen software environment — same exact versions, every time, never trust the version that happens to be sitting on someone's laptop that day. That's what makes the eventual number trustworthy instead of a fluke.

---

## Slide 5 — Flow / Methodology — What Makes It a Measurement (2 of 2)
**~70 sec**

Here's the part I'd genuinely ask you to remember, even if nothing else sticks: we wrote down our rules *before* we had any results. The exact definition of "what counts as a real call," the exact list of things we're allowed to compare, the exact formula for the final number — all locked and dated, weeks before any measurement happened.

Why bother? Because it's exactly like sealing an exam's marking scheme before you've seen a single student's answer sheet. If you write the rubric after you've already peeked at the answers, nobody should trust your grading — even if you didn't consciously cheat. Same principle here. We can't quietly redefine "success" after seeing whether our number looks good or bad.

A couple of specific honesty rules we committed to: we never call our comparison "precision," because we can't actually prove a static tool guessed *wrong* — only that we didn't see it happen at runtime. And no AI model is ever used to judge whether our own results are correct. That would be a bit like asking a student to grade their own exam.

---

## Slide 6 — Demo of Project
**~65 sec**

Let me show you the smallest possible version of this problem, live. We have a tiny toy program — a plugin system, maybe fifteen lines of code — that decides which function to run based on a name it looks up at the very last moment, that "mailroom" trick I mentioned earlier.

We run the static reader on it, and we run the real thing and watch it execute. Here's what happens: the static reader correctly spots two of the three real connections in the program. The third one — the one where the plugin system actually hands an email off to its handler — happens purely because of that last-second name lookup. The static tool never sees it. It's invisible to a tool that only reads code, even though it happens every single time you actually run the program.

That's the entire hypothesis of this project, shrunk down to fit on one screen. Now imagine doing this same comparison across hundreds of real, much bigger repositories instead of one fifteen-line toy — that's the number we're building toward.

---

## Slide 7 — Results / Output — Phase 0, Measured
**~70 sec**

So what did the first phase of the project actually produce? A few honest numbers.

We found and scored 558 real candidate repositories — we'd only promised about 450, so we're ahead there. And here's a finding we did not expect going in: the standard, widely-cited static analysis tool the whole field uses — completely fails, one hundred percent of the time, on the newer version of Python this project defaults to. Not fails a little — fails on every single file. On the slightly older Python version, it's a much more reasonable one-point-six percent failure rate on real library code. That gap between one hundred percent and one-point-six percent is itself a finding worth reporting, and we're reporting it rather than quietly hiding it.

We also caught real bugs by actually running things instead of just planning them on paper — including one where a bug-fix we wrote accidentally made a test-counting number nearly seventeen times too large, and we only caught it because we double-checked against a known-correct answer. That habit — trust nothing, verify everything twice — is the actual theme of Phase 0.

---

## Slide 8 — Status of Paper (1 of 2)
**~55 sec**

Two papers, two different stages. The first is a literature review the same team wrote earlier — a survey of existing research on AI tools that try to modernize old software — and that one is currently under review at [venue name]. It's the paper that originally pointed us at this exact gap in the field; one specific finding in it is what this whole project is built to go test properly.

The second paper is this project itself — still being written, because it's gated on getting real numbers out of Phase 3 before we can honestly claim anything. And here's something I actually like about how we've set this up: whichever way the number comes out, it's publishable. A small miss rate that's concentrated in one specific kind of code is, if anything, a *stronger* result than a big messy one, because it tells people exactly what to go fix.

---

## Slide 9 — Status of Paper — Proof (2 of 2)
**~35 sec**

And because "under review" is an easy thing to just say, this slide is where the actual proof goes — the submission confirmation, with reviewer names and any personal email addresses blacked out before anyone sees this slide. The checklist here is basically what any of you would ask to see if a student told you they'd submitted a paper: title, full author list, venue, an ID, and a timestamp. We'd rather show you the receipt than ask you to take our word for it.

---

## Slide 10 — Proposed vs Actual Outcome (1 of 2)
**~65 sec**

This is the slide where we hold ourselves to what we promised at the start. Every single commitment we made for this phase — discovering enough candidate repositories, keeping a healthy mix of simple and complex code in our sample, locking down our tool versions, measuring the failure rate I mentioned earlier, building the automation that runs everything — every one of those, met. Not "mostly met." Met, and in most cases beaten.

The two rows marked "next" aren't us falling behind — they're just honestly labeled as belonging to later phases. Building the full corpus of usable repositories and actually producing the headline number both depend on work that hasn't started yet by design, not because we're late. We wanted this table to be something you could interrogate line by line, not a slide that just says "everything's great."

---

## Slide 11 — What the Plan Did Not Predict (2 of 2)
**~70 sec**

No plan survives contact with real code, and I think it's more honest to show you where we were wrong than to pretend the plan was perfect.

The static analysis tool doesn't just struggle with the newer Python — it fails completely, and it turns out the way that tool is packaged is actually broken on the operating system we use for everything, and had been quietly working only by luck on one particular kind of computer. We also discovered partway through that the laptop we started developing on physically cannot handle building the full dataset — not enough memory — so we had to explicitly split the work between a development machine and a proper server. And I already mentioned the counting bug that inflated a number by nearly seventeen times; we caught that one during our own double-checking process, which is exactly why that process exists.

None of these were fun to discover. All of them are now written down, fixed, and carried forward as open items rather than swept under the rug.

---

## Slide 12 — Conclusion, Deliverables & Impact
**~65 sec**

So, pulling it together. What we know so far: the plan is ahead of schedule, and the field's go-to static analysis tool has a much bigger blind spot on modern Python than anyone seems to have written down before us.

What we're actually going to hand over at the end of this: not just a number in a paper, but a reusable kit — the pinned repositories, the recorded ways of running them, the reference call graphs, and the tooling to redo all of it. Benchmarks like that tend to outlive the specific paper they came from; people keep using the dataset long after they've stopped citing the original claim.

And why should anyone outside this room care? Because right now, AI coding assistants are increasingly given a map of a codebase and trusted to reason about it. If that map has holes nobody's measured, the assistant is confidently wrong in a way that's very hard to catch. We're trying to put an actual number on how big those holes are.

---

## Slide 13 — Individual Responsibilities
**~40 sec**

Quickly, who did what. [Member 1] owned finding and scoring the candidate repositories — the discovery and filtering pipeline. [Member 2] built the automation that checks whether each project actually installs and runs. [Member 3] handled getting the static analysis tools working correctly inside our locked environment. [Member 4] built the runtime tracer, the live demo you just saw, and wrote the formal specification that ties the whole measurement together. Our guide, [Guide Name], signed off on every one of our frozen decisions and will be approving the go/no-go before we move to the final measurement phase.

---

## Slide 14 — Gantt Chart
**~55 sec**

I want to draw your attention to something specific about this chart, because the old version of it made it look like almost nothing had happened yet. It hadn't — the chart was just organized the wrong way, by calendar phase instead of by actual piece of work.

Reorganized properly: eight separate pieces of work are fully delivered, and every single one of them landed inside the first three weeks. The one thing still actively running is building out the full set of repositories, and everything past that — the actual tracing, the fusing of the two graphs, the final number — is planned but hasn't started, exactly as scheduled. We stop the chart at week eight on purpose: by our own plan, the core paper is already complete at that point, and anything past it is a bonus, not a requirement.

---

## Slide 15 — References
**~25 sec**

Ten references here, standard IEEE format — the original static call-graph tool we benchmark against, the Python monitoring feature that makes our tracer possible, a few recent papers on AI-assisted code modernization that motivated this whole direction, and our own literature review. I won't read through all ten out loud; they're here for anyone who wants to look deeper afterward.

---

## Slide 16 — Thank You
**~15 sec**

That's Phase 0. Happy to take any questions — and honestly, the harder the question, the better, because that's exactly the spirit we tried to build this whole pipeline in. Thank you.
