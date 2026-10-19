import { useState } from "react";
import {
  edgeKey,
  type ConstructCard,
  type ConstructRow,
  type ConstructsFile,
} from "@/lib/realDemo";

const OUTCOME_LABEL: Record<ConstructCard["outcome"], string> = {
  found: "PyCG finds it",
  missed: "PyCG misses it",
  "resolved-in-small": "Resolved here, missed in click",
};

function stripMeta(source: string): string {
  // The META block is machine-readable bookkeeping, not the specimen. Showing
  // it would bury the eight lines that actually demonstrate the construct.
  const start = source.indexOf("META = {");
  if (start === -1) return source.trim();
  const end = source.indexOf("\n}", start);
  const rest = end === -1 ? "" : source.slice(end + 2);
  return (source.slice(0, start) + rest).replace(/\n{3,}/g, "\n\n").trim();
}

function docstringOf(source: string): string {
  const match = source.match(/^"""([\s\S]*?)"""/);
  return match ? match[1].trim() : "";
}

function codeOf(source: string): string {
  return stripMeta(source).replace(/^"""[\s\S]*?"""\s*/, "").trim();
}

function ConstructCardView({ card, clickRow }: { card: ConstructCard; clickRow?: ConstructRow }) {
  const [open, setOpen] = useState(false);
  const missing = new Set(card.missing_edges.map(edgeKey));

  return (
    <article className={`construct-card outcome-${card.outcome}`}>
      <header className="stack gap-1">
        <div className="construct-head">
          <h3 className="construct-title">{card.title}</h3>
          <span className={`pill pill-${card.outcome}`}>{OUTCOME_LABEL[card.outcome]}</span>
        </div>
        <p className="note">{card.blurb}</p>
      </header>

      <pre className="construct-code">
        <code>{codeOf(card.source)}</code>
      </pre>

      <div className="construct-edges">
        {card.runtime_edges.map((e) => {
          const isMissing = missing.has(edgeKey(e));
          return (
            <div key={edgeKey(e)} className={`edge-row ${isMissing ? "is-missing" : ""}`}>
              <span className="marker">{isMissing ? "✕" : "✓"}</span>
              <span className="mono micro">
                {e.caller.replace("fixture.", "")} → {e.callee.replace("fixture.", "")}
              </span>
            </div>
          );
        })}
      </div>

      {/* Read live from the click measurement where the classifier uses the
          same bucket name, so these can never drift from the run above. The
          fixture's own click_evidence string is only a fallback for
          constructs the classifier has no bucket for. */}
      {clickRow ? (
        <p className="note construct-evidence">
          In click:{" "}
          <strong>
            {clickRow.missing}/{clickRow.total} missed (
            {(clickRow.ratio * 100).toFixed(0)}%)
          </strong>
        </p>
      ) : (
        card.click_evidence && (
          <p className="note construct-evidence">
            In click: <strong>{card.click_evidence}</strong>
          </p>
        )
      )}

      <footer className="stack gap-1">
        <p className="micro faint">
          {card.citation_url ? (
            <a href={card.citation_url} target="_blank" rel="noreferrer">
              {card.citation}
            </a>
          ) : (
            card.citation
          )}
        </p>
        <button type="button" className="micro" onClick={() => setOpen((v) => !v)}>
          {open ? "hide reasoning" : "why this fixture exists"}
        </button>
        {open && <p className="note note-faint construct-why">{docstringOf(card.source)}</p>}
      </footer>
    </article>
  );
}

export function ConstructGrid({
  data,
  clickConstructs = [],
}: {
  data: ConstructsFile;
  clickConstructs?: ConstructRow[];
}) {
  const rowFor = (slug: string) => clickConstructs.find((r) => r.construct === slug);
  const missed = data.constructs.filter((c) => c.outcome === "missed");
  const contrast = data.constructs.filter((c) => c.outcome === "resolved-in-small");
  const controls = data.constructs.filter((c) => c.outcome === "found");

  return (
    <div className="wrap stack gap-4">
      <div className="stack gap-1">
        <div className="rule-heavy" style={{ maxWidth: "5rem" }} />
        <p className="eyebrow" style={{ margin: 0 }}>
          The taxonomy
        </p>
        <h2>Which constructs, specifically</h2>
        <p className="deck">
          The hypothesis is not "static analysis is bad". It is that the misses concentrate in
          nameable constructs. Each card is a minimal program exercising one of them, put through
          the identical pipeline: PyCG in the pinned container, the same tracer, the same diff.
        </p>
      </div>

      <div className="notice">
        <p className="note">
          Each fixture states, in its own source, the edge it predicts will be missed. The build
          script verifies the prediction and{" "}
          {data.n_failed_predictions === 0 ? (
            <>
              all {data.constructs.length} currently hold. Two of them originally predicted a miss,
              were proven wrong, and had their expectation corrected rather than the fixture
              reshaped until it failed. Those are the contrast cards below.
            </>
          ) : (
            <>
              <strong>{data.n_failed_predictions}</strong> currently fail, which is shown rather
              than hidden.
            </>
          )}
        </p>
      </div>

      <p className="micro faint">Missed even at twenty lines</p>
      <div className="construct-grid">
        {missed.map((c) => (
          <ConstructCardView key={c.dir} card={c} clickRow={rowFor(c.construct)} />
        ))}
      </div>

      <p className="micro faint">
        Resolved at fixture scale, missed in click. The construct alone is not what defeats the
        analysis
      </p>
      <div className="construct-grid">
        {contrast.map((c) => (
          <ConstructCardView key={c.dir} card={c} clickRow={rowFor(c.construct)} />
        ))}
      </div>

      <p className="micro faint">Controls: these should be found, and are</p>
      <div className="construct-grid">
        {controls.map((c) => (
          <ConstructCardView key={c.dir} card={c} clickRow={rowFor(c.construct)} />
        ))}
      </div>
    </div>
  );
}
