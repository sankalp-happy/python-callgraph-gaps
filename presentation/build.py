#!/usr/bin/env python3
"""Fill the Acharya Phase-II template with the TraceWeave-Core project content."""
from pptx import Presentation
from pptx.util import Inches as In, Pt
from pptx.dml.color import RGBColor as C
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from lxml import etree

# ---------------------------------------------------------------- palette
ORANGE = C(0xF2, 0x8E, 0x01)   # inherited from the template's side band
INK    = C(0x1E, 0x25, 0x2E)
MUTED  = C(0x6E, 0x78, 0x83)
CARD   = C(0xF1, 0xF3, 0xF5)
SLATE  = C(0x2B, 0x34, 0x40)
WHITE  = C(0xFF, 0xFF, 0xFF)
MISS   = C(0xB3, 0x33, 0x22)   # static missed it
RUN    = C(0x0F, 0x6C, 0x8C)   # observed at runtime
GOOD   = C(0x2E, 0x7D, 0x5B)
LINE   = C(0xD7, 0xDD, 0xE3)

BODY = "Times New Roman"
MONO = "Courier New"

L, R = 3.00, 12.00          # content column, inches
W = R - L                    # 9.00
TOP, BOT = 1.18, 6.86        # usable vertical band

# ---------------------------------------------------------------- helpers
def no_bullet(p):
    pPr = p._p.get_or_add_pPr()
    if pPr.find(qn('a:buNone')) is None:
        etree.SubElement(pPr, qn('a:buNone'))

def para(tf, text, size=13, bold=False, color=INK, font=BODY, align=PP_ALIGN.LEFT,
         space_before=0, space_after=2, first=False, italic=False, line=0.95):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(space_before)
    p.space_after = Pt(space_after)
    p.line_spacing = line
    no_bullet(p)
    if text:
        r = p.add_run(); r.text = text
        r.font.size, r.font.bold, r.font.italic = Pt(size), bold, italic
        r.font.color.rgb = color
        r.font.name = font
    return p

def rich(tf, parts, size=13, align=PP_ALIGN.LEFT, space_before=0, space_after=2,
         first=False, line=0.95):
    """parts = [(text, bold, color, font|None), ...] in one paragraph."""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before, p.space_after, p.line_spacing = Pt(space_before), Pt(space_after), line
    no_bullet(p)
    for t, b, col, *rest in parts:
        r = p.add_run(); r.text = t
        r.font.size, r.font.bold = Pt(size), b
        r.font.color.rgb = col
        r.font.name = rest[0] if rest and rest[0] else BODY
    return p

def textbox(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP):
    sh = slide.shapes.add_textbox(In(x), In(y), In(w), In(h))
    tf = sh.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    return tf

def card(slide, x, y, w, h, fill=CARD, radius=0.035, line_col=None):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, In(x), In(y), In(w), In(h))
    sh.adjustments[0] = radius
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    if line_col is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line_col; sh.line.width = Pt(0.75)
    sh.shadow.inherit = False
    sh.text_frame.text = ""
    return sh

def chip(slide, x, y, d, label, fill=ORANGE, fg=WHITE, size=15):
    """Numbered circle — the deck's repeated motif."""
    sh = slide.shapes.add_shape(MSO_SHAPE.OVAL, In(x), In(y), In(d), In(d))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    sh.line.fill.background(); sh.shadow.inherit = False
    tf = sh.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, label, size=size, bold=True, color=fg, align=PP_ALIGN.CENTER, first=True,
         space_after=0)
    return sh

def flat(sh):
    """Drop the theme style ref — otherwise LibreOffice/PowerPoint paint a shadow
    under 1-px rules and pills, which reads as a rendering artifact."""
    st = sh._element.find(qn('p:style'))
    if st is not None:
        sh._element.remove(st)
    return sh

def bar(slide, x, y, w, h, fill):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, In(x), In(y), In(w), In(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    sh.line.fill.background(); sh.shadow.inherit = False
    sh.text_frame.text = ""
    return flat(sh)

def set_title(slide, text, size=26):
    for sh in slide.shapes:
        if sh.has_text_frame and sh.name.startswith("Title"):
            tf = sh.text_frame
            tf.clear()
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            para(tf, text, size=size, bold=True, color=INK, first=True, space_after=0)
            return sh
    return None

def strip_body(slide):
    """Remove the template's content placeholder — every content slide draws its own."""
    for sh in list(slide.shapes):
        if sh.name.startswith("Content Placeholder"):
            sh._element.getparent().remove(sh._element)

def section_head(slide, x, y, w, text, num=None, color=ORANGE):
    """Small caps-ish section label used at the top of every card."""
    if num is not None:
        chip(slide, x, y - 0.03, 0.30, num, size=12)
        x, w = x + 0.42, w - 0.42
    tf = textbox(slide, x, y, w, 0.26)
    para(tf, text.upper(), size=11.5, bold=True, color=color, first=True, space_after=0)

# ---------------------------------------------------------------- content
TITLE = ("TraceWeave-Core: Measuring What Static Call-Graph "
         "Extraction Misses in Real Python Repositories")

prs = Presentation("deck.pptx")

# The master carries a decorative rule at y=1.90" that strikes through body content
# on every slide — visible in the template's own render. Remove it once, globally.
for _m in prs.slide_masters:
    for _sh in list(_m.shapes):
        if _sh.name == "Straight Connector 9":
            _sh._element.getparent().remove(_sh._element)

S = list(prs.slides)

# ============================================================ 1. TITLE SLIDE
s = S[0]
for sh in s.shapes:
    if sh.name == "Title 1" and In(1) < sh.top < In(3):  # the project-title box
        sh.top, sh.height = In(1.62), In(0.95)
        tf = sh.text_frame; tf.clear(); tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        para(tf, TITLE, size=21, bold=True, color=INK,
             align=PP_ALIGN.CENTER, first=True, space_after=0, line=1.0)
    elif sh.name == "TextBox 10":
        sh.top, sh.height = In(1.02), In(0.58)
        tf = sh.text_frame; tf.clear(); tf.word_wrap = True
        para(tf, "Project Phase-II  ·  Interim Presentation", size=15, bold=True,
             color=MUTED, align=PP_ALIGN.CENTER, first=True, space_after=0)
        para(tf, "on  [Presentation Date]", size=12, color=MUTED,
             align=PP_ALIGN.CENTER, space_after=0)
    elif sh.name == "TextBox 11":
        sh.top = In(2.66)

for sh in s.shapes:
    if sh.has_table:
        t = sh.table
        members = ["[Member 1 Name]", "[Member 2 Name]", "[Member 3 Name]", "[Member 4 Name]"]
        for i, name in enumerate(members, start=1):
            cells = t.rows[i].cells
            if i == 1:
                tf = cells[0].text_frame; tf.clear()
                para(tf, "[Group No]", size=13, bold=True, color=INK,
                     align=PP_ALIGN.CENTER, first=True, space_after=0)
            tf = cells[1].text_frame; tf.clear()
            para(tf, name, size=13, color=INK, align=PP_ALIGN.CENTER,
                 first=True, space_after=0)
            tf = cells[2].text_frame; tf.clear()
            para(tf, "[1AY__AI___]", size=13, color=INK, align=PP_ALIGN.CENTER,
                 first=True, space_after=0)
        g = t.rows[5].cells
        tf = g[1].text_frame; tf.clear()
        para(tf, "[Guide Name]", size=13, bold=True, color=INK,
             align=PP_ALIGN.CENTER, first=True, space_after=0)
        para(tf, "[Designation]", size=12, color=MUTED,
             align=PP_ALIGN.CENTER, space_after=0)

# ============================================================ 2. CONTENTS
s = S[1]
strip_body(s)
set_title(s, "Contents")
AGENDA = [
    ("1", "Problem Statement & Objective", "Why static call graphs are the bottleneck"),
    ("2", "Flow / Methodology", "The measurement pipeline, and what makes it a measurement"),
    ("3", "Demo of Project", "A call graph missing a real call, live"),
    ("4", "Results / Output", "Phase 0, measured"),
    ("5", "Status of Paper", "Submission and proof"),
    ("6", "Proposed vs Actual Outcome", "Targets, deliveries and the surprises"),
    ("7", "Conclusion, Deliverables & Impact", "What ships and who it helps"),
    ("8", "Individual Responsibilities", "Workstream ownership"),
    ("9", "Gantt Chart", "Workstreams delivered, and what remains"),
    ("10", "References", "IEEE format"),
]
cw = (W - 0.30) / 2
for i, (n, head, sub) in enumerate(AGENDA):
    col, row = i // 5, i % 5
    x = L + col * (cw + 0.30)
    y = 1.42 + row * 1.05
    chip(s, x, y + 0.05, 0.42, n, size=14)
    tf = textbox(s, x + 0.58, y, cw - 0.58, 0.42)
    para(tf, head, size=15, bold=True, color=INK, first=True, space_after=1)
    para(tf, sub, size=11, color=MUTED, space_after=0)

tf = textbox(s, L, 6.52, W, 0.30)
para(tf, "Content is presented as bullets, figures and tables throughout — no paragraphs.",
     size=10.5, italic=True, color=MUTED, first=True, space_after=0)

# ============================================================ 3. PROBLEM
s = S[2]
strip_body(s)
set_title(s, "1.  Problem Statement & Objective")

# -- left card: the problem
cw2 = 4.35
card(s, L, TOP, cw2, 3.05)
section_head(s, L + 0.22, TOP + 0.20, cw2 - 0.44, "The problem")
tf = textbox(s, L + 0.22, TOP + 0.55, cw2 - 0.44, 2.35)
for t in [
    "Repository-level modernization is bottlenecked by call-graph quality, not model capacity.",
    "Python decides many calls at run time — getattr dispatch, importlib, plugin registries, DI containers.",
    "Static extractors cannot see those edges — and no one has measured how many are lost.",
    "A silently lossy graph makes an LLM code agent confidently wrong.",
]:
    rich(tf, [("•  ", True, ORANGE), (t, False, INK)], size=12.5, space_after=7)

# -- right card: what a miss actually looks like
x2 = L + cw2 + 0.30
cw3 = W - cw2 - 0.30
card(s, x2, TOP, cw3, 3.05, fill=SLATE)
section_head(s, x2 + 0.22, TOP + 0.20, cw3 - 0.44, "What one miss looks like", color=ORANGE)
tf = textbox(s, x2 + 0.22, TOP + 0.58, cw3 - 0.44, 2.30)
rich(tf, [("STATIC  (PyCG 0.0.8)", True, C(0x9F, 0xAD, 0xBC))], size=10.5, first=True, space_after=4)
for t in ["main → dispatch", "dispatch → <builtin>.getattr"]:
    para(tf, "  " + t, size=11.5, color=WHITE, font=MONO, space_after=3)
rich(tf, [("RUNTIME  (sys.setprofile)", True, C(0x9F, 0xAD, 0xBC))], size=10.5,
     space_before=8, space_after=4)
for t in ["main → dispatch", "dispatch → handle_email"]:
    para(tf, "  " + t, size=11.5, color=WHITE, font=MONO, space_after=3)
rich(tf, [("✕  the second edge is real, executed, and invisible to static analysis",
           True, C(0xFF, 0xB0, 0x9A))], size=11, space_before=9, space_after=0)

# -- objectives
OBJ = [
    ("O1", "Measure the miss rate", "Recall of static extraction against runtime-observed edges (H2a)"),
    ("O2", "Name the mechanism", "Show misses concentrate in identifiable construct classes"),
    ("O3", "Release DynBench-Core", "Pinned repos, replayable workloads, reference edge sets, harness"),
    ("O4", "Report feasibility", "What it costs to trace real projects at corpus scale"),
]
oy = TOP + 3.52
tf = textbox(s, L, oy - 0.30, W, 0.26)
para(tf, "OBJECTIVES", size=11.5, bold=True, color=ORANGE, first=True, space_after=0)
ow = (W - 3 * 0.20) / 4
for i, (n, head, sub) in enumerate(OBJ):
    x = L + i * (ow + 0.20)
    card(s, x, oy, ow, 1.95)
    chip(s, x + 0.20, oy + 0.18, 0.40, n, size=13)
    tf = textbox(s, x + 0.20, oy + 0.66, ow - 0.40, 1.15)
    para(tf, head, size=13, bold=True, color=INK, first=True, space_after=4)
    para(tf, sub, size=10.5, color=MUTED, space_after=0, line=1.0)

# ============================================================ 4. METHODOLOGY 1
s = S[3]
strip_body(s)
set_title(s, "2.  Flow / Methodology — Measurement Pipeline  (1 of 2)")

STAGES = [
    ("1", "Discover", "GitHub search over Python repos with a build file.",
     "558 candidates queued"),
    ("2", "Score density", "AST scorer counts dynamic constructs per KLOC of source only.",
     "LOW / MED / HIGH stratum"),
    ("3", "Triage", "Containerised install + test run, one repo, one Python, one attempt.",
     "GREEN / AMBER / RED + pinned lockfile"),
    ("4", "Capture workloads", "Annotators record ≥3 replayable runs per repo, verified twice.",
     "The execution oracle"),
    ("5", "Extract both graphs", "Static: PyCG 0.0.8 + Pyright 1.1.411.  Dynamic: sys.monitoring tracer.",
     "S  and  R"),
    ("6", "Fuse & measure", "Dual-state CPG, fused on read; recall over the comparable universe.",
     "The H2a number"),
]
sw = (W - 2 * 0.22) / 3
sh_ = 2.42
for i, (n, head, body, out) in enumerate(STAGES):
    col, row = i % 3, i // 3
    x = L + col * (sw + 0.22)
    y = TOP + row * (sh_ + 0.26)
    card(s, x, y, sw, sh_)
    chip(s, x + 0.22, y + 0.22, 0.44, n, size=14)
    tf = textbox(s, x + 0.22, y + 0.78, sw - 0.44, 1.40)
    para(tf, head, size=14.5, bold=True, color=INK, first=True, space_after=5)
    para(tf, body, size=11, color=MUTED, space_after=0, line=1.05)
    bar(s, x + 0.22, y + sh_ - 0.44, sw - 0.44, 0.012, LINE)
    tf = textbox(s, x + 0.22, y + sh_ - 0.36, sw - 0.44, 0.26)
    rich(tf, [("→  ", True, ORANGE), (out, True, INK)], size=11, first=True, space_after=0)

tf = textbox(s, L, TOP + 2 * sh_ + 0.42, W, 0.30)
rich(tf, [("Every stage runs inside a container pinned by digest, never by tag — ", False, MUTED),
          ("the host never traces.", True, INK)], size=11.5, first=True, space_after=0)

# ============================================================ 5. METHODOLOGY 2
s = S[4]
strip_body(s)
set_title(s, "2.  Flow / Methodology — What Makes It a Measurement  (2 of 2)")

cwA = 4.10
card(s, L, TOP, cwA, 3.30)
section_head(s, L + 0.22, TOP + 0.20, cwA - 0.44, "Identity is pinned before anything runs")
tf = textbox(s, L + 0.22, TOP + 0.58, cwA - 0.44, 2.60)
para(tf, "Repo identity — all five required", size=12, bold=True, color=INK, first=True, space_after=3)
para(tf, "(repo_url, sha, pyver,\n base_image_digest, lockfile_sha256)", size=10.5,
     color=RUN, font=MONO, space_after=7, line=1.05)
para(tf, "Node identity — frozen", size=12, bold=True, color=INK, space_after=3)
para(tf, "(repo_url, sha, relative_path,\n qualified_symbol)", size=10.5, color=RUN,
     font=MONO, space_after=6, line=1.05)
rich(tf, [("Line numbers are deliberately excluded", True, INK),
          (" — they move under reformatting and differ between the static parse and the "
           "runtime frame.", False, MUTED)], size=11, space_after=8, line=1.05)
rich(tf, [("Both graphs are extracted inside the same pinned image, ", True, INK),
          ("so a difference between them is a property of the code — not of the "
           "environment it ran in.", False, MUTED)], size=11, space_after=0, line=1.05)

xB = L + cwA + 0.28
cwB = W - cwA - 0.28
card(s, xB, TOP, cwB, 3.30)
section_head(s, xB + 0.22, TOP + 0.20, cwB - 0.44, "Metric discipline, pre-registered")
tf = textbox(s, xB + 0.22, TOP + 0.58, cwB - 0.44, 2.60)
for lead, rest in [
    ("Comparable universe — ", "both ends in-repo and Python-level. C/builtin and third-party are excluded from the primary denominator."),
    ("Recall = |S∩R| / |R|. ", "|S∩R|/|S| is never called precision — it is the workload-confirmed fraction."),
    ("R is a lower bound, ", "conditional on the recorded workloads. That wording is mandatory everywhere."),
    ("Wrapper transparency — ", "caller → wrapper → f collapses to caller → f, so decorators cannot manufacture misses."),
    ("No LLM-as-judge ", "anywhere in validation or headline metrics."),
]:
    rich(tf, [("•  ", True, ORANGE), (lead, True, INK), (rest, False, MUTED)],
         size=11, space_after=6, line=1.05)

fy = TOP + 3.72
tf = textbox(s, L, fy - 0.30, W, 0.26)
para(tf, "FROZEN BEFORE THE CODE THAT CONSUMES THEM", size=11.5, bold=True,
     color=ORANGE, first=True, space_after=0)
FROZEN = [
    ("metric_spec_h2a.md", "v1.0", "Node identity, what counts as an edge, the comparable universe, threats pre-empted."),
    ("density_scorer_spec.md", "v1.0", "Thresholds calibrated once, on 14 reference repos, before any corpus admission."),
    ("config/base_images.json", "v1.2", "Five image digests, tool pins, the recipe ladder. Appended to, never edited."),
]
fw = (W - 2 * 0.20) / 3
for i, (name, ver, why) in enumerate(FROZEN):
    x = L + i * (fw + 0.20)
    card(s, x, fy, fw, 1.55, fill=WHITE, line_col=LINE)
    tf = textbox(s, x + 0.20, fy + 0.18, fw - 0.40, 1.22)
    rich(tf, [(name, True, INK, MONO)], size=11, first=True, space_after=3)
    rich(tf, [("frozen ", False, MUTED), (ver, True, GOOD)], size=10.5, space_after=5)
    para(tf, why, size=10, color=MUTED, space_after=0, line=1.05)

# ============================================================ 6. DEMO
s = S[5]
strip_body(s)
set_title(s, "3.  Demo of Project — A Call Graph Missing a Real Call")

cwD = 3.95
tf = textbox(s, L, TOP, cwD, 0.26)
para(tf, "WHAT RUNS ON SCREEN", size=11.5, bold=True, color=ORANGE, first=True, space_after=0)
STEPS = [
    ("1", "fixture.py", "A small plugin registry that dispatches through getattr — the construct class H2a is about."),
    ("2", "PyCG 0.0.8", "Runs in the pinned container against the same file, writes static.json."),
    ("3", "sys.setprofile tracer", "Executes the fixture for real, writes runtime.json."),
    ("4", "Web explainer", "React + Cytoscape diffs the two graphs and highlights the edge only one of them has."),
]
for i, (n, head, body) in enumerate(STEPS):
    y = TOP + 0.34 + i * 1.02
    chip(s, L, y + 0.02, 0.38, n, size=13)
    tf = textbox(s, L + 0.50, y, cwD - 0.50, 0.92)
    para(tf, head, size=13.5, bold=True, color=INK, first=True, space_after=3)
    para(tf, body, size=10.5, color=MUTED, space_after=0, line=1.05)

xD = L + cwD + 0.30
cwE = W - cwD - 0.30
card(s, xD, TOP, cwE, 3.30, fill=SLATE)
section_head(s, xD + 0.22, TOP + 0.20, cwE - 0.44, "Real output, this repository", color=ORANGE)
tf = textbox(s, xD + 0.22, TOP + 0.60, cwE - 0.44, 2.55)
rich(tf, [("static.json", True, C(0x9F, 0xAD, 0xBC), MONO), ("  —  3 edges", False, C(0x9F, 0xAD, 0xBC))],
     size=10.5, first=True, space_after=4)
for t in ["fixture → fixture.main",
          "fixture.main → PluginRegistry.dispatch",
          "PluginRegistry.dispatch → <builtin>.getattr"]:
    para(tf, "  " + t, size=9, color=WHITE, font=MONO, space_after=3)
rich(tf, [("runtime.json", True, C(0x9F, 0xAD, 0xBC), MONO), ("  —  3 edges", False, C(0x9F, 0xAD, 0xBC))],
     size=10.5, space_before=8, space_after=4)
for t, col in [("fixture → fixture.main", WHITE),
               ("fixture.main → PluginRegistry.dispatch", WHITE),
               ("PluginRegistry.dispatch → PluginRegistry.handle_email", C(0xFF, 0xC4, 0x6B))]:
    para(tf, "  " + t, size=9, color=col, font=MONO, space_after=3)
rich(tf, [("✕  handle_email is executed every run and appears in no static graph.",
           True, C(0xFF, 0xB0, 0x9A))], size=11, space_before=9, space_after=0)

dy = TOP + 3.52
card(s, xD, dy, cwE, 1.10, fill=WHITE, line_col=LINE)
tf = textbox(s, xD + 0.22, dy + 0.18, cwE - 0.44, 0.72)
para(tf, "DEMO SAFETY", size=10.5, bold=True, color=ORANGE, first=True, space_after=4)
rich(tf, [("Warm end-to-end run 0.35–2.7 s", True, INK),
          ("  ·  15 s fallback threshold  ·  ", False, MUTED),
          ("restore_fallback.sh", False, RUN, MONO),
          (" replays a recorded pair.", False, MUTED)], size=10.5, space_after=0, line=1.05)

card(s, L, 5.92, W, 0.88, fill=SLATE)
tf = textbox(s, L + 0.28, 6.06, W - 0.56, 0.60, anchor=MSO_ANCHOR.MIDDLE)
rich(tf, [("The demo is the hypothesis in miniature. ", True, C(0xFF, 0xC4, 0x6B)),
          ("Run the same static-vs-runtime diff across the whole pinned corpus and the "
           "result is the H2a number.", False, WHITE)],
     size=12, align=PP_ALIGN.CENTER, first=True, space_after=0, line=1.05)

# ============================================================ 7. RESULTS
s = S[6]
strip_body(s)
set_title(s, "4.  Results / Output — Phase 0, Measured")

STATS = [
    ("558", "candidates discovered\n& scored", "target ~450 · floor 300"),
    ("100%", "PyCG failure rate\nunder Python 3.12", "it does not run there at all"),
    ("1.6%", "PyCG failure on library\ncode under Python 3.10", "3.1% on test & fixture paths"),
    ("93 s", "click triaged GREEN,\nend to end", "9-package lockfile + sha256"),
]
stw = (W - 3 * 0.20) / 4
for i, (big, lab, sub) in enumerate(STATS):
    x = L + i * (stw + 0.20)
    card(s, x, TOP, stw, 1.56)
    tf = textbox(s, x + 0.18, TOP + 0.13, stw - 0.36, 1.30)
    para(tf, big, size=34, bold=True, color=ORANGE, first=True, space_after=2, line=0.9)
    para(tf, lab, size=11, bold=True, color=INK, space_after=2, line=1.0)
    para(tf, sub, size=9.5, color=MUTED, space_after=0, line=1.0)

ry = TOP + 1.78
cwF = 4.35
card(s, L, ry, cwF, 3.80, fill=WHITE, line_col=LINE)
section_head(s, L + 0.22, ry + 0.20, cwF - 0.44, "Stratified queue & scorer calibration")
rows = [("Stratum", "Queue", "Ref. set", True),
        ("HIGH  (≥10.0)", "135", "6", False),
        ("MED  (4.0–10.0)", "177", "4", False),
        ("LOW  (<4.0)", "246", "3", False),
        ("TOO_SMALL  (<500 SLOC)", "—", "1", False),
        ("Total", "558", "14", True)]
for i, (a, b, c, bold) in enumerate(rows):
    y = ry + 0.62 + i * 0.40
    if bold:
        bar(s, L + 0.22, y + 0.32, cwF - 0.44, 0.012, LINE)
    tf = textbox(s, L + 0.22, y, 2.55, 0.30)
    para(tf, a, size=11.5, bold=bold, color=INK if bold else MUTED, first=True, space_after=0)
    for j, v in enumerate((b, c)):
        tf = textbox(s, L + 2.80 + j * 0.72, y, 0.62, 0.30)
        para(tf, v, size=11.5, bold=bold, color=INK, align=PP_ALIGN.RIGHT,
             first=True, space_after=0)
tf = textbox(s, L + 0.22, ry + 3.22, cwF - 0.44, 0.44)
para(tf, "Stratum comes from source only — scoring test suites together made every "
         "pytest project look HIGH.", size=9.5, italic=True, color=MUTED, first=True,
     space_after=0, line=1.0)

xG = L + cwF + 0.30
cwG = W - cwF - 0.30
card(s, xG, ry, cwG, 3.80, fill=WHITE, line_col=LINE)
section_head(s, xG + 0.22, ry + 0.20, cwG - 0.44, "Found by running Phase 0, not planning it")
tf = textbox(s, xG + 0.22, ry + 0.58, cwG - 0.44, 3.05)
for lead, rest in [
    ("PyCG 0.0.8 cannot be imported on Linux — ", "it ships PyCG/ but imports pycg. A symlink shim is now mandatory in every image."),
    ("The scorer's first run had no discrimination — ", "10 of 14 repos landed HIGH. Four false-positive classes were fixed before freezing."),
    ("It corrected two a-priori labels, and was right: ", "requests really does call importlib.import_module in its compat layer."),
    ("ins1's classifier has an ordering bug. ", "Kept verbatim as error_class_v10 for audit comparability; the disagreement rate is now reportable."),
    ("A 16.8× overcount was caught in verification — ", "click's collected tests read as 32965 instead of 1965."),
]:
    rich(tf, [("•  ", True, ORANGE), (lead, True, INK), (rest, False, MUTED)],
         size=10.5, space_after=8, line=1.05)

# ============================================================ 8. PAPER STATUS 1
s = S[7]
strip_body(s)
set_title(s, "5.  Status of Paper  (1 of 2)")

card(s, L, TOP, W, 2.30, fill=WHITE, line_col=LINE)
tf = textbox(s, L + 0.28, TOP + 0.22, W - 3.10, 1.90)
para(tf, "PAPER 1  ·  SYSTEMATIC REVIEW", size=11, bold=True, color=ORANGE, first=True, space_after=6)
para(tf, "Graph-Aware Neuro-Symbolic Approaches for Legacy Modernization: "
         "A Systematic Review", size=16, bold=True, color=INK, space_after=6, line=1.05)
para(tf, "Adarsha S P · Sankalp Shankar · Surabhi Singh · Pravith S Upadhyaya · Abhishek Kumar",
     size=11, color=MUTED, space_after=6)
rich(tf, [("Scope: ", True, INK),
          ("IEEE Xplore, ACM DL and arXiv, January 2020 – April 2026; repository-level "
           "code translation, refactoring and validation. §VIII.B is the finding this "
           "project turns into a measurement.", False, MUTED)], size=11, space_after=0, line=1.05)

st = card(s, L + W - 2.80, TOP + 0.22, 2.52, 1.86, fill=SLATE)
tf = textbox(s, L + W - 2.62, TOP + 0.42, 2.16, 1.50)
para(tf, "STATUS", size=10, bold=True, color=C(0x9F, 0xAD, 0xBC), first=True, space_after=6)
para(tf, "UNDER REVIEW", size=17, bold=True, color=C(0xFF, 0xC4, 0x6B), space_after=8, line=1.0)
para(tf, "Venue:  [Venue Name]", size=10.5, color=WHITE, space_after=3)
para(tf, "Submitted:  [Date]", size=10.5, color=WHITE, space_after=3)
para(tf, "Paper ID:  [ID]", size=10.5, color=WHITE, space_after=0)

py2 = TOP + 2.52
card(s, L, py2, W, 2.05, fill=CARD)
tf = textbox(s, L + 0.28, py2 + 0.22, W - 0.56, 1.65)
para(tf, "PAPER 2  ·  IN PREPARATION", size=11, bold=True, color=ORANGE, first=True, space_after=6)
para(tf, "TraceWeave-Core: How Much of a Python Call Graph Does Static Extraction Miss?",
     size=15, bold=True, color=INK, space_after=6, line=1.05)
rich(tf, [("Gated on the Phase 3 GO / NO-GO. ", True, INK),
          ("The headline is the H2a recall figure with its per-stratum and per-edge-type "
           "breakdowns, plus the DynBench-Core artifact. The measurement is publishable "
           "either way — a low miss rate concentrated at named constructs is a stronger "
           "result than a diffuse high one.", False, MUTED)], size=11, space_after=0, line=1.05)

tf = textbox(s, L, TOP + 4.80, W, 0.32)
para(tf, "No threshold or definition may be tuned after seeing results — the specs were "
         "frozen before the extraction code existed.", size=10.5, italic=True,
     color=MUTED, first=True, space_after=0)

# ============================================================ 9. PAPER STATUS 2
s = S[8]
strip_body(s)
set_title(s, "5.  Status of Paper — Proof  (2 of 2)")

pw = 5.35
card(s, L, TOP, pw, 4.55, fill=WHITE, line_col=LINE)
inner = card(s, L + 0.25, TOP + 0.55, pw - 0.50, 3.72, fill=CARD)
tf = textbox(s, L + 0.22, TOP + 0.20, pw - 0.44, 0.30)
para(tf, "SUBMISSION PROOF", size=11, bold=True, color=ORANGE, first=True, space_after=0)
tf = textbox(s, L + 0.55, TOP + 1.90, pw - 1.10, 1.20, anchor=MSO_ANCHOR.MIDDLE)
para(tf, "[ Paste the submission-confirmation screenshot here ]", size=13, bold=True,
     color=MUTED, align=PP_ALIGN.CENTER, first=True, space_after=6)
para(tf, "Acknowledgement e-mail or the portal's submitted-papers page",
     size=10.5, color=MUTED, align=PP_ALIGN.CENTER, space_after=0)

xH = L + pw + 0.30
cwH = W - pw - 0.30
card(s, xH, TOP, cwH, 4.55, fill=CARD)
tf = textbox(s, xH + 0.24, TOP + 0.22, cwH - 0.48, 0.30)
para(tf, "WHAT THE PROOF MUST SHOW", size=11, bold=True, color=ORANGE, first=True, space_after=0)
tf = textbox(s, xH + 0.24, TOP + 0.62, cwH - 0.48, 3.70)
for t in ["Paper title exactly as submitted",
          "Full author list in submission order",
          "Venue name and track",
          "Submission or paper ID",
          "Date-stamped acknowledgement",
          "Current state shown by the portal"]:
    rich(tf, [("☐   ", True, ORANGE), (t, False, INK)], size=12, space_after=10)
bar(s, xH + 0.24, TOP + 3.42, cwH - 0.48, 0.012, LINE)
tf = textbox(s, xH + 0.24, TOP + 3.58, cwH - 0.48, 0.85)
para(tf, "Redact reviewer identities and any e-mail address that is not a team member's "
         "before the slide is shown.", size=10, italic=True, color=MUTED, first=True,
     space_after=0, line=1.05)

# ============================================================ 10. PROPOSED vs ACTUAL 1
s = S[9]
strip_body(s)
set_title(s, "6.  Proposed Outcome vs Actual Outcome  (1 of 2)")

HDR = ("Phase 0 commitment", "Proposed", "Actual", "")
ROWS = [
    ("Candidates discovered & scored", "~450  (floor 300)", "558 queued", "MET"),
    ("Stratum balance — HIGH not thin", "risk flagged in plan", "HIGH 135 / MED 177 / LOW 246", "MET"),
    ("Pyright pinned before Phase 1", "version query pending", "1.1.411, published 2026-06-25", "MET"),
    ("PyCG parse-failure rate measured", "\"expected non-trivial\"", "1.6% @ 3.10  ·  100% @ 3.12", "MET"),
    ("triage/runner.py — parallel queue", "recipe ladder + checkpoints", "delivered, re-verifies every outcome", "MET"),
    ("Density scorer calibrated & frozen", "calibrate once, then freeze", "v1.0 — 6 HIGH / 4 MED / 3 LOW / 1 TS", "MET"),
    ("Corpus with ≥3 workloads per repo", "~60 repos  (floor 40)", "Phase 1 work — not started", "NEXT"),
    ("H2a recall figure", "Phase 3 GO / NO-GO", "not yet measured, by design", "NEXT"),
]
colx = [L + 0.22, L + 3.28, L + 5.42, L + 8.12]
colw = [2.98, 2.06, 2.62, 0.80]
flat(card(s, L, TOP, W, 0.42, fill=SLATE))
for i, h in enumerate(HDR):
    tf = textbox(s, colx[i], TOP + 0.10, colw[i], 0.26)
    para(tf, h.upper(), size=10, bold=True, color=WHITE, first=True, space_after=0)
for i, (a, b, c, tag) in enumerate(ROWS):
    y = TOP + 0.42 + i * 0.545
    if i % 2 == 0:
        bar(s, L, y, W, 0.545, C(0xF7, 0xF9, 0xFA))
    for j, v in enumerate((a, b, c)):
        tf = textbox(s, colx[j], y + 0.13, colw[j], 0.34)
        para(tf, v, size=10.5, bold=(j == 0), color=INK if j != 1 else MUTED,
             first=True, space_after=0, line=1.0)
    col = GOOD if tag == "MET" else ORANGE
    pill = flat(card(s, colx[3], y + 0.11, 0.80, 0.30, fill=col, radius=0.5))
    tf = pill.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, tag, size=9, bold=True, color=WHITE, align=PP_ALIGN.CENTER, first=True, space_after=0)

tf = textbox(s, L, TOP + 0.42 + len(ROWS) * 0.545 + 0.16, W, 0.32)
rich(tf, [("Phase 0 closed on schedule and over target on every item it owned. ", True, INK),
          ("The two NEXT rows are Phase 1 and Phase 3 deliverables, not slippage.", False, MUTED)],
     size=11, first=True, space_after=0)

# ============================================================ 11. PROPOSED vs ACTUAL 2
s = S[10]
strip_body(s)
set_title(s, "6.  What the Plan Did Not Predict  (2 of 2)")

DEV = [
    ("PyCG does not run on Python 3.12 at all",
     "1311 of 1311 reference files fail with ImportManagerError — not a SyntaxError, so §2 anticipated the wrong risk.",
     "Static baselines now run on ≤3.11 while repos are triaged on 3.12. Recorded as deliberate, not discovered from a stack trace."),
    ("The published 0.0.8 sdist is unimportable on Linux",
     "It installs PyCG/ but every internal import reads pycg. It only ever worked on case-insensitive macOS.",
     "Pin held at 0.0.8; every image carries the symlink shim, and the deviation is written into MANIFEST §2.1."),
    ("This Mac cannot build the corpus",
     "8 GB RAM OOM-kills test suites at --jobs 3; the corpus must be built on one architecture.",
     "Mac is the manager host; the Linux x86_64 box executes. The corpus is amd64 and a Mac-triaged repo is development output."),
    ("A patch introduced a silent 16.8× overcount",
     "n_collected matched pytest's pre-deselection total: click read 32965 instead of 1965.",
     "Caught during verification, fixed in both triage.sh and runner.py; the total is kept separately as n_collected_total."),
]
dw = (W - 0.24) / 2
for i, (head, what, resp) in enumerate(DEV):
    col, row = i % 2, i // 2
    x = L + col * (dw + 0.24)
    y = TOP + row * 2.03
    card(s, x, y, dw, 1.88, fill=WHITE, line_col=LINE)
    chip(s, x + 0.20, y + 0.20, 0.34, str(i + 1), size=12)
    tf = textbox(s, x + 0.64, y + 0.19, dw - 0.86, 0.40)
    para(tf, head, size=12.5, bold=True, color=INK, first=True, space_after=0, line=1.0)
    tf = textbox(s, x + 0.20, y + 0.76, dw - 0.40, 1.00)
    para(tf, what, size=10, color=MUTED, first=True, space_after=5, line=1.05)
    rich(tf, [("→  ", True, ORANGE), (resp, False, INK)], size=10, space_after=0, line=1.05)

oy2 = TOP + 4.20
card(s, L, oy2, W, 1.28, fill=CARD)
tf = textbox(s, L + 0.24, oy2 + 0.18, W - 0.48, 0.95)
para(tf, "STILL OPEN — CARRIED INTO PHASE 1", size=10.5, bold=True, color=ORANGE,
     first=True, space_after=6)
for lead, rest in [
    ("Amend ins1 §6. ", "triage.sh v1.2 emits OOM, TIMEOUT, KILLED and collect_partial, which the operator sheet forbids — an operator cannot record what the script prints. validate_sheet.py --v12 is the interim machine check."),
    ("Re-run the 10% human-vs-classifier audit under v1.2, ", "and do not pool the 14 v1.1 spot-check rows with the 558."),
]:
    rich(tf, [("•  ", True, ORANGE), (lead, True, INK), (rest, False, MUTED)],
         size=10, space_after=4, line=1.05)

# ============================================================ 12. CONCLUSION
s = S[11]
strip_body(s)
set_title(s, "7.  Conclusion, Deliverables & Impact")

cw4 = (W - 2 * 0.24) / 3
BLOCKS = [
    ("Key findings", ORANGE, [
        "Phase 0 closed complete and over target: 558 candidates against a plan of ~450.",
        "The field's standard static baseline fails on 100% of files under the interpreter this project defaults to.",
        "Dynamic-feature density is measurable and discriminating once four false-positive classes are removed.",
        "Every headline defect so far was found by running the pipeline, not by reviewing it.",
    ]),
    ("Deliverables", RUN, [
        "DynBench-Core — pinned repos, replayable workloads, reference edge sets, harness.",
        "A pre-registered H2a metric specification, frozen before any extraction code.",
        "Automated triage: triage.sh v1.2 + runner.py with explicit corpus admission.",
        "A tracing-feasibility survey, including the repos that could not be traced.",
    ]),
    ("Impact", GOOD, [
        "Tells graph-conditioned code agents how lossy their retrieval substrate really is.",
        "Names the construct classes to fix, rather than reporting one diffuse percentage.",
        "Benchmarks outlive methods — the artifact stays useful after the number is quoted.",
        "A negative result is still the paper: the conditional claim is the strong one.",
    ]),
]
for i, (head, col, items) in enumerate(BLOCKS):
    x = L + i * (cw4 + 0.24)
    card(s, x, TOP, cw4, 4.20, fill=WHITE, line_col=LINE)
    tf = textbox(s, x + 0.22, TOP + 0.24, cw4 - 0.44, 0.34)
    para(tf, head, size=15, bold=True, color=col, first=True, space_after=0)
    tf = textbox(s, x + 0.22, TOP + 0.80, cw4 - 0.44, 3.25)
    for t in items:
        rich(tf, [("•  ", True, col), (t, False, INK)], size=11, space_after=10, line=1.05)

card(s, L, TOP + 4.42, W, 0.86, fill=SLATE)
tf = textbox(s, L + 0.28, TOP + 4.60, W - 0.56, 0.52, anchor=MSO_ANCHOR.MIDDLE)
rich(tf, [("Every pin, digest and frozen threshold exists so the published number is a "
           "measurement — ", False, WHITE),
          ("not the result of searching until something looked good.", True, C(0xFF, 0xC4, 0x6B))],
     size=12.5, align=PP_ALIGN.CENTER, first=True, space_after=0, line=1.05)

# ============================================================ 13. RESPONSIBILITIES
s = S[12]
strip_body(s)
set_title(s, "8.  Individual Responsibilities")

RESP = [
    ("[Member 1 Name]", "[1AY__AI___]", "Discovery & stratification",
     "discover_candidates.py · density_score.py · scorer calibration and the frozen thresholds"),
    ("[Member 2 Name]", "[1AY__AI___]", "Triage automation",
     "triage.sh v1.2 · runner.py · lockfile pinning, corpus admission and the 10% audit"),
    ("[Member 3 Name]", "[1AY__AI___]", "Static baselines",
     "PyCG 0.0.8 + Pyright 1.1.411 in pinned images · parse-rate measurement · feasibility survey"),
    ("[Member 4 Name]", "[1AY__AI___]", "Tracing, demo & specification",
     "sys.monitoring tracer · live demo and web explainer · metric_spec_h2a.md and MANIFEST"),
]
colx2 = [L + 0.24, L + 2.45, L + 3.85, L + 6.55]
colw2 = [2.10, 1.32, 2.58, 2.30]
flat(card(s, L, TOP, W, 0.44, fill=SLATE))
for i, h in enumerate(["Name", "USN", "Workstream", "Owns"]):
    tf = textbox(s, colx2[i], TOP + 0.11, colw2[i], 0.26)
    para(tf, h.upper(), size=10, bold=True, color=WHITE, first=True, space_after=0)
for i, (nm, usn, ws, owns) in enumerate(RESP):
    y = TOP + 0.44 + i * 0.92
    if i % 2 == 0:
        bar(s, L, y, W, 0.92, C(0xF7, 0xF9, 0xFA))
    tf = textbox(s, colx2[0], y + 0.20, colw2[0], 0.30)
    para(tf, nm, size=12, bold=True, color=INK, first=True, space_after=0)
    tf = textbox(s, colx2[1], y + 0.21, colw2[1], 0.30)
    para(tf, usn, size=11, color=MUTED, first=True, space_after=0)
    tf = textbox(s, colx2[2], y + 0.20, colw2[2], 0.30)
    para(tf, ws, size=11.5, bold=True, color=ORANGE, first=True, space_after=0)
    tf = textbox(s, colx2[3], y + 0.16, colw2[3], 0.62)
    para(tf, owns, size=9.5, color=MUTED, first=True, space_after=0, line=1.05)

gy = TOP + 0.44 + 4 * 0.92 + 0.22
card(s, L, gy, W, 0.80, fill=CARD)
tf = textbox(s, L + 0.24, gy + 0.16, W - 0.48, 0.50, anchor=MSO_ANCHOR.MIDDLE)
rich(tf, [("Guide — [Guide Name], [Designation].  ", True, INK),
          ("Reviews every freeze and version bump, approves the Phase 3 GO / NO-GO, "
           "and supervises submission.", False, MUTED)], size=11, first=True, space_after=0)

tf = textbox(s, L, gy + 0.94, W, 0.34)
para(tf, "Shared across all four: weekly integration, the 10% human-vs-classifier audit, "
         "and rehearsal of the live demo on the presentation machine.",
     size=10, italic=True, color=MUTED, first=True, space_after=0)

# ============================================================ 14. GANTT
s = S[13]
strip_body(s)
set_title(s, "9.  Gantt Chart — Workstreams to the Week 8 Seam")

WEEKS = 8
GX = L + 2.95
GW = R - GX
colwk = GW / WEEKS
GY = TOP + 0.48
ROWH = 0.33
TODAY = 2.85          # weeks elapsed since 2026-07-27

DONE, NOW, NEXT = "done", "now", "next"
TRACKS = [
    ("Discovery & candidate pool",   1, 3, DONE),
    ("Density scorer + calibration", 1, 2, DONE),
    ("Triage atom — triage.sh v1.2", 1, 3, DONE),
    ("runner.py + corpus ledger",    2, 3, DONE),
    ("Static baselines pinned",      2, 3, DONE),
    ("Metric spec — frozen",         1, 1, DONE),
    ("SOP v1.1 + operator sheets",   1, 3, DONE),
    ("Tracer prototype + live demo", 3, 3, DONE),
    ("Corpus build — 558 repos",     3, 5, NOW),
    ("Workload capture (ins2)",      4, 6, NEXT),
    ("Tracing + normalisation",      4, 7, NEXT),
    ("Fusion → H2a → GO / NO-GO",    6, 8, NEXT),
]
FILL = {DONE: GOOD, NOW: ORANGE, NEXT: C(0xD3, 0xDA, 0xE1)}
TAG  = {DONE: "DONE", NOW: "IN PROGRESS", NEXT: ""}
FG   = {DONE: WHITE, NOW: WHITE, NEXT: MUTED}

# legend
lx = L + 2.95
for label, key in [("Delivered", DONE), ("In progress", NOW), ("Planned", NEXT)]:
    sw = card(s, lx, TOP + 0.06, 0.22, 0.14, fill=FILL[key], radius=0.5)
    flat(sw)
    tf = textbox(s, lx + 0.30, TOP + 0.01, 1.10, 0.24)
    para(tf, label, size=9.5, color=MUTED, first=True, space_after=0)
    lx += 1.32

# week header + column rules
for w in range(WEEKS):
    x = GX + w * colwk
    tf = textbox(s, x, GY - 0.28, colwk, 0.22)
    para(tf, f"W{w + 1}", size=9.5, bold=True, color=MUTED, align=PP_ALIGN.CENTER,
         first=True, space_after=0)
    bar(s, x, GY, 0.008, len(TRACKS) * ROWH, C(0xE8, 0xEC, 0xF0))
bar(s, GX + GW - 0.008, GY, 0.008, len(TRACKS) * ROWH, C(0xE8, 0xEC, 0xF0))

for i, (name, w0, w1, state) in enumerate(TRACKS):
    y = GY + i * ROWH
    if i % 2 == 0:
        bar(s, L, y, W, ROWH, C(0xF7, 0xF9, 0xFA))
    tf = textbox(s, L + 0.10, y + 0.09, 2.75, 0.24)
    para(tf, name, size=10, bold=(state != NEXT), color=INK if state != NEXT else MUTED,
         first=True, space_after=0)
    bx = GX + (w0 - 1) * colwk + 0.03
    bw = (w1 - w0 + 1) * colwk - 0.06
    b = flat(card(s, bx, y + 0.07, bw, 0.21, fill=FILL[state], radius=0.5))
    tfb = b.text_frame
    tfb.margin_left = tfb.margin_right = tfb.margin_top = tfb.margin_bottom = 0
    tfb.vertical_anchor = MSO_ANCHOR.MIDDLE
    if TAG[state] and bw > 0.60:
        para(tfb, TAG[state], size=7.5, bold=True, color=FG[state],
             align=PP_ALIGN.CENTER, first=True, space_after=0)

# divider between what is delivered and what remains
bar(s, L, GY + 8 * ROWH, W, 0.012, LINE)

# today marker
tx = GX + TODAY * colwk
bar(s, tx - 0.01, GY - 0.10, 0.02, len(TRACKS) * ROWH + 0.10, MISS)
tf = textbox(s, tx - 0.80, GY + len(TRACKS) * ROWH + 0.03, 1.60, 0.22)
para(tf, "▲  TODAY", size=9, bold=True, color=MISS, align=PP_ALIGN.CENTER,
     first=True, space_after=0)

ny = GY + len(TRACKS) * ROWH + 0.32
card(s, L, ny, W, 0.92, fill=CARD)
tf = textbox(s, L + 0.24, ny + 0.13, W - 0.48, 0.72)
rich(tf, [("Eight of twelve workstreams are delivered, in the first three weeks. ", True, INK),
          ("All four of MANIFEST §7's Phase-1 blockers — the Pyright pin, the PyCG "
           "parse-rate measurement, runner.py and discover_candidates.py — were cleared "
           "before Phase 1 opened.", False, MUTED)],
     size=10, first=True, space_after=5, line=1.05)
rich(tf, [("The chart stops at the Week 8 seam ", True, INK),
          ("because H2a, DynBench-Core and the feasibility survey already form a complete "
           "paper there. H2b-lite and the release run weeks 8–12 beyond it.", False, MUTED)],
     size=10, space_after=0, line=1.05)

# ============================================================ 15. REFERENCES
s = S[14]
strip_body(s)
set_title(s, "10.  References")

REFS = [
    "V. Salis, T. Sotiropoulos, P. Louridas, D. Spinellis, and D. Mitropoulos, “PyCG: "
    "Practical call graph generation in Python,” in Proc. 43rd Int. Conf. Software "
    "Engineering (ICSE), 2021, pp. 1646–1657.",

    "A. S. P, S. Shankar, S. Singh, P. S. Upadhyaya, and A. Kumar, “Graph-aware "
    "neuro-symbolic approaches for legacy modernization: A systematic review,” 2026, "
    "under review.",

    "M. Shannon, “PEP 669 — Low impact monitoring for CPython,” Python Enhancement "
    "Proposals, Python Software Foundation, 2022.",

    "R. Bairi, A. Sonwane, A. Kanade, S. Iyer, S. Parthasarathy, S. Rajamani, B. Ashok, "
    "and S. Shet, “CodePlan: Repository-level coding using LLMs and planning,” in Proc. "
    "Int. Conf. Learning Representations (ICLR), 2024.",

    "S. Ouyang, W. Yu, K. Ma, Z. Xiao, Z. Zhang, M. Jia, J. Han, H. Zhang, and D. Yu, "
    "“RepoGraph: Enhancing AI software engineering with repository-level code graph,” "
    "in Proc. Int. Conf. Learning Representations (ICLR), 2025.",

    "Y. Pan, J. Zhao, C. Wang, and Q. Liu, “RepoTransBench: A real-world benchmark for "
    "repository-level code translation,” arXiv:2412.17744, 2024.",

    "A. R. Ibrahimzada, K. Ke, M. Pawagi, M. S. Abid, R. Pan, S. Sinha, and R. Jabbarvand, "
    "“Repository-level compositional code translation and validation,” arXiv:2410.24117, 2024.",

    "D. Guo, S. Ren, S. Lu, Z. Feng, D. Tang, S. Liu, L. Zhou, N. Duan, A. Svyatkovskiy, "
    "S. Fu, M. Tufano, S. Deng, C. Clement, D. Drain, N. Sundaresan, J. Yin, D. Jiang, and "
    "M. Zhou, “GraphCodeBERT: Pre-training code representations with data flow,” in Proc. "
    "Int. Conf. Learning Representations (ICLR), 2021.",

    "Microsoft, “Pyright: Static type checker for Python,” version 1.1.411, 2026. "
    "[Online]. Available: https://github.com/microsoft/pyright",

    "Python Software Foundation, “ast — Abstract syntax trees,” Python 3.12 documentation, "
    "2026. [Online]. Available: https://docs.python.org/3.12/library/ast.html",
]
rw = (W - 0.30) / 2
for i, ref in enumerate(REFS):
    col, row = i // 5, i % 5
    x = L + col * (rw + 0.30)
    y = TOP + row * 1.06
    tf = textbox(s, x, y, 0.44, 0.30)
    para(tf, f"[{i+1}]", size=11, bold=True, color=ORANGE, first=True, space_after=0)
    tf = textbox(s, x + 0.44, y, rw - 0.44, 1.00)
    para(tf, ref, size=10, color=INK, first=True, space_after=0, line=1.05)

tf = textbox(s, L, TOP + 5.36, W, 0.30)
para(tf, "IEEE reference format.  Internal project documents (MANIFEST.md, "
         "metric_spec_h2a.md, density_scorer_spec.md) are cited in the report, not here.",
     size=9.5, italic=True, color=MUTED, first=True, space_after=0)

# ============================================================ 16. THANK YOU
s = S[15]
for sh in s.shapes:
    if sh.has_text_frame and "Thank you" in sh.text_frame.text:
        tf = sh.text_frame
        for p in tf.paragraphs:
            for r in p.runs:
                r.font.color.rgb = INK

prs.save("TraceWeave-Core_PhaseII_Interim.pptx")
print("saved: TraceWeave-Core_PhaseII_Interim.pptx  ", len(prs.slides.__iter__.__self__._sldIdLst)
      if hasattr(prs.slides, "_sldIdLst") else "", "slides")
