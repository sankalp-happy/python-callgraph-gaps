import { DENSITY_STRATA, EVIDENTIARY_FRAMING, EVIDENTIARY_FRAMING_DETAIL, PYCG_PY310, PYCG_PY312 } from "@/lib/evidence";

const bar = (pct: number, color: string) => (
  <div style={{ background: "var(--rule-soft)", borderRadius: 3, height: 10, overflow: "hidden" }}>
    <div style={{ width: `${Math.max(pct, 2)}%`, background: color, height: "100%" }} />
  </div>
);

export function EvidencePanel() {
  const maxRate = Math.max(...PYCG_PY310.perRepo.map((r) => r.ratePct), 1);
  const totalStrata = DENSITY_STRATA.reduce((sum, s) => sum + s.count, 0);

  return (
    <div className="wrap stack gap-4">
      <div className="stack gap-1">
        <p className="eyebrow" style={{ margin: 0 }}>
          Wider evidence
        </p>
        <h2>What we measured across 14 real, well-known repos</h2>
      </div>

      <div className="row-2col">
        <p className="micro faint">PyCG 0.0.8, Python 3.10 vs 3.12</p>
        <div className="stack gap-2">
          <p>
            <strong>{PYCG_PY310.overallFailed} / {PYCG_PY310.overallTotal} files</strong> ({(
              (PYCG_PY310.overallFailed / PYCG_PY310.overallTotal) * 100
            ).toFixed(1)}%) fail to parse under Python 3.10.
          </p>
          <p>
            <strong>{PYCG_PY312.overallFailed} / {PYCG_PY312.overallTotal} files</strong> (100%) fail
            under Python 3.12. The field's standard static call-graph tool cannot run at all on the
            Python version most people use today (<code className="micro">{PYCG_PY312.failureSignature}</code>).
          </p>
        </div>
      </div>

      <div className="stack gap-2">
        <p className="micro faint">Per-repo parse-failure rate, Python 3.10</p>
        {PYCG_PY310.perRepo.map((r) => (
          <div key={r.repo} className="stack gap-1" style={{ display: "grid", gridTemplateColumns: "6rem 1fr 3rem", alignItems: "center", gap: ".6rem" }}>
            <span className="micro">{r.repo}</span>
            {bar((r.ratePct / maxRate) * 100, "var(--steel)")}
            <span className="micro faint">{r.ratePct}%</span>
          </div>
        ))}
      </div>

      <div className="row-2col">
        <p className="micro faint">Density stratification (599-repo candidate pool)</p>
        <div className="stack gap-1">
          {DENSITY_STRATA.map((s) => (
            <div key={s.stratum} className="stack gap-1" style={{ display: "grid", gridTemplateColumns: "6rem 1fr 3rem", alignItems: "center", gap: ".6rem" }}>
              <span className="micro">{s.stratum}</span>
              {bar((s.count / totalStrata) * 100, "var(--accent)")}
              <span className="micro faint">{s.count}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="row-2col">
        <p className="micro faint">What each number does and does not support</p>
        <div className="stack gap-2">
          <p style={{ fontStyle: "italic" }}>&ldquo;{EVIDENTIARY_FRAMING}&rdquo;</p>
          <p className="note note-faint">{EVIDENTIARY_FRAMING_DETAIL}</p>
        </div>
      </div>
    </div>
  );
}
