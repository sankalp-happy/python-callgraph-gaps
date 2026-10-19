// Cached, already-computed evidence (design doc: Premise 2 -- never
// recomputed live). Frozen from real output on 2026-08-15:
//   TW_DATA=~/traceweave-data python3 traceweave/scripts/pycg_parse_rate.py report --pyver 3.10
//   TW_DATA=~/traceweave-data python3 traceweave/scripts/pycg_parse_rate.py report --pyver 3.12
// and traceweave/candidates/02_scored.jsonl's stratum counts.
//
// Baked in as a TS constant, not fetched at runtime, so this panel (unlike
// the live-execution page) also works from a built static bundle.

export interface RepoFailureRate {
  repo: string;
  analysed: number;
  failed: number;
  ratePct: number;
}

export const PYCG_PY310: { overallFailed: number; overallTotal: number; perRepo: RepoFailureRate[] } = {
  overallFailed: 32,
  overallTotal: 1311,
  perRepo: [
    { repo: "black", analysed: 120, failed: 11, ratePct: 9.2 },
    { repo: "sqlalchemy", analysed: 120, failed: 9, ratePct: 7.5 },
    { repo: "requests", analysed: 37, failed: 1, ratePct: 2.7 },
    { repo: "click", analysed: 78, failed: 2, ratePct: 2.6 },
    { repo: "Python", analysed: 120, failed: 3, ratePct: 2.5 },
    { repo: "ansible", analysed: 120, failed: 2, ratePct: 1.7 },
    { repo: "flask", analysed: 83, failed: 1, ratePct: 1.2 },
    { repo: "celery", analysed: 120, failed: 1, ratePct: 0.8 },
    { repo: "django", analysed: 120, failed: 1, ratePct: 0.8 },
    { repo: "pytest", analysed: 120, failed: 1, ratePct: 0.8 },
    { repo: "chardet", analysed: 93, failed: 0, ratePct: 0 },
    { repo: "records", analysed: 9, failed: 0, ratePct: 0 },
    { repo: "scrapy", analysed: 120, failed: 0, ratePct: 0 },
    { repo: "toolz", analysed: 51, failed: 0, ratePct: 0 },
  ],
};

export const PYCG_PY312 = {
  overallFailed: 1311,
  overallTotal: 1311,
  failureSignature: "ImportManagerError: Can't add edge to a non existing node",
};

export const DENSITY_STRATA: { stratum: string; count: number }[] = [
  { stratum: "LOW", count: 246 },
  { stratum: "MED", count: 177 },
  { stratum: "HIGH", count: 135 },
  { stratum: "TOO_SMALL", count: 41 },
];

export const EVIDENTIARY_FRAMING =
  "Three different kinds of evidence sit on this page, and they are not " +
  "interchangeable. Keep them apart when quoting any of it.";

export const EVIDENTIARY_FRAMING_DETAIL =
  "The 2.4% / 100% PyCG figures above are a measured parse-compatibility fact across 14 " +
  "repositories. A tool from the field's own literature failing to parse most files under " +
  "Python 3.12. The construct fixtures are demonstrations of shape, not rates: they are " +
  "written by us, and two of them turned out to be resolvable. The click measurement is the " +
  "only one that compares real static output against real execution, and it is n = 1: one " +
  "repository, one workload, one PyCG run whose output is known not to be reproducible. " +
  "None of the three is yet the H2a corpus result, which needs the sampled repo set and " +
  "multiple workloads per repo. What has changed since Phase 0 is that the dynamic tracer " +
  "now exists and has been run end-to-end on a real library, so the question is no longer " +
  "unanswerable, just not yet answered at the scale the claim requires.";
