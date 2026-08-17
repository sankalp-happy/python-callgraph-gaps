#!/usr/bin/env python3
"""Turn `candidates/03_queue.csv` into the exact sheets each operator is owed.

Discovery produced 558 queued repos. ins1 §1, ins2 §1 and ins3 §1 all say the
same thing -- "A longer list (400-600 projects) is being generated and will be
added to your sheet later. Work the 14 first." This is that list, split three
ways, with every script-owned column pre-filled and every human-owned column
left empty.

Column sets are copied from the instruction documents, not invented here:

    ins1 §6   triage sheet, one row per repo. Includes `result_line_seen`,
              which ins1 calls "new in v1.1 and the most useful column on the
              sheet" -- and which discover_candidates.py's QC-sample writer
              currently omits (see --qc-fix).
    ins2 §4   prework tab is one row per *candidate workload*, so what ins2 needs
              from us is a target list, not a pre-filled tab.
    ins3 §6   main tab, with licence/stars/last_commit_date/port_exists filled by
              script exactly as §6 says they are.
    ins3 §4   PART 1-R: the short licence-review list. §4 predicts "about 1
              project in 10"; the real rate is printed below because it is higher.

Queue order is preserved everywhere. That order is load-bearing: amendment 3
interleaves the strata so that ANY prefix carries all three, which is what makes
a partial run interpretable.

Usage:
    python3 make_operator_sheets.py --queue ../../candidates/03_queue.csv \
                                    --out ../../handoff
    python3 make_operator_sheets.py --qc-fix   # rewrite 03_qc_sample.csv's header
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

# Per sheet, not one constant: docs/sop_v1.2_changelog.md amends ins1 ONLY (it
# adds OOM/TIMEOUT/KILLED and collect_partial). Stamping ins2 and ins3 v1.2 as
# well would claim changes those documents never had, and validate_sheet.py gates
# the new vocabulary on the row's own version -- so a wrong stamp there would
# accept values the operator was never told about.
SHEET_VERSION = "v1.1"
SHEET_VERSION_INS1 = "v1.2"

# ins1_v1.1_spotcheck.md §6, in order.
INS1_COLS = ["row_id", "repo_url", "sha", "status", "error_class", "fix_applied",
             "n_failing", "minutes_spent", "log_file", "result_line_seen",
             "notes", "your_name", "date", "sheet_version"]

# ins3_v1.1.md §6 main tab, in order.
INS3_COLS = ["row_id", "repo_url", "licence", "licence_reviewed_by",
             "last_commit_date", "stars", "port_exists", "part3_status",
             "minutes_spent", "recorded_by", "date", "sheet_version", "notes"]

# ins3_v1.1.md §4. Only the columns a reviewer touches, plus what they need to
# find the file. Deliberately narrow: §4 says "Do not go looking for this work."
INS3_R_COLS = ["row_id", "repo_url", "licence_from_script", "licence_spdx_seen",
               "licence", "licence_reviewed_by", "notes", "date", "sheet_version"]

# ins2 needs targets, not a filled tab (§4 is one row per candidate workload).
INS2_COLS = ["queue_position", "row_id", "repo", "repo_url", "sha", "stratum",
             "stars", "build_file", "has_tests_dir", "has_test_files",
             "prework_status", "recorded_by", "date", "sheet_version"]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_queued(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    queued = [r for r in rows
              if (r.get("excluded_reason") or "none") == "none"
              and str(r.get("queue_position") or "").strip()]
    queued.sort(key=lambda r: int(r["queue_position"]))
    return queued


def write(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    log(f"  {path}  ({len(rows)} rows)")


def short_name(url: str) -> str:
    return url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent
    ap.add_argument("--queue", type=Path,
                    default=here.parent.parent / "candidates" / "03_queue.csv")
    ap.add_argument("--out", type=Path, default=here.parent.parent / "handoff")
    ap.add_argument("--qc-fix", action="store_true",
                    help="add the missing result_line_seen column to "
                         "03_qc_sample.csv (ins1 §6 requires it)")
    args = ap.parse_args()

    if not args.queue.exists():
        log(f"FATAL: no queue at {args.queue}")
        return 2
    queued = load_queued(args.queue)
    log(f"[sheets] {len(queued)} queued repos, positions "
        f"{queued[0]['queue_position']}..{queued[-1]['queue_position']}")
    log(f"[sheets] strata: {dict(sorted(Counter(r['stratum'] for r in queued).items()))}")

    # --- ins1: the triage sheet -------------------------------------------------
    ins1 = [{"row_id": r["row_id"], "repo_url": r["repo_url"], "sha": r["sha"],
             "status": "", "error_class": "", "fix_applied": "", "n_failing": "",
             "minutes_spent": "", "log_file": "", "result_line_seen": "",
             "notes": "-", "your_name": "", "date": "",
             "sheet_version": SHEET_VERSION_INS1}
            for r in queued]
    write(args.out / "ins1_triage_558.csv", INS1_COLS, ins1)

    # --- ins2: the target list --------------------------------------------------
    ins2 = [{"queue_position": r["queue_position"], "row_id": r["row_id"],
             "repo": short_name(r["repo_url"]), "repo_url": r["repo_url"],
             "sha": r["sha"], "stratum": r["stratum"], "stars": r["stars"],
             "build_file": r["build_file"], "has_tests_dir": r["has_tests_dir"],
             "has_test_files": r["has_test_files"], "prework_status": "not_started",
             "recorded_by": "", "date": "", "sheet_version": SHEET_VERSION}
            for r in queued]
    write(args.out / "ins2_targets_558.csv", INS2_COLS, ins2)

    # --- ins3: main tab ---------------------------------------------------------
    ins3 = [{"row_id": r["row_id"], "repo_url": r["repo_url"],
             "licence": r["licence"], "licence_reviewed_by": "-",
             "last_commit_date": r["last_commit_date"], "stars": r["stars"],
             "port_exists": "NA_V11", "part3_status": "not_started",
             "minutes_spent": "", "recorded_by": "", "date": "",
             "sheet_version": SHEET_VERSION, "notes": "-"}
            for r in queued]
    write(args.out / "ins3_main_558.csv", INS3_COLS, ins3)

    # --- ins3 PART 1-R: only the rows a human must read -------------------------
    review = [r for r in queued if r["redistribution_class"] == "REVIEW_NEEDED"]
    ins3r = [{"row_id": r["row_id"], "repo_url": r["repo_url"],
              "licence_from_script": r["licence"],
              "licence_spdx_seen": r.get("licence_spdx", ""),
              "licence": "", "licence_reviewed_by": "", "notes": "-",
              "date": "", "sheet_version": SHEET_VERSION}
             for r in review]
    write(args.out / "ins3_part1R_licence_review_91.csv", INS3_R_COLS, ins3r)

    pct = len(review) / len(queued) * 100
    log("")
    log(f"[sheets] PART 1-R is {len(review)} of {len(queued)} rows ({pct:.1f}%).")
    log(f"         ins3 §4 predicts 'about 1 project in 10'. The real rate is "
        f"{pct:.1f}%, so budget {len(review) * 0.5:.0f} minutes, not "
        f"{len(queued) * 0.1 * 0.5:.0f}.")
    lic = Counter(r["licence"] for r in review)
    for k, n in lic.most_common():
        log(f"         {k}: {n}")
    log("")
    log("[sheets] licence spread across all 558 (advisory only — nothing gates on "
        "it yet, see github_meta.py REDISTRIBUTION):")
    for k, n in Counter(r["redistribution_class"] for r in queued).most_common():
        log(f"         {k}: {n}")

    if args.qc_fix:
        qc = args.queue.parent / "03_qc_sample.csv"
        with qc.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        if "result_line_seen" in (rows[0].keys() if rows else []):
            log(f"[qc-fix] {qc.name} already has result_line_seen; nothing to do")
        else:
            for r in rows:
                r["result_line_seen"] = ""
            write(qc, INS1_COLS, rows)
            log(f"[qc-fix] added result_line_seen to {qc.name} ({len(rows)} rows). "
                f"ins1 §6: 'the most useful column on the sheet'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
