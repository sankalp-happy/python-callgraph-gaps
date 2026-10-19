# -*- coding: utf-8 -*-
"""Rewrite the Phase-II interim deck as text-only bullet slides.

Keeps the department template chrome, the title slide, the table of contents
and the Gantt chart. Every other slide becomes black headers + bullets.
"""
import copy, sys
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR
from pptx.oxml.ns import qn

import os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "PhaseII_Interim_submitted.pptx")
OUT = os.path.join(HERE, "PhaseII_Interim_bullets.pptx")

BLACK = RGBColor(0x00, 0x00, 0x00)
FONT = "Times New Roman"

# template chrome that must survive on a content slide
KEEP = {"Rectangle", "Group 19", "TextBox 3", "Title 1", "Rectangle 10"}

# H header, B bullet, S sub-bullet, P plain paragraph (no bullet char)
SLIDES = {}

SLIDES[3] = ("1.  Problem Statement & Objective", 11, [
 ("H", "THE PROBLEM"),
 ("B", "Repository-level modernization is bottlenecked by call-graph quality, not by model capacity."),
 ("B", "Python decides many calls at run time — getattr dispatch, importlib, plugin registries, DI containers."),
 ("B", "Static extractors cannot see those edges, and no one has measured how many are lost."),
 ("B", "A silently lossy call graph makes an LLM code agent confidently wrong."),
 ("H", "WHAT ONE MISS LOOKS LIKE"),
 ("B", "Static extraction (PyCG 0.0.8) reports two edges: main → dispatch, then dispatch → <builtin>.getattr."),
 ("B", "Runtime tracing (sys.setprofile) reports two edges: main → dispatch, then dispatch → handle_email."),
 ("B", "The second runtime edge is real, is executed on every run, and is invisible to static analysis."),
 ("H", "OBJECTIVES"),
 ("B", "O1 — Measure the miss rate: recall of static extraction against runtime-observed edges (hypothesis H2a)."),
 ("B", "O2 — Name the mechanism: show that misses concentrate in identifiable construct classes, not diffusely."),
 ("B", "O3 — Release DynBench-Core: pinned repositories, replayable workloads, reference edge sets and harness."),
 ("B", "O4 — Report feasibility: what it actually costs to trace real projects at corpus scale."),
])

SLIDES[4] = ("2.  Flow / Methodology — Measurement Pipeline  (1 of 2)", 11, [
 ("H", "THE PIPELINE — SIX STAGES, EACH WITH A FIXED OUTPUT"),
 ("B", "Discover — GitHub search over Python repositories that carry a build file.  Output: 558 candidates queued."),
 ("B", "Score density — AST scorer counts dynamic constructs per KLOC of source only.  Output: LOW / MED / HIGH stratum."),
 ("B", "Triage — containerised install and test run; one repo, one Python, one attempt.  Output: GREEN / AMBER / RED plus a pinned lockfile."),
 ("B", "Capture workloads — annotators record at least three replayable runs per repo, verified twice.  Output: the execution oracle."),
 ("B", "Extract both graphs — static: PyCG 0.0.8 and Pyright 1.1.411; dynamic: the sys.monitoring tracer.  Output: S and R."),
 ("B", "Fuse and measure — dual-state CPG fused on read; recall computed over the comparable universe.  Output: the H2a number."),
 ("H", "WHY THE ORDER IS PART OF THE METHOD"),
 ("B", "Density scoring precedes triage, so the corpus is stratified before expensive container work is spent on it."),
 ("B", "Workload capture precedes extraction, so the runtime edge set is fixed by a recorded oracle rather than by whatever happened to execute."),
 ("B", "Fusion is last, so neither graph can be adjusted after the other has been seen."),
 ("H", "EXECUTION ENVIRONMENT"),
 ("B", "Every stage runs inside a container pinned by digest, never by tag."),
 ("B", "The host never traces — it only schedules, collects and verifies."),
])

SLIDES[5] = ("2.  Flow / Methodology — What Makes It a Measurement  (2 of 2)", 11, [
 ("H", "IDENTITY IS PINNED BEFORE ANYTHING RUNS"),
 ("B", "Repo identity requires all five fields: repo_url, sha, pyver, base_image_digest, lockfile_sha256."),
 ("B", "Node identity is frozen as: repo_url, sha, relative_path, qualified_symbol."),
 ("B", "Line numbers are deliberately excluded — they move under reformatting and differ between the static parse and the runtime frame."),
 ("B", "Both graphs are extracted inside the same pinned image, so a difference between them is a property of the code, not of the environment."),
 ("H", "METRIC DISCIPLINE, PRE-REGISTERED"),
 ("B", "Comparable universe — both endpoints in-repo and Python-level; C/builtin and third-party edges are excluded from the primary denominator."),
 ("B", "Recall = |S∩R| / |R|.  The quantity |S∩R| / |S| is never called precision; it is the workload-confirmed fraction."),
 ("B", "R is a lower bound, conditional on the recorded workloads.  That wording is mandatory everywhere it is reported."),
 ("B", "Wrapper transparency — caller → wrapper → f collapses to caller → f, so decorators cannot manufacture misses."),
 ("B", "No LLM-as-judge anywhere in validation or in any headline metric."),
 ("H", "FROZEN BEFORE THE CODE THAT CONSUMES THEM"),
 ("B", "metric_spec_h2a.md, frozen v1.0 — node identity, what counts as an edge, the comparable universe, threats pre-empted."),
 ("B", "density_scorer_spec.md, frozen v1.0 — thresholds calibrated once, on 14 reference repos, before any corpus admission."),
 ("B", "config/base_images.json, frozen v1.2 — five image digests, tool pins, the recipe ladder; appended to, never edited."),
])

SLIDES[6] = ("3.  Demo of Project — A Call Graph Missing a Real Call", 11, [
 ("H", "WHAT RUNS ON SCREEN"),
 ("B", "fixture.py — a small plugin registry that dispatches through getattr, the exact construct class H2a is about."),
 ("B", "PyCG 0.0.8 — runs in the pinned container against the same file and writes static.json."),
 ("B", "sys.setprofile tracer — executes the fixture for real and writes runtime.json."),
 ("B", "Web explainer — React and Cytoscape diff the two graphs and highlight the edge only one of them has."),
 ("H", "REAL OUTPUT FROM THIS REPOSITORY"),
 ("B", "static.json, 3 edges: fixture → fixture.main; fixture.main → PluginRegistry.dispatch; PluginRegistry.dispatch → <builtin>.getattr."),
 ("B", "runtime.json, 3 edges: fixture → fixture.main; fixture.main → PluginRegistry.dispatch; PluginRegistry.dispatch → PluginRegistry.handle_email."),
 ("B", "The two graphs agree on the first two edges and disagree on the third."),
 ("B", "PluginRegistry.handle_email is executed on every run and appears in no static graph."),
 ("H", "DEMO SAFETY"),
 ("B", "A warm end-to-end run takes 0.35 to 2.7 seconds; the fallback threshold is 15 seconds."),
 ("B", "restore_fallback.sh replays a recorded static/runtime pair if the live run does not complete."),
 ("H", "WHY THE DEMO IS THE ARGUMENT"),
 ("B", "The demo is the hypothesis in miniature: one file, one construct, one lost edge."),
 ("B", "Run the same static-versus-runtime diff across the whole pinned corpus and the result is the H2a number."),
])

SLIDES[7] = ("4.  Results / Output — Phase 0, Measured", 10.5, [
 ("H", "HEADLINE NUMBERS"),
 ("B", "558 candidates discovered and scored, against a target of ~450 and a floor of 300."),
 ("B", "100% PyCG failure rate under Python 3.12 — it does not run there at all."),
 ("B", "1.6% PyCG failure on library code under Python 3.10, and 3.1% on test and fixture paths."),
 ("B", "93 seconds to triage click GREEN, end to end, producing a 9-package lockfile and its sha256."),
 ("H", "STRATIFIED QUEUE AND SCORER CALIBRATION"),
 ("B", "HIGH, density ≥ 10.0 — 135 repos queued, 6 in the reference set."),
 ("B", "MED, density 4.0 to 10.0 — 177 repos queued, 4 in the reference set."),
 ("B", "LOW, density < 4.0 — 246 repos queued, 3 in the reference set."),
 ("B", "TOO_SMALL, under 500 SLOC — not queued, 1 in the reference set."),
 ("B", "Totals: 558 repos queued; 14 reference repos used for calibration."),
 ("B", "Stratum is computed from source only — scoring test suites together made every pytest project look HIGH."),
 ("H", "FOUND BY RUNNING PHASE 0, NOT BY PLANNING IT"),
 ("B", "PyCG 0.0.8 cannot be imported on Linux — it ships PyCG/ but imports pycg; a symlink shim is now mandatory in every image."),
 ("B", "The scorer's first run had no discrimination: 10 of 14 repos landed HIGH.  Four false-positive classes were fixed before freezing."),
 ("B", "The scorer corrected two a-priori labels and was right — requests really does call importlib.import_module in its compat layer."),
 ("B", "ins1's classifier has an ordering bug.  It is kept verbatim as error_class_v10 for audit comparability, and the disagreement rate is now reportable."),
 ("B", "A 16.8× overcount was caught in verification — click's collected tests read as 32965 instead of 1965."),
])

SLIDES[8] = ("5.  Status of Paper  (1 of 2)", 11, [
 ("H", "PAPER 1 · SYSTEMATIC REVIEW · UNDER REVIEW"),
 ("B", "Title: “Graph-Aware Neuro-Symbolic Approaches for Legacy Modernization: A Systematic Review”."),
 ("B", "Authors: Adarsha S P · Sankalp Shankar · Surabhi Singh · Pravith S Upadhyaya · Abhishek Kumar."),
 ("B", "Sources searched: IEEE Xplore, ACM Digital Library and arXiv, January 2020 to April 2026."),
 ("B", "Subject: repository-level code translation, refactoring and validation."),
 ("B", "§VIII.B is the finding this project turns into a measurement."),
 ("B", "Venue: [Venue Name].    Submitted: [Date].    Paper ID: [ID]."),
 ("H", "PAPER 2 · IN PREPARATION"),
 ("B", "Title: “TraceWeave-Core: How Much of a Python Call Graph Does Static Extraction Miss?”"),
 ("B", "Gated on the Phase 3 GO / NO-GO decision."),
 ("B", "Headline result: the H2a recall figure, with its per-stratum and per-edge-type breakdowns."),
 ("B", "Accompanying artifact: DynBench-Core."),
 ("B", "The measurement is publishable either way — a low miss rate concentrated at named constructs is a stronger result than a diffuse high one."),
 ("H", "PRE-REGISTRATION"),
 ("B", "No threshold or definition may be tuned after seeing results — the specs were frozen before the extraction code existed."),
])

SLIDES[9] = ("5.  Status of Paper — Proof  (2 of 2)", 11, [
 ("H", "SUBMISSION PROOF"),
 ("B", "The submission-confirmation screenshot is pasted onto this slide before the review."),
 ("B", "Acceptable proof: the acknowledgement e-mail, or the portal's submitted-papers page."),
 ("H", "WHAT THE PROOF MUST SHOW"),
 ("B", "Paper title, exactly as submitted."),
 ("B", "Full author list, in submission order."),
 ("B", "Venue name and track."),
 ("B", "Submission or paper ID."),
 ("B", "Date-stamped acknowledgement."),
 ("B", "Current state, as reported by the portal."),
 ("H", "BEFORE THE SLIDE IS SHOWN"),
 ("B", "Redact reviewer identities."),
 ("B", "Redact any e-mail address that is not a team member's."),
 ("B", "Confirm the screenshot is legible when projected, not only on a laptop screen."),
])

SLIDES[10] = ("6.  Proposed Outcome vs Actual Outcome  (1 of 2)", 11, [
 ("H", "PHASE 0 COMMITMENTS — MET"),
 ("B", "Candidates discovered and scored — proposed ~450, floor 300; actual 558 queued."),
 ("B", "Stratum balance, HIGH not thin — risk flagged in the plan; actual HIGH 135 / MED 177 / LOW 246."),
 ("B", "Pyright pinned before Phase 1 — version query pending; actual 1.1.411, published 2026-06-25."),
 ("B", "PyCG parse-failure rate measured — proposed as “expected non-trivial”; actual 1.6% at 3.10 and 100% at 3.12."),
 ("B", "triage/runner.py parallel queue — proposed recipe ladder plus checkpoints; delivered, and it re-verifies every outcome."),
 ("B", "Density scorer calibrated and frozen — proposed calibrate once then freeze; delivered v1.0, 6 HIGH / 4 MED / 3 LOW / 1 TOO_SMALL."),
 ("H", "COMMITMENTS CARRIED FORWARD — NEXT"),
 ("B", "Corpus with at least three workloads per repo — proposed ~60 repos, floor 40; Phase 1 work, not started."),
 ("B", "H2a recall figure — proposed at the Phase 3 GO / NO-GO; not yet measured, by design."),
 ("H", "HOW TO READ THIS"),
 ("B", "Phase 0 closed on schedule and over target on every item it owned."),
 ("B", "The two NEXT items are Phase 1 and Phase 3 deliverables, not slippage."),
])

SLIDES[11] = ("6.  What the Plan Did Not Predict  (2 of 2)", 10, [
 ("H", "FOUR SURPRISES, AND WHAT EACH ONE CHANGED"),
 ("B", "PyCG does not run on Python 3.12 at all — 1311 of 1311 reference files fail with ImportManagerError, not a SyntaxError, so §2 anticipated the wrong risk."),
 ("S", "Response: static baselines now run on Python ≤ 3.11 while repos are triaged on 3.12, recorded as a deliberate split rather than discovered from a stack trace."),
 ("B", "The published 0.0.8 sdist is unimportable on Linux — it installs PyCG/ but every internal import reads pycg, so it only ever worked on case-insensitive macOS."),
 ("S", "Response: the pin is held at 0.0.8, every image carries the symlink shim, and the deviation is written into MANIFEST §2.1."),
 ("B", "This Mac cannot build the corpus — 8 GB of RAM OOM-kills test suites at --jobs 3, and the corpus must be built on one architecture."),
 ("S", "Response: the Mac is the manager host and the Linux x86_64 box executes; the corpus is amd64, and a Mac-triaged repo counts as development output."),
 ("B", "A patch introduced a silent 16.8× overcount — n_collected matched pytest's pre-deselection total, so click read 32965 instead of 1965."),
 ("S", "Response: caught during verification and fixed in both triage.sh and runner.py, with the pre-deselection total kept separately as n_collected_total."),
 ("H", "STILL OPEN — CARRIED INTO PHASE 1"),
 ("B", "Amend ins1 §6: triage.sh v1.2 emits OOM, TIMEOUT, KILLED and collect_partial, which the operator sheet forbids — an operator cannot record what the script prints."),
 ("S", "validate_sheet.py --v12 is the interim machine check until the amendment lands."),
 ("B", "Re-run the 10% human-versus-classifier audit under v1.2."),
 ("B", "Do not pool the 14 v1.1 spot-check rows with the 558."),
])

SLIDES[12] = ("7.  Conclusion, Deliverables & Impact", 11, [
 ("H", "KEY FINDINGS"),
 ("B", "Phase 0 closed complete and over target: 558 candidates against a plan of ~450."),
 ("B", "The field's standard static baseline fails on 100% of files under the interpreter this project defaults to."),
 ("B", "Dynamic-feature density is measurable and discriminating once four false-positive classes are removed."),
 ("B", "Every headline defect so far was found by running the pipeline, not by reviewing it."),
 ("H", "DELIVERABLES"),
 ("B", "DynBench-Core — pinned repositories, replayable workloads, reference edge sets and harness."),
 ("B", "A pre-registered H2a metric specification, frozen before any extraction code existed."),
 ("B", "Automated triage — triage.sh v1.2 and runner.py, with explicit corpus admission."),
 ("B", "A tracing-feasibility survey, including the repositories that could not be traced."),
 ("H", "IMPACT"),
 ("B", "Tells graph-conditioned code agents how lossy their retrieval substrate really is."),
 ("B", "Names the construct classes to fix, rather than reporting one diffuse percentage."),
 ("B", "Benchmarks outlive methods — the artifact stays useful after the number is quoted."),
 ("B", "A negative result is still the paper: the conditional claim is the strong one."),
 ("H", "WHY THE PINS EXIST"),
 ("B", "Every pin, digest and frozen threshold exists so the published number is a measurement, not the result of searching until something looked good."),
])

SLIDES[13] = ("8.  Individual Responsibilities", 11, [
 ("H", "WORKSTREAM OWNERSHIP"),
 ("B", "[Member 1 Name], [1AY__AI___] — Discovery & stratification.  Owns discover_candidates.py, density_score.py, scorer calibration and the frozen thresholds."),
 ("B", "[Member 2 Name], [1AY__AI___] — Triage automation.  Owns triage.sh v1.2, runner.py, lockfile pinning, corpus admission and the 10% audit."),
 ("B", "[Member 3 Name], [1AY__AI___] — Static baselines.  Owns PyCG 0.0.8 and Pyright 1.1.411 in pinned images, parse-rate measurement and the feasibility survey."),
 ("B", "[Member 4 Name], [1AY__AI___] — Tracing, demo & specification.  Owns the sys.monitoring tracer, the live demo and web explainer, metric_spec_h2a.md and MANIFEST."),
 ("H", "GUIDE — [GUIDE NAME], [DESIGNATION]"),
 ("B", "Reviews every freeze and every version bump."),
 ("B", "Approves the Phase 3 GO / NO-GO."),
 ("B", "Supervises submission."),
 ("H", "SHARED ACROSS ALL FOUR MEMBERS"),
 ("B", "Weekly integration."),
 ("B", "The 10% human-versus-classifier audit."),
 ("B", "Rehearsal of the live demo on the presentation machine."),
])

SLIDES[15] = ("10.  References", 9.5, [
 ("H", "IEEE FORMAT"),
 ("R", "V. Salis, T. Sotiropoulos, P. Louridas, D. Spinellis, and D. Mitropoulos, “PyCG: Practical call graph generation in Python,” in Proc. 43rd Int. Conf. Software Engineering (ICSE), 2021, pp. 1646–1657."),
 ("R", "A. S. P, S. Shankar, S. Singh, P. S. Upadhyaya, and A. Kumar, “Graph-aware neuro-symbolic approaches for legacy modernization: A systematic review,” 2026, under review."),
 ("R", "M. Shannon, “PEP 669 — Low impact monitoring for CPython,” Python Enhancement Proposals, Python Software Foundation, 2022."),
 ("R", "R. Bairi, A. Sonwane, A. Kanade, S. Iyer, S. Parthasarathy, S. Rajamani, B. Ashok, and S. Shet, “CodePlan: Repository-level coding using LLMs and planning,” in Proc. Int. Conf. Learning Representations (ICLR), 2024."),
 ("R", "S. Ouyang, W. Yu, K. Ma, Z. Xiao, Z. Zhang, M. Jia, J. Han, H. Zhang, and D. Yu, “RepoGraph: Enhancing AI software engineering with repository-level code graph,” in Proc. Int. Conf. Learning Representations (ICLR), 2025."),
 ("R", "Y. Pan, J. Zhao, C. Wang, and Q. Liu, “RepoTransBench: A real-world benchmark for repository-level code translation,” arXiv:2412.17744, 2024."),
 ("R", "A. R. Ibrahimzada, K. Ke, M. Pawagi, M. S. Abid, R. Pan, S. Sinha, and R. Jabbarvand, “Repository-level compositional code translation and validation,” arXiv:2410.24117, 2024."),
 ("R", "D. Guo, S. Ren, S. Lu, Z. Feng, D. Tang, S. Liu, L. Zhou, N. Duan, A. Svyatkovskiy, S. Fu, M. Tufano, S. Deng, C. Clement, D. Drain, N. Sundaresan, J. Yin, D. Jiang, and M. Zhou, “GraphCodeBERT: Pre-training code representations with data flow,” in Proc. Int. Conf. Learning Representations (ICLR), 2021."),
 ("R", "Microsoft, “Pyright: Static type checker for Python,” version 1.1.411, 2026. [Online]. Available: https://github.com/microsoft/pyright"),
 ("R", "Python Software Foundation, “ast — Abstract syntax trees,” Python 3.12 documentation, 2026. [Online]. Available: https://docs.python.org/3.12/library/ast.html"),
 ("H", "NOTE"),
 ("B", "Internal project documents (MANIFEST.md, metric_spec_h2a.md, density_scorer_spec.md) are cited in the report, not here."),
])


BOX_W_PT = 9.00 * 72
BOX_H_PT = 5.76 * 72


def fits(items, pt):
    """Rough Times New Roman layout estimate: does the block fit the box?"""
    total = 0.0
    for i, (kind, text) in enumerate(items):
        if kind == "H":
            size, avail, extra = pt + 0.5, BOX_W_PT, (0 if i == 0 else 9) + 3
        else:
            size = pt
            indent = {"B": 0.24, "S": 0.52, "R": 0.42}.get(kind, 0.0) * 72
            avail = BOX_W_PT - indent
            extra = 3.5
            text = "[10]  " + text if kind == "R" else "\u2022  " + text
        cpl = max(1, int(avail / (0.455 * size)))
        lines = -(-len(text) // cpl)
        total += lines * size * 1.16 + extra
    return total <= BOX_H_PT * 0.94


def pick_size(items):
    for pt in (14, 13.5, 13, 12.5, 12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5):
        if fits(items, pt):
            return pt
    return 8.5


def set_indent(para, mar_in, ind_in):
    pPr = para._p.get_or_add_pPr()
    pPr.set("marL", str(Inches(mar_in)))
    pPr.set("indent", str(Inches(ind_in)))
    for tag in ("a:buChar", "a:buAutoNum", "a:buNone"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    pPr.append(pPr.makeelement(qn("a:buNone"), {}))


REF_N = [0]


REF_N = [0]


def add_para(tf, first, kind, text, body_pt):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    if kind == "H":
        p.space_before = Pt(0 if first else 9)
        p.space_after = Pt(3)
        set_indent(p, 0, 0)
        r = p.add_run(); r.text = text
        f = r.font; f.name = FONT; f.size = Pt(body_pt + 0.5); f.bold = True; f.color.rgb = BLACK
        return
    if kind == "B":
        set_indent(p, 0.24, -0.24)
        prefix = "•  "
    elif kind == "R":
        REF_N[0] += 1
        set_indent(p, 0.44, -0.44)
        prefix = "[%d]%s " % (REF_N[0], "" if REF_N[0] > 9 else " ")
    elif kind == "S":
        set_indent(p, 0.52, -0.24)
        prefix = "–  "
    else:
        set_indent(p, 0, 0)
        prefix = ""
    p.space_before = Pt(0)
    p.space_after = Pt(3.5)
    r = p.add_run(); r.text = prefix + text
    f = r.font; f.name = FONT; f.size = Pt(body_pt); f.bold = False; f.color.rgb = BLACK


def main():
    prs = Presentation(SRC)
    for num, (title, _ignored_pt, items) in SLIDES.items():
        body_pt = pick_size(items)
        print(f"slide {num}: {len(items)} paras at {body_pt}pt")
        slide = prs.slides[num - 1]
        for sh in list(slide.shapes):
            if sh.name not in KEEP:
                sh._element.getparent().remove(sh._element)
        # title: keep the placeholder, force black
        for sh in slide.shapes:
            if sh.name == "Title 1" and sh.has_text_frame:
                for para in sh.text_frame.paragraphs:
                    runs = para.runs
                    for i, r in enumerate(runs):
                        r.text = title if i == 0 else ""
                        r.font.color.rgb = BLACK
        box = slide.shapes.add_textbox(Inches(3.00), Inches(1.12), Inches(9.00), Inches(5.76))
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        for i, (kind, text) in enumerate(items):
            add_para(tf, i == 0, kind, text, body_pt)
    prs.save(OUT)
    print("wrote", OUT)

main()
