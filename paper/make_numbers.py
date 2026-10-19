#!/usr/bin/env python3
"""Every number the paper quotes, computed from the result files and written as LaTeX macros.

    python3 paper/make_numbers.py > paper/numbers.tex

RQ1/RQ2 read phase1-results/ (the amd64 Phase 1 run). RQ3/RQ4 read the harness bench/learn
outputs once they exist; until then their macros print as \\pending.
"""
import json
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
    mac("pctUnnamed", pct(d["unnamed"], d["unnamed"] + d["real_items"]))
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
            cols = [f"{f2(st_['recall'])} / {f2(st_['precision'])}"] + \
                   [f"{f2(K[m][k]['model']['recall'])} / {f2(K[m][k]['model']['precision'])}" for m in order_m]
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
        mac("covSpearman", f"{d['coverage_vs_recall_spearman']:.2f}")
        mac("testsSpearman", f"{d['tests_vs_recall_spearman']:.2f}")
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

