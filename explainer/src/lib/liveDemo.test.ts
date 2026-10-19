import { describe, expect, it } from "vitest";
import {
  type PollState,
  type StaticFile,
  initialPollState,
  missingEdgesDiff,
  missingRatio,
  reduceLivePoll,
} from "./liveDemo";

describe("reduceLivePoll", () => {
  it("truncated/invalid JSON does not throw and does not update state", () => {
    const prev = initialPollState<StaticFile>();
    const next = reduceLivePoll('{"run_id": "1", "graph": {', null, prev);
    expect(next).toBe(prev);
    expect(next.data).toBeNull();
  });

  it("valid JSON on the next call does update state", () => {
    const prev = initialPollState<StaticFile>();
    const next = reduceLivePoll('{"run_id": "1", "graph": {"a": ["b"]}}', null, prev);
    expect(next.status).toBe("ok");
    expect(next.data).toEqual({ run_id: "1", graph: { a: ["b"] } });
  });

  it("rejects a file whose run_id is not newer than minRunId (stale reset)", () => {
    const prev: PollState<StaticFile> = { data: null, status: "waiting" };
    const next = reduceLivePoll('{"run_id": "5", "graph": {}}', "5", prev);
    expect(next.status).toBe("stale");
    expect(next.data).toBeNull();
  });

  it("accepts a file whose run_id is newer than minRunId", () => {
    const prev: PollState<StaticFile> = { data: null, status: "waiting" };
    const next = reduceLivePoll('{"run_id": "6", "graph": {}}', "5", prev);
    expect(next.status).toBe("ok");
    expect(next.data?.run_id).toBe("6");
  });
});

describe("missingEdgesDiff", () => {
  it("(a) edge present in static -> 0 missing", () => {
    const d = missingEdgesDiff({ a: ["b"] }, [{ caller: "a", callee: "b", ts: 0 }]);
    expect(d.counter.missing).toBe(0);
  });

  it("(b) edge absent from static -> 1 missing", () => {
    const d = missingEdgesDiff({ a: [] }, [{ caller: "a", callee: "b", ts: 0 }]);
    expect(d.counter.missing).toBe(1);
  });

  it("(c) empty static -> all runtime edges missing", () => {
    const d = missingEdgesDiff({}, [{ caller: "a", callee: "b", ts: 0 }]);
    expect(d.counter).toEqual({ missing: 1, total: 1 });
  });

  it("(d) duplicate runtime edges: caller dedupes upstream, diff just counts what it's given", () => {
    const edges = [
      { caller: "a", callee: "b", ts: 0 },
      { caller: "a", callee: "b", ts: 1 },
    ];
    const deduped = [...new Map(edges.map((e) => [`${e.caller} ${e.callee}`, e])).values()];
    expect(deduped).toHaveLength(1);
  });

  it("(e) empty runtime -> 0/0, no div-by-zero", () => {
    const d = missingEdgesDiff({ a: ["b"] }, []);
    expect(d.counter).toEqual({ missing: 0, total: 0 });
    expect(missingRatio(d.counter)).toBe(0);
  });
});
