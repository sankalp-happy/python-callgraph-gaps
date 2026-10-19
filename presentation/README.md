# Review-panel material

## The Phase-II interim deck

| File | What it is |
|---|---|
| `PhaseII_Interim_submitted.pptx` / `.pdf` | **The authoritative deck.** What was presented: real member names, USNs and date filled in. Hand-finished in PowerPoint after generation. |
| `PhaseII_Interim_generated.pptx` / `.pdf` | `build.py`'s raw output, with `[Member 1 Name]`-style placeholders still in it. Kept as the generated baseline. |
| `slide_content.md` | Full slide content, 16 slides — the source of truth for wording. |
| `speaker_script.md` | ~1 min per slide, written for a panel of CS faculty without deep SE background. |
| `template_phase2.pptx` | The department's Phase-II template as supplied (5 slides). |
| `build.py` | Fills a template with the TraceWeave-Core content. **See the caveat below.** |
| `PhaseII_Interim_bullets.pptx` / `.pdf` | **Text-only bullet variant** of the submitted deck: black headers and bullets, no diagrams, boxes, icons or tables. Slides 1 (title), 2 (contents), 14 (Gantt) and 16 are the submitted originals, untouched. |
| `bulletize.py` | Regenerates that variant from `PhaseII_Interim_submitted.pptx`. Runnable as-is; it strips every content shape, keeps the template chrome, and picks a per-slide font size that fits the 9 × 5.76 in content box. |

### `build.py` is not runnable as it stands

`build.py` opens a file named `deck.pptx` and edits slides `S[0]` through `S[15]` **in place** — it
never adds a slide. So its input must already be a **16-slide** deck. `template_phase2.pptx` has
only 5 slides, and the 16-slide `deck.pptx` that was actually used is not in the repo and is not
anywhere else on this machine.

Consequences, so nobody rediscovers this at a deadline:

- Renaming `template_phase2.pptx` to `deck.pptx` **does not work** — it fails with
  `IndexError: list index out of range` at slide 6.
- Do **not** point `build.py` at `PhaseII_Interim_generated.pptx` either. That is `build.py`'s own
  output; re-running over it would double-apply every edit.
- To make the deck rebuildable again, recreate `deck.pptx`: open `template_phase2.pptx` and
  duplicate its content slide until the deck is 16 slides, in the order `slide_content.md` lists,
  then commit it next to `build.py`.

Until then, `PhaseII_Interim_submitted.pptx` is the artifact, and `slide_content.md` is where
wording changes belong.

## The pipeline flowchart

| File | What it is |
|---|---|
| `pipeline_flow.png` | Landscape 16:10 flowchart of the six-stage H2a measurement pipeline, 3200 x 2000 px. Sized to drop into the deck's 9 x 5.76 in content box. |
| `pipeline_flow.html` | The source. Regenerate with the command below — plain HTML/CSS, no dependencies beyond a Chrome binary. |
| `pipeline_flow_speech.md` | ~3 min script explaining the flowchart, same voice and audience as `speaker_script.md`. |

```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --hide-scrollbars --force-device-scale-factor=2 --window-size=1600,1000 \
  --screenshot=pipeline_flow.png "file://$PWD/pipeline_flow.html"
```

Mermaid was tried first and abandoned: `mmdc` ignores `direction` inside a subgraph whose nodes
have edges leaving it, so the three bands cannot be made to serpentine and the output comes out
either 7:1 wide or 1:2.4 tall. The HTML gives an exact aspect ratio for the cost of ~90 lines of CSS.

## Other material

| File | What it is |
|---|---|
| `viva/VIVA_QUESTIONS.md` / `.pdf` | Anticipated professor questions with plain-English answers, for a non-technical panel. The PDF is generated from the Markdown. |
| `TraceWeave-Core-Explained.pdf` | 29-page print export of the explainer site (`../project-explainer.html`). Regenerate by printing that page to PDF from Chromium. |
