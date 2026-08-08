# Deploying the project explainer

Two build targets, because they have opposite requirements:

| Command | Output | For |
|---|---|---|
| `pnpm build` | `build/` — split, hashed, cacheable assets | **Vercel** |
| `pnpm build:artifact` | `artifact/index.html` — one self-contained file | Claude artifact (its CSP blocks external files) |

Both are produced from the same `src/`. Editing content means editing
[`src/App.tsx`](src/App.tsx) — the phases, chapters, roles and glossary are all plain data arrays
near the top of that file.

---

## Deploy to Vercel

### Option A — from this folder, no git (quickest)

```bash
pnpm build
```

```bash
npx vercel deploy build --prod
```

The first run asks which Vercel account/project to use and remembers it. Because you are pointing it
at a folder that is already built, Vercel serves it as-is and runs no build of its own.

### Option B — from git (Vercel rebuilds on every push)

Push this `traceweave-explainer/` directory to a repository and import it in the Vercel dashboard.
[`vercel.json`](vercel.json) already tells Vercel everything it needs:

```json
"framework": "vite",
"buildCommand": "vite build",
"outputDirectory": "build"
```

Set **Root Directory** to `traceweave-explainer` if you push the whole research repo rather than just
this folder — otherwise Vercel will look for `package.json` at the top and fail.

> `buildCommand` is `vite build`, not `pnpm build`, on purpose. `pnpm build` also runs `tsc -b`,
> which is useful locally but only slows a deploy down and gives it one more way to fail.

### Option C — drag and drop

Run `pnpm build`, then drag the `build/` folder onto the Vercel dashboard's deploy area. No CLI, no
git. Fine for a one-off; you lose the ability to redeploy from a push.

---

## What `vercel.json` sets

- **`/assets/*` cached for a year, immutable.** Safe because Vite fingerprints those filenames — a
  content change produces a new name, so a stale cache can never serve the wrong file.
- **`X-Robots-Tag: noindex, nofollow`** on everything, and the same as a `<meta>` tag in
  `index.html`. This is an internal document. **If you want it publicly findable, remove both.**

Note that noindex is not access control — anyone with the URL can read it. If it needs to be
genuinely private, use Vercel's password protection or a preview deployment (both require a paid
plan).

---

## Local development

```bash
pnpm install
```

```bash
pnpm dev
```

Then open the URL it prints. Edits reload instantly.

To check a production build locally before deploying:

```bash
pnpm build && pnpm preview
```

---

## Updating the Claude artifact

The link shared with the team points at a self-contained copy, not at Vercel. After changing
content, regenerate and republish it:

```bash
pnpm build:artifact && cp artifact/index.html ../major/project-explainer.html
```

Then ask Claude to republish `major/project-explainer.html` — republishing the same path keeps the
same URL, so the link already shared with the team keeps working.

---

## Things worth knowing

**No external fonts.** The page uses system typefaces only (Helvetica Neue / Arial Narrow for
headings, Charter / Sitka Text / Cambria for body, SF Mono / Cascadia for data). Nothing is fetched
from a font CDN, so there is no flash of unstyled text and no third-party request. The trade-off is
that the exact faces differ slightly between macOS, Windows and Linux — all three stacks were chosen
so it stays coherent either way.

**Light and dark are designed separately**, not inverted. Both are driven by CSS custom properties in
[`src/index.css`](src/index.css); if you change a colour, change it in all four blocks — `:root`, the
`prefers-color-scheme: dark` media query, and the two `[data-theme]` overrides.

**The diagram is hand-placed SVG** in `src/App.tsx` (`NODES`, `DRAWN`, `MISSED`). Its `viewBox` is
600 units wide deliberately: SVG text scales with the viewBox, so a smaller one magnifies the labels
and stroke widths well past their intended size.

**The phase spine encodes state.** It renders solid down to the current phase and dashed below it —
mirroring the study's own subject, where a solid line is a path already travelled. If you change
which phase is current, set `status: "now"` on it and `"future"` on the ones after; the line and the
markers follow automatically.
