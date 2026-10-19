#!/usr/bin/env python3
"""Every number the paper quotes, computed from the result files and written as LaTeX macros.

    python3 paper/make_numbers.py > paper/numbers.tex

RQ1/RQ2 read phase1-results/ (the amd64 Phase 1 run). RQ3/RQ4 read the harness bench/learn
outputs once they exist; until then their macros print as \\pending.
"""
import json
import re
import os
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P1 = ROOT / "phase1-results"


def mac(name: str, value) -> None:
    print(f"\\newcommand{{\\{name}}}{{{value}}}")


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}\\%"


triage = {}
for line in (P1 / "triage" / "ledger.jsonl").open():
    r = json.loads(line)
    triage[r["repo_name"]] = r                       # last attempt per repo wins
adm = [r for r in triage.values() if r.get("admit") == "yes"]
mac("nTriaged", len(triage))
mac("nAdmissible", len(adm))
mac("nCollectEmpty", sum(r.get("error_class_runner") == "COLLECT_EMPTY" for r in triage.values()))

S = {}
for f in (P1 / "static").glob("*/summary.json"):
    s = json.loads(f.read_text())
    S[s["repo_name"]] = s
ledger = [json.loads(l) for l in (P1 / "static" / "ledger.jsonl").open()]
status = Counter(r["status"] for r in ledger)
ok = [s for s in S.values() if s["status"] == "ok"]
part = [s for s in S.values() if s["status"] == "partial"]
n_att = len(ledger)
mac("nStaticAttempted", n_att)
mac("nStaticOk", status["ok"])
mac("nPycgFail", status["partial"])
mac("pctPycgFail", pct(status["partial"], n_att))
mac("nLayoutFail", status["no_python_package_found"])
mac("nPyrightOk", sum(s["pyright"]["status"] == "ok" for s in S.values()))
mac("nWithArtifacts", len(S))
nodes = lambda s: s["inventory"]["callable_nodes"]
mac("medNodesOk", int(st.median(map(nodes, ok))))
mac("medNodesFail", int(st.median(map(nodes, part))))
mac("minNodesFail", min(map(nodes, part)))
mac("minNodesFailRepo", min(part, key=nodes)["repo_name"])
# how each PyCG failure failed, per seed (Phase 1 pycg.json): timeouts, crashes, out-of-memory
modes = {}
for sm in part:
    pj = json.loads((P1 / "static" / sm["repo_name"] / "pycg.json").read_text())
    modes[sm["repo_name"]] = {x["status"] for x in pj["run"]["per_seed"]}
mac("nFailTimeout", sum(m == {"timeout"} for m in modes.values()))
mac("nFailCrash", sum(m == {"error"} for m in modes.values()))
mac("nFailOom", sum(m == {"killed"} for m in modes.values()))
mac("nFailMixed", sum(len(m) > 1 for m in modes.values()))

# RQ1b: PyCG non-determinism across PYTHONHASHSEED 0/1/42, on the repos where all seeds finished
spread = {}
secs = []
for f in (P1 / "static").glob("*/pycg.json"):
    d = json.loads(f.read_text())
    runs = [p for p in d["run"]["per_seed"] if p["status"] == "ok"]
    secs += [p["seconds"] for p in runs]
    if len(runs) >= 2:
        e = [p["edges"] for p in runs]
        spread[f.parent.name] = (max(e) - min(e)) / max(e)
nondet = [s for s in ok if s["pycg"]["deterministic_across_seeds"] is False]
mac("nNondet", len(nondet))
mac("pctNondet", pct(len(nondet), len(ok)))
diff = sorted((v, k) for k, v in spread.items() if v > 0)
mac("medSpread", f"{100 * st.median(v for v, _ in diff):.1f}\\%")
mac("nSpreadTen", sum(v >= 0.10 for v, _ in diff))
mac("maxSpread", f"{100 * diff[-1][0]:.0f}\\%")
mac("maxSpreadRepo", diff[-1][1])
for strat in ("LOW", "MED", "HIGH"):
    o = [s for s in ok if s["stratum"] == strat]
    mac(f"nondet{strat.title()}", f"{sum(s in nondet for s in o)}/{len(o)}")
secs.sort()
mac("pycgMedSec", f"{st.median(secs):.1f}")
mac("pycgMaxSec", f"{secs[-1]:.0f}")

# RQ2: agreement on in-universe edges, the 78 repos where both baselines finished
jac = sorted(s["baseline_comparison"]["jaccard"] for s in ok)
q = st.quantiles(jac, n=4)
mac("jacMed", f"{st.median(jac):.2f}")
mac("jacQone", f"{q[0]:.2f}")
mac("jacQthree", f"{q[2]:.2f}")
mac("nJacBelowHalf", sum(j < 0.5 for j in jac))
mac("nJacAboveEight", sum(j >= 0.8 for j in jac))
bc = [s["baseline_comparison"] for s in ok]
mac("pycgOnlyShare", f"{100 * sum(b['pycg_only'] for b in bc) / sum(b['union'] for b in bc):.0f}\\%")
mac("pyrightOnlyShare", f"{100 * sum(b['pyright_only'] for b in bc) / sum(b['union'] for b in bc):.0f}\\%")
mac("nEdgesUnion", f"{sum(b['union'] for b in bc):,}".replace(",", "{,}"))
print("\\newcommand{\\pending}{\\textbf{[pending]}}")
# provenance constants that the prose quotes: discovery, reference set, sampling rounds, harness
disc = json.loads((ROOT / "candidates" / "discovery_run.json").read_text())
mac("nPoolMatched", f"{disc['pool']['matched']:,}".replace(",", "{,}"))
mac("nQueued", disc["counts"]["queued"])
mac("nRefSet", sum(1 for l in (ROOT / "traceweave" / "config" / "reference_repos.txt").open()
                   if l.strip() and not l.lstrip().startswith("#")))
tsv = (ROOT / "traceweave" / "study1" / "repos.tsv").read_text().splitlines()
cut = next(i for i, l in enumerate(tsv) if l.startswith("# --- Extension"))
body = lambda ls: [l.split("\t") for l in ls if l and not l.startswith("#") and not l.startswith("repo\t")]
r1, r2 = body(tsv[:cut]), body(tsv[cut:])
mac("nRoundOne", len(r1))
mac("roundOneStrata", ", ".join(f"{sum(r[1] == k for r in r1)} {k}" for k in ("HIGH", "MED", "LOW")))
mac("nRoundTwo", len(r2))
HZ = Path(os.environ.get("TW_HARNESS", Path.home() / "Projects" / "traceweave-harness"))
sg = HZ / "bundles" / "ShivyC" / "graph.json"
if sg.exists():
    meth = Counter(v["qualname"].rsplit(".", 1)[-1] for v in json.loads(sg.read_text())["nodes"].values() if v["kind"] == "method")
    mac("shivycMakeIl", meth["make_il"])
    mac("shivycMakeAsm", meth["make_asm"])
for repo, name in (("click", "Click"), ("toolz", "Toolz")):
    f = HZ / "results" / "resolve" / f"{repo}.sample.json"
    if f.exists():
        mac(f"sample{name}", len(json.loads(f.read_text()).get("callers", [])))
orc = HZ / "results" / "click.oracle.jsonl"
if orc.exists():
    rows_o = [json.loads(l) for l in orc.open()]
    mac("pilotFusedFails", sum(r["arm"] == "treatment" and r["condition"] == "fused" and not r["pass"] for r in rows_o))


# RQ3/RQ4: traceweave/study1/collect.py output, pooled over every traced repo
R = ROOT / "study1-results" / "rq34.json"
if R.exists():
    d = json.loads(R.read_text())

    def _exact(o):
        """Recompute precision/recall/F1 from tp/fp/fn wherever they appear: round once, here, not twice."""
        if isinstance(o, dict):
            if {"tp", "fp", "fn"} <= o.keys():
                tp, fp, fn = o["tp"], o["fp"], o["fn"]
                o["precision"] = tp / (tp + fp) if tp + fp else 0.0
                o["recall"] = tp / (tp + fn) if tp + fn else 0.0
                o["f1"] = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
            for v in o.values():
                _exact(v)
        elif isinstance(o, list):
            for v in o:
                _exact(v)
    _exact(d)
    reps = d["repos"]
    f2 = lambda x: f"{x:.2f}"
    mac("nRuntimeRepos", len(reps))
    last = {}
    for l in (ROOT / "study1-results" / "ledger.jsonl").open():   # a retried repo's last row wins
        r = json.loads(l)
        last[r["repo"]] = r["status"]
    mac("nRuntimeExcluded", sum(s == "failed" for s in last.values()))
    union = sorted(r["edge_recall"]["union"] for r in reps.values())
    mac("edgeUnionMed", f2(st.median(union)))
    mac("edgeUnionMissMed", f"{100 * (1 - st.median(union)):.0f}\\%")
    mac("nLowRuntime", sum(r["stratum"] == "LOW" for r in reps.values()))
    mac("edgeUnionMin", f2(union[0]))
    mac("edgeUnionMax", f2(union[-1]))
    for tool, name in (("pycg", "Pycg"), ("pyright", "Pyright")):
        mac(f"edge{name}Med", f2(st.median(r["edge_recall"][tool] for r in reps.values())))
    mac("nPyrightBeatsPycg", sum(r["edge_recall"]["pyright"] > r["edge_recall"]["pycg"] for r in reps.values()))
    mac("nObservedPairs", f"{sum(r['observed_edges'] for r in reps.values()):,}".replace(",", "{,}"))
    for strat in ("LOW", "MED", "HIGH"):
        v = [r["edge_recall"]["union"] for r in reps.values() if r["stratum"] == strat]
        mac(f"edgeMed{strat.title()}", f"{f2(st.median(v))} ($n{{=}}{len(v)}$)")
    P = d["pooled"]
    for k, name in (("PyCG", "Pycg"), ("Pyright", "Pyright"), ("PyCG ∪ Pyright", "Union"), ("name match", "Name")):
        mac(f"item{name}P", f2(P[k]["precision"]))
        mac(f"item{name}R", f2(P[k]["recall"]))
    mac("nItems", f"{P['PyCG']['n']:,}".replace(",", "{,}"))
    mac("nRealItems", f"{d['real_items']:,}".replace(",", "{,}"))
    miss = d["misses"]
    nmiss = sum(miss.values())
    mac("nMissed", f"{nmiss:,}".replace(",", "{,}"))
    mac("pctMissShared", pct(sum(v for k, v in miss.items() if k.endswith("/shared")), nmiss))
    mac("pctMissReference", pct(sum(v for k, v in miss.items() if k.startswith("reference/")), nmiss))
    mac("pctUnnamed", pct(d["unnamed"], sum(r["observed_edges"] for r in reps.values())))   # share of observed calls
    mac("nUnnamed", f"{d['unnamed']:,}".replace(",", "{,}"))
    names = {"gpt-oss-20b": "Twenty", "gpt-oss-120b": "OneTwenty", "qwen3.8-27b": "Qwen"}
    for m, x in d["llm"].items():
        mac(f"llm{names[m]}P", f2(x["model"]["precision"]))
        mac(f"llm{names[m]}R", f2(x["model"]["recall"]))
        mac(f"llm{names[m]}StaticP", f2(x["static union, same items"]["precision"]))
        mac(f"llm{names[m]}StaticR", f2(x["static union, same items"]["recall"]))
        mac(f"llm{names[m]}N", f"{x['model']['n']:,}".replace(",", "{,}"))
    c = d.get("combiner")
    if c:
        g = c["grouped_by_caller"]
        for k, name in (("learned combiner", "Comb"), ("PyCG ∪ Pyright", "CombUnion"),
                        ("majority of the 3 LLMs", "Majority"), ("static ∪ any LLM", "AnyLlm")):
            mac(f"cv{name}", f"{f2(g[k]['precision'])} & {f2(g[k]['recall'])} & {f2(g[k]['f1'])}")
        mac("cvCombFone", f2(g["learned combiner"]["f1"]))
        mac("nCombItems", f"{c['items']:,}".replace(",", "{,}"))
        mac("nCombRepos", len(c["repos"]))
        lo = c.get("leave_one_repo_out")
        if lo:
            mac("loroComb", f"{f2(lo['precision'])} & {f2(lo['recall'])} & {f2(lo['f1'])}")
    # per-repo table, one row per traced repo, sorted by stratum then union edge recall
    order = {"LOW": 0, "MED": 1, "HIGH": 2}
    rows = sorted(reps.items(), key=lambda kv: (order.get(kv[1]["stratum"], 3), kv[1]["edge_recall"]["union"]))
    short = {"bedrock-agentcore-sdk-python": "bedrock-agentcore-sdk", "confluence-markdown-exporter": "confluence-md-exporter",
             "mcp-sequential-thinking": "mcp-seq-thinking", "aws-dynamodb-encryption-python": "aws-dynamodb-encryption",
             "python-lazy-object-proxy": "lazy-object-proxy", "python-neutronclient": "neutronclient"}
    cells = []
    for n, r in rows:
        e, s = r["edge_recall"], r["scores"]
        cells.append(f"\\texttt{{{short.get(n, n)}}} & {r['stratum'][0]} & {r['observed_edges']} & "
                     f"{f2(e['pycg'])} & {f2(e['pyright'])} & {f2(e['union'])}")
    half = (len(cells) + 1) // 2               # two repos per table row, so ~40 repos fit a table*
    left, right = cells[:half], cells[half:] + [" & & & & & "] * (2 * half - len(cells))
    mac("rqThreeRows", "\n".join(f"{a} & {b} \\\\" for a, b in zip(left, right)))   # a macro: \input cannot start a row

    # RQ4 by kind of item: recall/precision of the static union and each LLM on the same items
    kinds = [("call/unique", "call, unique name"), ("call/shared", "call, shared name"),
             ("constructor/unique", "class name"), ("reference/unique", "reference, unique name"),
             ("reference/shared", "reference, shared name")]
    K = d.get("llm_by_kind", {})
    order_m = ["gpt-oss-20b", "gpt-oss-120b", "qwen3.8-27b"]
    if K:
        rows4 = []
        for k, label in kinds:
            st_ = K[order_m[0]][k]["static union, same items"]
            prec = lambda x: f2(x["precision"]) if x["tp"] + x["fp"] else "--"   # no claims: precision undefined
            cols = [f"{f2(st_['recall'])} / {prec(st_)}"] + \
                   [f"{f2(K[m][k]['model']['recall'])} / {prec(K[m][k]['model'])}" for m in order_m]
            rows4.append(f"{label} & {K[order_m[0]][k]['model']['n']} & " + " & ".join(cols) + " \\\\")
        mac("rqFourKindRows", "\n".join(rows4))
        rng = lambda k, f: (f2(min(K[m][k]["model"][f] for m in order_m)), f2(max(K[m][k]["model"][f] for m in order_m)))
        stat = lambda k, f: f2(K[order_m[0]][k]["static union, same items"][f])
        mac("kindSharedStaticR", stat("call/shared", "recall"))
        mac("kindSharedLlmR", "--".join(rng("call/shared", "recall")))
        mac("kindRefStaticR", f2(max(K[order_m[0]][k]["static union, same items"]["recall"]
                                     for k in ("reference/unique", "reference/shared"))))
        lo_r = min(K[m][k]["model"]["recall"] for m in order_m for k in ("reference/unique", "reference/shared"))
        hi_r = max(K[m][k]["model"]["recall"] for m in order_m for k in ("reference/unique", "reference/shared"))
        lo_p = min(K[m][k]["model"]["precision"] for m in order_m for k in ("reference/unique", "reference/shared"))
        hi_p = max(K[m][k]["model"]["precision"] for m in order_m for k in ("reference/unique", "reference/shared"))
        mac("kindRefLlmR", f"{f2(lo_r)}--{f2(hi_r)}")
        mac("kindRefLlmP", f"{f2(lo_p)}--{f2(hi_p)}")
        beats = d["llm_beats_static_f1"]
        mac("llmBeatsMin", min(beats.values()))
        mac("llmBeatsMax", max(beats.values()))
        mac("llmReposN", len(d["llm_by_repo"][order_m[0]]))

# methodology checks added after review: coverage, repeat trace, complementarity, bootstrap, LORO
if R.exists():
    if d.get("coverage_vs_recall_spearman") is not None:
        _rk = lambda v: {i: k for k, i in enumerate(sorted(range(len(v)), key=v.__getitem__))}
        def _rho(x, y):
            rx, ry, n = _rk(x), _rk(y), len(x)
            return 1 - 6 * sum((rx[i] - ry[i]) ** 2 for i in range(n)) / (n * (n * n - 1))
        _cv = [(r["line_coverage"], r["edge_recall"]["union"], r["tests_passed"] or 0) for r in reps.values()
               if r.get("line_coverage") is not None]
        mac("covSpearman", f"{_rho([a for a, _, _ in _cv], [b for _, b, _ in _cv]):.2f}")
        mac("testsSpearman", f"{_rho([c for _, _, c in _cv], [b for _, b, _ in _cv]):.2f}")
        cv = sorted(r["line_coverage"] for r in reps.values() if r.get("line_coverage") is not None)
        mac("covMed", f"{100 * st.median(cv):.0f}\\%")
        mac("covMin", f"{100 * cv[0]:.0f}\\%")
        mac("covMax", f"{100 * cv[-1]:.0f}\\%")
    if d.get("retrace"):
        mac("nRetrace", d["retrace"]["repos"])
        mac("retraceJacMin", f2(d["retrace"]["jaccard_min"]))
        mac("retraceJacMed", f2(d["retrace"]["jaccard_median"]))
    if d.get("llm_complementarity"):
        comp = d["llm_complementarity"]
        mac("compMissedR", "--".join(f2(x) for x in sorted({comp[m]["static missed"]["recall"] for m in comp})[::max(1, len(comp) - 1)]))
        mac("compFoundR", "--".join(f2(x) for x in sorted({comp[m]["static found"]["recall"] for m in comp})[::max(1, len(comp) - 1)]))
        mac("nCompMissed", comp[next(iter(comp))]["static missed"]["n"])
    if d.get("bootstrap"):
        bs = d["bootstrap"]
        names4 = {"gpt-oss-20b": "Twenty", "gpt-oss-120b": "OneTwenty", "qwen3.8-27b": "Qwen"}
        for m, x in bs.items():
            for k, kk in (("precision", "Prec"), ("recall", "Rec"), ("f1", "Fone")):
                mac(f"ci{names4[m]}{kk}", f"[{f2(x['model'][k][0])}, {f2(x['model'][k][1])}]")
        sx = next(iter(bs.values()))["static union, same items"]
        for k, kk in (("precision", "Prec"), ("recall", "Rec"), ("f1", "Fone")):
            mac(f"ciStatic{kk}", f"[{f2(sx[k][0])}, {f2(sx[k][1])}]")
    SK = d.get("static_by_kind")
    if SK:
        mac("staticPrecUniqueCall", f2(SK["call/unique"]["PyCG ∪ Pyright"]["precision"]))
        mac("staticPrecSharedCall", f2(SK["call/shared"]["PyCG ∪ Pyright"]["precision"]))
        mac("staticRecallSharedCall", f2(SK["call/shared"]["PyCG ∪ Pyright"]["recall"]))
        mac("pycgRecallCtor", f2(SK["constructor/unique"]["PyCG"]["recall"]))
        mac("pyrightRecallCtor", f2(SK["constructor/unique"]["Pyright"]["recall"]))
    c = d.get("combiner") or {}
    if c.get("loro_all"):
        rows5 = []
        for k, label in (("PyCG", "PyCG"), ("Pyright", "Pyright"), ("PyCG ∪ Pyright", "PyCG $\\cup$ Pyright"),
                         ("majority of the 3 LLMs", "majority of the three LLMs"), ("static ∪ any LLM", "static $\\cup$ any LLM"),
                         ("learned combiner", "learned combiner")):
            x = c["loro_all"][k]
            rows5.append(f"{label} & {f2(x['precision'])} & {f2(x['recall'])} & {f2(x['f1'])} \\\\")
        mac("loroRows", "\n".join(rows5))
        mac("loroCombFone", f2(c["loro_all"]["learned combiner"]["f1"]))
        mac("loroUnionFone", f2(c["loro_all"]["PyCG ∪ Pyright"]["f1"]))
        mac("loroMajorityFone", f2(c["loro_all"]["majority of the 3 LLMs"]["f1"]))
        mac("loroCombP", f2(c["loro_all"]["learned combiner"]["precision"]))
        mac("loroCombR", f2(c["loro_all"]["learned combiner"]["recall"]))
        mac("loroUnionP", f2(c["loro_all"]["PyCG ∪ Pyright"]["precision"]))
        mac("loroUnionR", f2(c["loro_all"]["PyCG ∪ Pyright"]["recall"]))
        by = c["loro_by_repo"]
        mac("nLoroBeats", sum(v["learned combiner"] > v["PyCG ∪ Pyright"] for v in by.values()))
        mac("nLoroWorse", sum(v["learned combiner"] < v["PyCG ∪ Pyright"] for v in by.values()))
        mac("nLoroRepos", len(by))

# dynamism score (the stratifier) against static recall, across traced repos
if R.exists():
    dens = {json.loads(l)["name"]: json.loads(l).get("density_score") for l in (ROOT / "candidates" / "02_scored.jsonl").open()}
    dens |= {"click": 17.39, "toolz": 7.82}          # reference set, docs/density_scorer_spec.md section 2
    dp = [(dens[n], r["edge_recall"]["union"]) for n, r in reps.items() if dens.get(n) is not None]
    rk = lambda v: {i: k for k, i in enumerate(sorted(range(len(v)), key=v.__getitem__))}
    rx, ry, nn = rk([a for a, _ in dp]), rk([b for _, b in dp]), len(dp)
    mac("densitySpearman", f"{1 - 6 * sum((rx[i] - ry[i]) ** 2 for i in range(nn)) / (nn * (nn * nn - 1)):.2f}")

_ds = (ROOT / "traceweave" / "scripts" / "density_score.py").read_text()
mac("thrLowMed", re.search(r"^THRESHOLD_LOW_MED = ([0-9.]+)", _ds, re.M).group(1))
mac("thrMedHigh", re.search(r"^THRESHOLD_MED_HIGH = ([0-9.]+)", _ds, re.M).group(1))

# uncertainty and paired comparisons asked for in review (repository-level resampling, fixed seeds)
import math
import random as _random


def _spearman(x, y):
    rk = lambda v: {i: k for k, i in enumerate(sorted(range(len(v)), key=v.__getitem__))}
    rx, ry, n = rk(x), rk(y), len(x)
    return 1 - 6 * sum((rx[i] - ry[i]) ** 2 for i in range(n)) / (n * (n * n - 1))


def _boot(vals, stat, reps=2000, seed=20261019):
    rnd, n = _random.Random(seed), len(vals)
    out = sorted(stat([vals[rnd.randrange(n)] for _ in range(n)]) for _ in range(reps))
    return out[int(0.025 * reps)], out[int(0.975 * reps) - 1]


def _perm_p(x, y, reps=5000, seed=20261019):
    rnd, obs = _random.Random(seed), abs(_spearman(x, y))
    yy, hit = list(y), 0
    for _ in range(reps):
        rnd.shuffle(yy)
        hit += abs(_spearman(x, yy)) >= obs - 1e-12
    return (hit + 1) / (reps + 1)


def _wilcoxon(diffs):
    """Two-sided signed-rank test, normal approximation with tie correction; zero differences dropped."""
    d = [x for x in diffs if abs(x) > 1e-12]
    n = len(d)
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks, i = [0.0] * n, 0
    while i < n:
        j = i
        while j + 1 < n and abs(abs(d[order[j + 1]]) - abs(d[order[i]])) < 1e-12:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    wplus = sum(r for r, x in zip(ranks, d) if x > 0)
    mu, sd = n * (n + 1) / 4, math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    z = (wplus - mu) / sd if sd else 0.0
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def _fmt_p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


if R.exists():
    ur = [r["edge_recall"]["union"] for r in reps.values()]
    lo, hi = _boot(ur, st.median)
    mac("ciEdgeUnionMed", f"[{f2(lo)}, {f2(hi)}]")
    pairs_rc = [(r["line_coverage"], r["edge_recall"]["union"], r["tests_passed"] or 0) for r in reps.values()
                if r.get("line_coverage") is not None]
    for nm, xs, ys in (("cov", [a for a, _, _ in pairs_rc], [b for _, b, _ in pairs_rc]),
                       ("tests", [c for _, _, c in pairs_rc], [b for _, b, _ in pairs_rc]),
                       ("density", [a for a, _ in dp], [b for _, b in dp])):
        mac(f"{nm}SpearmanExact", f"{_spearman(xs, ys):.3f}")
        mac(f"{nm}SpearmanP", _fmt_p(_perm_p(xs, ys)))
        idx = list(range(len(xs)))
        lo, hi = _boot(idx, lambda ii: _spearman([xs[i] for i in ii], [ys[i] for i in ii]))
        z = lambda v: f"{v:.2f}".replace("-0.00", "0.00")
        mac(f"{nm}SpearmanCI", f"[{z(lo)}, {z(hi)}]")
    diff = [r["edge_recall"]["pyright"] - r["edge_recall"]["pycg"] for r in reps.values()]
    mac("pyrMinusPycgMed", f2(st.median(diff)))
    lo, hi = _boot(diff, st.median)
    mac("ciPyrMinusPycgMed", f"[{f2(lo)}, {f2(hi)}]")
    mac("pyrPycgWilcoxonP", _fmt_p(_wilcoxon(diff)))
    mac("nPyrPycgTies", sum(abs(x) < 1e-12 for x in diff))
    mac("nPyrPycgReversals", sum(x < -1e-12 for x in diff))

# PyCG failures per (repo, seed) in the three-seed run, over the repositories PyCG was run on
runs = []
for sm in S.values():
    pj = P1 / "static" / sm["repo_name"] / "pycg.json"
    if pj.exists():
        runs.append([x["status"] for x in json.loads(pj.read_text())["run"]["per_seed"]])
mac("nPycgRun", len(runs))
mac("pctPycgFailRun", pct(status["partial"], len(runs)))
mac("nPycgAnySeedFail", sum(any(x != "ok" for x in r) for r in runs))
mac("pctPycgSeedRunsFailed", pct(sum(x != "ok" for r in runs for x in r), sum(len(r) for r in runs)))

# independent-review numbers (traceweave/study1/review_stats.py -> study1-results/review.json)
RV = ROOT / "study1-results" / "review.json"
if RV.exists():
    rv = json.loads(RV.read_text())
    for k, nm in (("pycg", "Pycg"), ("pyright", "Pyright"), ("union", "Union")):
        mac(f"poolRecall{nm}", f2(rv["pooled"][k]))           # over ALL observed calls, pair-weighted
    dc = rv["decomp"]
    tot_m = sum(dc.values())
    mac("nMissAll", f"{tot_m:,}".replace(",", "{,}"))
    names_m = {"unnamed/other": "UnnamedOther", "unnamed/dunder": "UnnamedDunder", "call/shared": "CallShared",
               "call/unique": "CallUnique", "reference/shared": "RefShared", "reference/unique": "RefUnique",
               "constructor/unique": "Ctor"}
    for k, nm in names_m.items():
        mac(f"miss{nm}", pct(dc.get(k, 0), tot_m))
        mac(f"medMiss{nm}", f"{100 * rv['decomp_repo_median'].get(k, 0):.0f}\\%")
    order_m2 = sorted(names_m, key=lambda k: -dc.get(k, 0))
    labels_m = {"unnamed/other": "unnamed: library or callback", "unnamed/dunder": "unnamed: special method",
                "call/shared": "call, shared name", "call/unique": "call, unique name",
                "reference/shared": "reference, shared name", "reference/unique": "reference, unique name",
                "constructor/unique": "class name"}
    num = lambda v: f"{v:,}".replace(",", "{,}")
    mac("missDecompRows", "\n".join(f"{labels_m[k]} & {num(dc.get(k, 0))} & {pct(dc.get(k, 0), tot_m)} \\\\"
                                     for k in order_m2))
    mac("missDecompRowsMed", "\n".join(
        f"{labels_m[k]} & {num(dc.get(k, 0))} & {pct(dc.get(k, 0), tot_m)} & {100 * rv['decomp_repo_median'].get(k, 0):.0f}\\% \\\\"
        for k in order_m2))
    un_share = [r["shares"].get("unnamed/other", 0) + r["shares"].get("unnamed/dunder", 0)
                for r in rv["repos"].values() if r["missed"]]
    mac("medMissUnnamedAll", f"{100 * st.median(un_share):.0f}\\%")
    mac("missSharedAll", pct(dc.get("call/shared", 0) + dc.get("reference/shared", 0), tot_m))
    mac("missUnnamedAll", pct(dc.get("unnamed/other", 0) + dc.get("unnamed/dunder", 0), tot_m))
    mac("missReferenceAll", pct(dc.get("reference/shared", 0) + dc.get("reference/unique", 0), tot_m))
    mac("nUnnamedFound", rv["unnamed_found_by_union"])
    mac("pctUnnamedFound", pct(rv["unnamed_found_by_union"], d["unnamed"]))
    mac("nSelfCallItems", rv["self_call_items"])
    rf = rv["reflect"]
    nref = rf.get("reflective/found", 0) + rf.get("reflective/missed", 0)
    nplain = rf.get("plain/found", 0) + rf.get("plain/missed", 0)
    mac("nReflectCalls", nref)
    mac("pctReflectCalls", f"{100 * nref / (nref + nplain):.0f}\\%")
    mac("reflectMissRate", f2(rf.get("reflective/missed", 0) / nref))
    mac("plainMissRate", f2(rf.get("plain/missed", 0) / nplain))
    mac("pctMissReflective", pct(rf.get("reflective/missed", 0), tot_m))
    sm_ = rv["sample"]
    mac("nSampleCallers", sm_["callers"])
    mac("nSampleStaticOnly", sm_["callers_static_wrong_only"])
    mac("sampleBaseRate", pct(sm_["items_observed"], sm_["items"]))
    def _pr(pref):
        tp, fp, fn = sm_.get(pref + "/tp", 0), sm_.get(pref + "/fp", 0), sm_.get(pref + "/fn", 0)
        return tp / (tp + fp), tp / (tp + fn)
    sp_, sr_ = _pr("without_static_wrong_only/static")
    mac("woStaticP", f2(sp_))
    mac("woStaticR", f2(sr_))
    ms = [_pr(f"without_static_wrong_only/{m}") for m in ("gpt-oss-20b", "gpt-oss-120b", "qwen3.8-27b")]
    mac("woLlmR", f"{f2(min(r for _, r in ms))}--{f2(max(r for _, r in ms))}")
    mac("woLlmP", f"{f2(min(p for p, _ in ms))}--{f2(max(p for p, _ in ms))}")

# paired LORO comparisons over repositories (traceweave/study1/loro.py -> study1-results/loro_*.jsonl)
def _loro_stats(path):
    rows_l = [json.loads(l) for l in path.open()]
    rules = {"comb": lambda r: r["p"] >= 0.5, "union": lambda r: r["pycg"] or r["pyright"], "pyright": lambda r: r["pyright"]}
    per = defaultdict(lambda: {k: [0, 0, 0] for k in rules})        # repo -> rule -> [tp, fp, fn]
    for r in rows_l:
        for k, f in rules.items():
            t = per[r["repo"]][k]
            if f(r) and r["label"]:
                t[0] += 1
            elif f(r):
                t[1] += 1
            elif r["label"]:
                t[2] += 1
    def f1(repos_, k):
        tp = sum(per[x][k][0] for x in repos_); fp = sum(per[x][k][1] for x in repos_); fn = sum(per[x][k][2] for x in repos_)
        return 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    names_ = sorted(per)
    rnd, diffs = _random.Random(20261019), {"union": [], "pyright": []}
    for _ in range(2000):
        bs = [names_[rnd.randrange(len(names_))] for _ in names_]
        for k in diffs:
            diffs[k].append(f1(bs, "comb") - f1(bs, k))
    ci = {k: (sorted(v)[50], sorted(v)[1949]) for k, v in diffs.items()}
    return {"f1": {k: f1(names_, k) for k in rules}, "ci": ci, "n_repos": len(names_), "n_items": len(rows_l)}


from collections import defaultdict
LA, LN = ROOT / "study1-results" / "loro_all.jsonl", ROOT / "study1-results" / "loro_noref.jsonl"
if LA.exists():
    la = _loro_stats(LA)
    mac("loroDiffUnion", f2(la["f1"]["comb"] - la["f1"]["union"]))
    mac("ciLoroDiffUnion", f"[{f2(la['ci']['union'][0])}, {f2(la['ci']['union'][1])}]")
    mac("loroDiffPyright", f2(la["f1"]["comb"] - la["f1"]["pyright"]))
    mac("ciLoroDiffPyright", f"[{f2(la['ci']['pyright'][0])}, {f2(la['ci']['pyright'][1])}]")
    mac("loroCheckFone", f2(la["f1"]["comb"]))                        # must equal loroCombFone
if LN.exists():
    ln = _loro_stats(LN)
    mac("loroNorefCombFone", f2(ln["f1"]["comb"]))
    mac("loroNorefUnionFone", f2(ln["f1"]["union"]))
    mac("ciLoroNorefDiffUnion", f"[{f2(ln['ci']['union'][0])}, {f2(ln['ci']['union'][1])}]")
    mac("nLoroNorefRepos", ln["n_repos"])

# unnamed observed calls by kind (study1-results/unnamed.json, harness bench.unnamed)
U = ROOT / "study1-results" / "unnamed.json"
if U.exists():
    u = json.loads(U.read_text())
    tot_u = sum(u["total"].values())
    mac("pctUnnamedDunder", pct(u["total"].get("dunder", 0), tot_u))
    top = u["top"][0]
    mac("unnamedTopRepo", top[1])
    mac("pctUnnamedTopOfRest", pct(top[2].get("named-elsewhere", 0), u["total"].get("named-elsewhere", 0)))

# PyCG seed sweep: traceweave/study1/sweep.py report
SW = ROOT / "study1-results" / "seeds.json"
if SW.exists():
    sw = json.loads(SW.read_text())
    full10 = {n: r for n, r in sw.items() if len(r.get("seeds", {})) >= 10}   # "ten seeds" claims: complete repos only
    swept = {n: r for n, r in full10.items() if "recall_pycg" in r}
    mac("nTenSeed", len(full10))
    if swept:
        spread = {n: r["recall_pycg"][2] - r["recall_pycg"][0] for n, r in swept.items()}
        worst = max(spread, key=spread.get)
        mac("nSwept", len(swept))
        mac("nSweptVaries", sum(v > 0 for v in spread.values()))
        mac("sweepMaxPts", f"{100 * spread[worst]:.0f}")
        mac("sweepMaxDelta", f2(spread[worst]))
        mac("sweepMedDelta", f2(st.median(spread.values())))
        mac("sweepWorstRepo", worst)
        mac("sweepWorstLo", f2(swept[worst]["recall_pycg"][0]))
        mac("sweepWorstHi", f2(swept[worst]["recall_pycg"][2]))
        mac("sweepMedPts", f"{100 * st.median(spread.values()):.1f}")
        mac("sweepMaxGraphs", max(r.get("distinct_graphs", 1) for r in swept.values()))
        us = {n: r["recall_union"][2] - r["recall_union"][0] for n, r in swept.items()}
        mac("sweepUnionMaxPts", f"{100 * max(us.values()):.0f}")
        mac("sweepUnionMaxDelta", f2(max(us.values())))
    mixed = sorted(n for n, r in sw.items() if n != "iterprobe"
                   and {v["status"] for v in r["seeds"].values()} >= {"ok", "timeout"})
    if mixed:
        mac("nMixedTermination", len(mixed))
        mac("mixedTerminationRepo", mixed[0])
    setlvl = {n: r for n, r in full10.items() if "jaccard_min" in r}
    if setlvl:
        mac("nSetSwept", len(setlvl))
        mac("nSetNondet", sum(r["jaccard_min"] < 1 for r in setlvl.values()))
        mac("setJacMin", f2(min(r["jaccard_min"] for r in setlvl.values())))
        mac("setJacMinRepo", min(setlvl, key=lambda n: setlvl[n]["jaccard_min"]))
        obsvary = {n: r for n, r in setlvl.items() if r.get("varying_observed")}
        mac("nVaryObserved", len(obsvary))
        # count-level (Phase 1) against set-level (sweep) on the same repos: why 46% is a lower bound
        p1 = {n: S[n]["pycg"]["deterministic_across_seeds"] for n in setlvl if n in S}
        mac("nRawOnly", sum(p1[n] is False and setlvl[n]["jaccard_min"] == 1 for n in p1))
        mac("nHiddenByCount", sum(p1[n] is True and setlvl[n]["jaccard_min"] < 1 for n in p1))
        mac("nCountNondetSwept", sum(p1[n] is False for n in p1))

# PyCG iteration probes: traceweave/study1/sweep.py iterprobe (copied to study1-results/iterprobe/)
IP = ROOT / "study1-results" / "iterprobe"
if (IP / "chevron.seed0.jsonl").exists():
    rows_ = [json.loads(l) for l in (IP / "chevron.seed0.jsonl").open()]
    growth = {rows_[i + 1]["defs"] - rows_[i]["defs"] for i in range(10, len(rows_) - 1)}
    mac("chevPasses", len(rows_))
    mac("chevDefsFirst", rows_[0]["defs"])
    mac("chevDefsLast", rows_[-1]["defs"])
    mac("chevGrowth", "/".join(map(str, sorted(growth))))
    mac("chevRepeats", sum(r["seen_at"] is not None for r in rows_))
if (IP / "muscriptor.seed0.jsonl").exists():
    mr = [json.loads(l) for l in (IP / "muscriptor.seed0.jsonl").open()]
    mac("muscNamesFirst", f"{mr[0]['names']:,}".replace(",", "{,}"))
    mac("muscNamesLast", f"{mr[-1]['names']:,}".replace(",", "{,}"))
    mac("muscPasses", len(mr) - 1)
    mac("muscLastPassMin", f"{(mr[-1]['seconds'] - mr[-2]['seconds']) / 60:.0f}")

# third review round: seed severity, same-seed control, small-n sensitivity, LLM baselines
import tarfile
if SW.exists() and (ROOT / "study1-results" / "seeds.tar.gz").exists():
    Jn = sorted(r["jaccard_min"] for r in full10.values() if "jaccard_min" in r and r["jaccard_min"] < 1)
    qj = st.quantiles(Jn, n=4)
    mac("setJacMed", f"{st.median(Jn):.2f}")
    mac("setJacQone", f"{qj[0]:.2f}")
    mac("setJacQthree", f"{qj[2]:.2f}")
    mac("nSetJacBelowNine", sum(j < 0.9 for j in Jn))
    lone = [n for n in full10 if "jaccard_min" not in full10[n]]
    mac("setSweptMissingRepo", lone[0] if lone else "none")
    with tarfile.open(ROOT / "study1-results" / "seeds.tar.gz") as tf:
        sw_seed = {}
        for m in tf.getmembers():
            parts = m.name.split("/")
            if m.isfile() and len(parts) == 3 and parts[2] in ("seed0.json", "seed1.json"):
                sw_seed[(parts[1], parts[2][4])] = json.load(tf.extractfile(m))
    agree = same_e = diff_e = 0
    for (n, sd), rec in sw_seed.items():
        pj = P1 / "static" / n / "pycg.json"
        if not pj.exists():
            continue
        p1j = json.loads(pj.read_text())
        per = {x["seed"]: x["status"] for x in p1j["run"]["per_seed"]}
        if sd in per:
            agree += (per[sd] == "ok") == (rec["status"] == "ok")
        if sd == "0" and p1j["run"].get("deterministic_across_seeds") is True and sw.get(n, {}).get("distinct_graphs") == 1:
            if set(rec.get("edges", [])) == set(p1j["edges"]["in_universe_edges"]):
                same_e += 1
            else:
                diff_e += 1
    mac("nRepeatSeedRuns", sum(1 for (n, sd) in sw_seed if (P1 / "static" / n / "pycg.json").exists()
                                 and sd in {x["seed"] for x in json.loads((P1 / "static" / n / "pycg.json").read_text())["run"]["per_seed"]}))
    mac("nRepeatSeedAgree", agree)
    mac("nRepeatEdgeIdentical", same_e)
    mac("nRepeatEdgeDiffer", diff_e)
    # seed-DEPENDENT repos: Phase 1 kept per-seed raw sizes, not edge sets; same seed -> same size?
    nd_runs = nd_equal = 0
    nd_repos = set()
    for (n, sd), rec in sw_seed.items():
        pj = P1 / "static" / n / "pycg.json"
        if not pj.exists():
            continue
        p1j = json.loads(pj.read_text())
        if p1j["run"].get("deterministic_across_seeds") is not False:
            continue
        per = {x["seed"]: x for x in p1j["run"]["per_seed"]}
        if sd in per and per[sd]["status"] == "ok" and rec["status"] == "ok":
            nd_repos.add(n)
            nd_runs += 1
            nd_equal += (per[sd]["nodes"], per[sd]["edges"]) == ((rec.get("cost") or {}).get("nodes"), (rec.get("cost") or {}).get("edges"))
    mac("nRepeatNondetRepos", len(nd_repos))
    mac("nRepeatNondetRuns", nd_runs)
    mac("nRepeatNondetEqual", nd_equal)

if R.exists():
    big = {n: r for n, r in reps.items() if r["observed_edges"] >= 20}      # small-n sensitivity
    mac("nBigRepos", len(big))
    mac("nSmallRepos", len(reps) - len(big))
    for tool, nm in (("pycg", "Pycg"), ("pyright", "Pyright"), ("union", "Union")):
        mac(f"bigMed{nm}", f2(st.median(r["edge_recall"][tool] for r in big.values())))
    mac("bigPyrightWins", sum(r["edge_recall"]["pyright"] > r["edge_recall"]["pycg"] for r in big.values()))
    bd = [(dens[n], r["edge_recall"]["union"]) for n, r in big.items() if dens.get(n) is not None]
    mac("bigDensitySpearman", f"{_spearman([a for a, _ in bd], [b for _, b in bd]):.2f}")
    mac("bigDensitySpearmanP", _fmt_p(_perm_p([a for a, _ in bd], [b for _, b in bd])))
    # Kruskal-Wallis on union recall across LOW/MED/HIGH (chi-square, df = 2: p = exp(-H/2)), ties averaged
    vals = sorted((r["edge_recall"]["union"], r["stratum"]) for r in reps.values())
    rank_of, i = {}, 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1][0] == vals[i][0]:
            j += 1
        for k in range(i, j + 1):
            rank_of[k] = (i + j) / 2 + 1
        i = j + 1
    N = len(vals)
    by_s = defaultdict(list)
    for k, (_, sname) in enumerate(vals):
        by_s[sname].append(rank_of[k])
    Hs = 12 / (N * (N + 1)) * sum(len(v) * (st.mean(v) - (N + 1) / 2) ** 2 for v in by_s.values())
    tie = 1 - sum(c ** 3 - c for c in Counter(v for v, _ in vals).values()) / (N ** 3 - N)
    Hs = Hs / tie if tie else Hs
    mac("kwStrataH", f"{Hs:.2f}")
    mac("kwStrataP", _fmt_p(math.exp(-Hs / 2)))

if LA.exists():
    rows_l = [json.loads(l) for l in LA.open()]
    llm_names = ("gpt-oss-20b", "gpt-oss-120b", "qwen3.8-27b")
    rules = {"comb": lambda r: r["p"] >= 0.5, "union": lambda r: r["pycg"] or r["pyright"],
             "pyright": lambda r: r["pyright"], "pycg": lambda r: r["pycg"],
             "majority": lambda r: sum(r["votes"]) >= 2, "anyllm": lambda r: r["pycg"] or r["pyright"] or any(r["votes"])}
    for k, m in enumerate(llm_names):
        rules[m] = (lambda k: lambda r: r["votes"][k])(k)
    def tallies(rs, f):
        tp = sum(1 for r in rs if f(r) and r["label"]); fp = sum(1 for r in rs if f(r) and not r["label"])
        fn = sum(1 for r in rs if r["label"]) - tp
        return tp, fp, fn
    def f1t(t):
        return 2 * t[0] / (2 * t[0] + t[1] + t[2]) if t[0] else 0.0
    best = max(llm_names, key=lambda m: f1t(tallies(rows_l, rules[m])))
    rules["pyr_best"] = lambda r: r["pyright"] or r["votes"][llm_names.index(best)]
    mac("bestLlm", best)
    labels_r = [("pycg", "PyCG"), ("pyright", "Pyright"), ("union", "PyCG $\\cup$ Pyright"),
                ("gpt-oss-20b", "gpt-oss-20b"), ("gpt-oss-120b", "gpt-oss-120b"), ("qwen3.8-27b", "qwen3.8-27b"),
                ("majority", "majority of the three LLMs"), ("pyr_best", f"Pyright $\\cup$ {best}"),
                ("anyllm", "static $\\cup$ any LLM"), ("comb", "learned combiner")]
    by_repo = defaultdict(list)
    for r in rows_l:
        by_repo[r["repo"]].append(r)
    names_r = sorted(by_repo)
    rnd = _random.Random(20261019)          # same draws as _loro_stats, so the CIs agree
    boots = [[names_r[rnd.randrange(len(names_r))] for _ in names_r] for _ in range(2000)]
    per = {k: {n: tallies(by_repo[n], f) for n in names_r} for k, f in rules.items()}
    def pooled_f1(k, ns):
        t = [sum(per[k][n][i] for n in ns) for i in range(3)]
        return f1t(t)
    rows6 = []
    for k, lab in labels_r:
        t = tallies(rows_l, rules[k])
        p_, r_ = (t[0] / (t[0] + t[1]) if t[0] + t[1] else 0.0), (t[0] / (t[0] + t[2]) if t[0] + t[2] else 0.0)
        if k == "comb":
            ci = ""
        else:
            ds = sorted(pooled_f1("comb", b) - pooled_f1(k, b) for b in boots)
            m_ = lambda v: f"{v:.2f}".replace("-0.00", "0.00").replace("-", "$-$")     # text-mode table cell
            ci = f"[{m_(ds[50])}, {m_(ds[1949])}]"
        rows6.append(f"{lab} & {f2(p_)} & {f2(r_)} & {f2(f1t(t))} & {ci} \\\\")
    mac("loroRowsCI", "\n".join(rows6))      # last column: paired repo-bootstrap CI of combiner F1 minus that row


# D1 mapping audit (traceweave/study1/d1_mapping.py -> study1-results/d1_mapping.json)
D1 = ROOT / "study1-results" / "d1_mapping.json"
if D1.exists() and R.exists():
    d1 = json.loads(D1.read_text())
    ok1 = [n for n, r in d1["repos"].items() if "observed" in r]
    mac("nMapRepos", len(ok1))
    for k, nm in (("recall_strict_seed0", "Strict"), ("recall_lenient", "Lenient"), ("recall_pyright", "Pyright"),
                  ("recall_union_lenient", "UnionLenient")):
        mac(f"mapPool{nm}", f2(d1["pooled"][k]))
        mac(f"mapMed{nm}", f2(d1["median"][k]))
    obs1 = sum(reps[n]["observed_edges"] for n in ok1)
    mac("mapPoolUnionStrict", f2(sum(reps[n]["edge_recall"]["union"] * reps[n]["observed_edges"] for n in ok1) / obs1))
    mac("mapMedUnionStrict", f2(st.median(reps[n]["edge_recall"]["union"] for n in ok1)))
    mac("mapPyrWinsStrict", d1["pyright_wins_strict"])
    mac("mapPyrWinsLenient", d1["pyright_wins_lenient"])
    c1 = d1["ctor"]
    mac("mapCtorStrict", f2(c1["ctor_strict"] / c1["ctor_n"]))
    mac("mapCtorLenient", f2(c1["ctor_lenient"] / c1["ctor_n"]))
    mac("mapCtorPyright", f2(c1["ctor_pyright"] / c1["ctor_n"]))
    a1 = d1["audit"]
    mac("nMapAudited", f"{a1['pyright_hits_strict_pycg_misses']:,}".replace(",", "{,}"))
    mac("nMapLoss", a1["mapping_loss"])
    mac("pctMapLoss", pct(a1["mapping_loss"], a1["pyright_hits_strict_pycg_misses"]))
    mac("pctMapLossSample", f"{100 * a1['random50_loss_share']:.0f}\\%")
    # the union moves by under 0.01: give the delta itself so 0.533 -> 0.535 is not printed as 0.53 -> 0.54
    mac("mapUnionPoolDelta", f"{d1['pooled']['recall_union_lenient'] - sum(reps[n]['edge_recall']['union'] * reps[n]['observed_edges'] for n in ok1) / obs1:.3f}")
