#!/usr/bin/env python3
"""PyCG seed sweep: does the hash seed change how many REAL calls PyCG finds?

For every traced repo whose Phase 1 PyCG was seed-dependent, run PyCG once per PYTHONHASHSEED on
exactly Phase 1's file list (extract.py's inventory and exclusions, a fresh clone at the pinned
sha), then score each seed's in-universe edges against the calls the test suite made
(bundles/<repo>/truth.json, the same pairs as collect.py).

    python3 sweep.py run                                   # resumable, one JSON per (repo, seed)
    python3 sweep.py run --only chevron --seeds 0 --timeout 7200 --untraced   # the 16-node timeout
    python3 sweep.py report > seeds.json
"""
import argparse
import csv
import json
import os
import statistics as st
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "static"))
import pycg_baseline                                     # noqa: E402
from extract import NON_LIBRARY_TOP                      # noqa: E402
from nodes import DEFAULT_EXCLUDE_DIRS, inventory_repo   # noqa: E402

H = Path(os.environ.get("TW_HARNESS", Path.home() / "traceweave-harness"))
DATA = Path(os.environ.get("TW_DATA", Path.home() / "traceweave-data"))
OUT = DATA / "study1" / "seeds"


def targets(only):
    if only:
        return only
    rows = csv.DictReader((l for l in (HERE / "repos.tsv").open() if not l.startswith("#")), delimiter="\t")
    return [r["repo"] for r in rows if r["pycg_deterministic"] == "false"]


def clone(name: str, summary: dict) -> Path:
    d = OUT / "clones" / name
    sha = summary["clone"]["sha_resolved"]
    if not (d / ".git").exists():
        d.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", summary["repo_url"], str(d)], check=True)
    subprocess.run(["git", "-C", str(d), "checkout", "-q", "--force", sha], check=True)
    return d


def cmd_run(args) -> int:
    for name in targets(args.only):
        if not args.untraced and not (H / "bundles" / name / "truth.json").exists():
            print(f"{name}: not traced yet, skipped")
            continue
        summary = json.loads((DATA / "static" / name / "summary.json").read_text())
        todo = [s for s in args.seeds.split(",") if not (OUT / name / f"seed{s}.json").exists()]
        if not todo:
            continue
        repo = clone(name, summary)
        inv = inventory_repo(repo, [repo / p for p in summary["packages"]], repo / summary["src_root"],
                             set(), set(DEFAULT_EXCLUDE_DIRS) | NON_LIBRARY_TOP)
        rel_files = [m.relative_path for m in inv.modules]
        for seed in todo:
            run = pycg_baseline.run_pycg(repo, rel_files, summary["src_root"], seed,
                                         pycg_baseline.DEFAULT_IMAGE, "8g", args.timeout)
            rec = {k: v for k, v in run.items() if k in ("status", "seed", "wall_seconds", "detail", "cost")}
            if run["status"] == "ok":
                graph, _ = pycg_baseline.union_graphs([run])
                edges, _ = pycg_baseline.normalize(graph, inv)
                rec["edges"] = sorted(f"{a}->{b}" for a, b in edges.in_universe)
            (OUT / name).mkdir(parents=True, exist_ok=True)
            (OUT / name / f"seed{seed}.json").write_text(json.dumps(rec) + "\n")
            print(f"{name} seed {seed}: {rec['status']} {rec.get('wall_seconds')} s "
                  f"{len(rec.get('edges', []))} edges", flush=True)
    return 0


def cmd_iterprobe(args) -> int:
    """PyCG's fixpoint, capped and logged per pass (static/pycg_iterprobe.py), on Phase 1's files."""
    for name in args.only:
        summary = json.loads((DATA / "static" / name / "summary.json").read_text())
        repo = clone(name, summary)
        inv = inventory_repo(repo, [repo / p for p in summary["packages"]], repo / summary["src_root"],
                             set(), set(DEFAULT_EXCLUDE_DIRS) | NON_LIBRARY_TOP)
        listing = "\n".join(f"/repo/{m.relative_path}" for m in inv.modules)
        root = "/repo" if summary["src_root"] == "." else f"/repo/{summary['src_root']}"
        out = OUT / "iterprobe" / f"{name}.seed{args.seed}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["docker", "run", "--rm", "-i", "--memory=8g", "-e", f"PYTHONHASHSEED={args.seed}",
               "--entrypoint", "python3", "-v", f"{repo}:/repo:ro",
               "-v", f"{HERE.parent / 'static'}:/s:ro", pycg_baseline.DEFAULT_IMAGE,
               "/s/pycg_iterprobe.py", "--root", root, "--max-iter", str(args.max_iter), "--wall", str(args.wall)]
        with out.open("w") as fh:
            proc = subprocess.run(cmd, input=listing, stdout=fh, stderr=subprocess.PIPE, text=True)
        rc = proc.returncode
        out.with_suffix(".err").write_text(proc.stderr[-4000:])
        rows = [json.loads(l) for l in out.read_text().splitlines()]
        last = rows[-1] if rows else {}
        cyc = [r for r in rows if r["seen_at"] is not None]
        print(f"{name} seed {args.seed}: rc={rc} passes={len(rows)} converged={last.get('converged')} "
              f"defs={last.get('defs')} names={last.get('names')} first repeat={cyc[0] if cyc else None}")
    return 0


def cmd_report(args) -> int:
    sys.path.insert(0, str(H))
    os.chdir(H)
    from graph import ENTRY, Bundle
    out = {}
    for d in sorted(p for p in OUT.iterdir() if p.is_dir() and p.name != "clones"):
        name = d.name
        seeds = {json.loads(f.read_text())["seed"]: json.loads(f.read_text()) for f in d.glob("seed*.json")}
        row = {"seeds": {s: {"status": r["status"], "seconds": r.get("wall_seconds"),
                             "edges": len(r.get("edges", []))} for s, r in seeds.items()}}
        sets = {s: {tuple(e.split("->")) for e in r["edges"]} for s, r in seeds.items() if r["status"] == "ok"}
        traced = (H / "bundles" / name / "truth.json").exists()
        obs, pyright = set(), set()
        if traced:                                       # recall per seed needs the traced labels
            b = Bundle(name)
            truth = json.loads((b.dir / "truth.json").read_text())
            obs = {(e[0], e[1]) for e in truth["edges"]
                   if e[0] != ENTRY and e[0] != e[1] and b.nodes[e[1]]["kind"] in ("function", "method")}
            pyright = b.static_by_tool.get("pyright", set())
            for s, es in sets.items():
                row["seeds"][s]["recall_pycg"] = round(len(obs & es) / len(obs), 4) if obs else None
                row["seeds"][s]["recall_union"] = round(len(obs & (es | pyright)) / len(obs), 4) if obs else None
        if len(sets) >= 2:                               # set-level, not count-level: every swept repo
            ks = sorted(sets)
            jac = [len(sets[a] & sets[b]) / len(sets[a] | sets[b]) for i, a in enumerate(ks) for b in ks[i + 1:]
                   if sets[a] | sets[b]]
            base = sets[ks[0]]
            varying = set().union(*sets.values()) - set.intersection(*sets.values())
            row |= {"jaccard_min": round(min(jac), 4) if jac else 1.0, "jaccard_median": round(st.median(jac), 4) if jac else 1.0,
                    "distinct_graphs": len({frozenset(e) for e in sets.values()}),
                    "varying_edges": len(varying), "varying_observed": len(varying & obs) if traced else None,
                    "always_edges": len(set.intersection(*sets.values())),
                    "vs_seed0": {s: {"added": len(es - base), "removed": len(base - es)} for s, es in sets.items()},
                    "examples": {"added": sorted("->".join(e) for e in (set().union(*sets.values()) - base))[:3],
                                 "removed": sorted("->".join(e) for e in (base - set.intersection(*sets.values())))[:3],
                                 "varying_observed": sorted("->".join(e) for e in varying & obs)[:3]}}
        rp = [v["recall_pycg"] for v in row["seeds"].values() if v.get("recall_pycg") is not None]
        ru = [v["recall_union"] for v in row["seeds"].values() if v.get("recall_union") is not None]
        if rp:
            row |= {"observed": len(obs), "recall_pycg": [min(rp), st.median(rp), max(rp)],
                    "recall_union": [min(ru), st.median(ru), max(ru)],
                    "recall_pycg_union_of_seeds": round(len(obs & set().union(*sets.values())) / len(obs), 4)}
        out[name] = row
    json.dump(out, sys.stdout, indent=1)
    print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--only", nargs="+")
    p.add_argument("--seeds", default=",".join(str(i) for i in range(10)))
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--untraced", action="store_true", help="run even without a traced bundle (chevron)")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("iterprobe", help="PyCG's fixpoint capped and logged per pass (chevron)")
    p.add_argument("--only", nargs="+", required=True)
    p.add_argument("--seed", default="0")
    p.add_argument("--max-iter", type=int, default=100)
    p.add_argument("--wall", type=int, default=1500)
    p.set_defaults(fn=cmd_iterprobe)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
