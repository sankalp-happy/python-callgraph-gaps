// Pure, framework-free logic for the Live Demo page (design doc: Data
// contract). Kept separate from the polling/React code so the poll-parse-
// retry mechanism and the missing-edge diff can be unit-tested without
// mocking fetch or rendering anything.

export interface StaticFile {
  run_id: string;
  graph: Record<string, string[]>;
}

export interface RuntimeEdge {
  caller: string;
  callee: string;
  ts: number;
}

export interface RuntimeFile {
  run_id: string;
  edges: RuntimeEdge[];
}

export type PollStatus = "waiting" | "stale" | "ok";

export interface PollState<T> {
  data: T | null;
  status: PollStatus;
}

export const initialPollState = <T,>(): PollState<T> => ({ data: null, status: "waiting" });

/**
 * One poll tick's worth of logic: parse the raw file text, reject it if
 * malformed (both writers use atomic write + rename, but a poll can still
 * land mid-write on some filesystems) or if it's stale (a leftover file from
 * before the presenter clicked "start new run").
 *
 * `minRunId`: reject any file whose run_id is not strictly greater than
 * this. `null` means "accept the first file that shows up" (no run started
 * yet). Epoch-seconds run ids are monotonically increasing, so "greater
 * than the last accepted run" is enough to catch a forgotten reset -- the
 * browser never needs to know the terminal's *next* run_id in advance.
 */
export function reduceLivePoll<T extends { run_id: string }>(
  raw: string,
  minRunId: string | null,
  prev: PollState<T>,
): PollState<T> {
  let parsed: T;
  try {
    parsed = JSON.parse(raw) as T;
  } catch {
    return prev;
  }
  if (minRunId !== null && !(Number(parsed.run_id) > Number(minRunId))) {
    return { data: prev.data, status: "stale" };
  }
  return { data: parsed, status: "ok" };
}

export interface DiffResult {
  missingEdges: RuntimeEdge[];
  counter: { missing: number; total: number };
}

const pairKey = (caller: string, callee: string) => `${caller} ${callee}`;

/** JS port of traceweave/demo/tracer.py's diff_missing_edges -- keep the two in sync. */
export function missingEdgesDiff(
  staticGraph: Record<string, string[]>,
  runtimeEdges: RuntimeEdge[],
): DiffResult {
  const staticPairs = new Set<string>();
  for (const [caller, callees] of Object.entries(staticGraph)) {
    for (const callee of callees) staticPairs.add(pairKey(caller, callee));
  }
  const missingEdges = runtimeEdges.filter((e) => !staticPairs.has(pairKey(e.caller, e.callee)));
  return { missingEdges, counter: { missing: missingEdges.length, total: runtimeEdges.length } };
}

/** missing / total, 0 (not NaN/Infinity) when total is 0. */
export function missingRatio(counter: { missing: number; total: number }): number {
  return counter.total ? counter.missing / counter.total : 0;
}
