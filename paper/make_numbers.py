#!/usr/bin/env python3
"""Every number the paper quotes, computed from the result files and written as LaTeX macros.

    python3 paper/make_numbers.py > paper/numbers.tex

RQ1/RQ2 read phase1-results/ (the amd64 Phase 1 run). RQ3/RQ4 read the harness bench/learn
outputs once they exist; until then their macros print as \\pending.
"""
import json
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
        mac("nCombItems", f"{c['items']:,}".replace(",", "{,}"))
        mac("nCombRepos", len(c["repos"]))
        lo = c.get("leave_one_repo_out")
        if lo:
            mac("loroComb", f"{f2(lo['precision'])} & {f2(lo['recall'])} & {f2(lo['f1'])}")
    # per-repo table, one row per traced repo, sorted by stratum then union edge recall
    order = {"LOW": 0, "MED": 1, "HIGH": 2}
    rows = sorted(reps.items(), key=lambda kv: (order.get(kv[1]["stratum"], 3), kv[1]["edge_recall"]["union"]))
    lines = []
    for n, r in rows:
        e, s = r["edge_recall"], r["scores"]
        short = {"bedrock-agentcore-sdk-python": "bedrock-agentcore-sdk", "confluence-markdown-exporter": "confluence-md-exporter",
                 "mcp-sequential-thinking": "mcp-seq-thinking"}.get(n, n)
        lines.append(f"\\texttt{{{short}}} & {r['stratum'][0]} & {r['observed_edges']} & "
                     f"{f2(e['pycg'])} & {f2(e['pyright'])} & {f2(e['union'])} & {f2(s['PyCG ∪ Pyright']['recall'])} \\\\")
    mac("rqThreeRows", "\n".join(lines))   # a macro, not a file: \input cannot start a tabular row
