#!/usr/bin/env python3
"""Check an operator sheet against its instruction document's allowed values.

ins1 §6 is blunt about why this exists: *"Spelling must be exact. `Green`,
`green`, and `GREEN ` (trailing space) are all wrong. A script reads this file and
does not forgive typos."* This is that script. It is better that it runs before a
sheet comes back than after.

Validates ins1 (§6 triage), ins2 (§4 prework) and ins3 (§6 main tab + §4 Part
1-R) sheets. Reports every violation with its row and column; never edits.

The returned 14-row v1.1 spot-check failed 14 of 14 rows against §6 -- casing,
`NA` for `na`, and an empty `minutes_spent` on 12 of them. None of that was
carelessness so much as a spec with no machine check attached to it.

Usage:
    python3 validate_sheet.py ins1 ../../handoff/ins1_triage_558.csv
    python3 validate_sheet.py ins3r ../../handoff/ins3_part1R_licence_review_91.csv
    python3 validate_sheet.py ins1 sheet.csv --filled-only   # ignore blank rows

Exit codes: 0 clean, 1 violations found, 2 bad args / missing input.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INT_RE = re.compile(r"^\d+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
URL_RE = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+$")

# ins1_v1.1_spotcheck.md §6. `error_class` gains OOM/TIMEOUT/KILLED only if the
# amendment in ins1_v1.1_amendment_draft.md is accepted -- --v12 turns them on.
INS1 = {
    "status": ["GREEN", "GREEN_AFTER_FIX", "AMBER", "RED", "UNCLEAR"],
    "error_class": ["NONE", "PYTHON_VERSION", "DEP_RESOLUTION",
                    "MISSING_SYSTEM_LIB", "NETWORK", "CLONE", "TIMEBOX", "OTHER"],
    "fix_applied": ["none", "py3.11", "py3.10", "py3.9", "py3.8",
                    "tried_3.11_3.10_3.9", "tried_3.10_3.8"],
    "sheet_version": ["v1.1"],
}
INS1_V12_ERROR_CLASS = ["OOM", "TIMEOUT", "KILLED"]

# ins2_v1.1_prework.md §4 / §4.1
INS2 = {
    "likely_kind": ["test_suite", "demo_script", "cli_usage"],
    "file_exists_in_repo": ["yes", "no", "na"],
    "confidence": ["high", "medium", "low"],
    "sheet_version": ["v1.1"],
}

# ins3_v1.1.md §6
INS3 = {
    "part3_status": ["not_started", "DONE", "TIMEBOX", "NONE_FOUND"],
    "port_exists": ["NA_V11"],
    "sheet_version": ["v1.1"],
}

# ins3_v1.1.md §4 table. "Do not create new values."
INS3_LICENCE = ["MIT", "Apache", "BSD", "GPL", "LGPL", "MPL", "PUBLIC_DOMAIN",
                "NONE_FOUND", "OTHER"]


def log(msg: str) -> None:
    print(msg, file=sys.stdout, flush=True)


class Report:
    def __init__(self) -> None:
        self.bad: list[tuple[int, str, str, str]] = []

    def add(self, row: int, col: str, val: str, why: str) -> None:
        self.bad.append((row, col, val, why))

    def enum(self, row: int, col: str, val: str, allowed: list[str],
             required: bool = True) -> None:
        if val == "" and not required:
            return
        if val in allowed:
            return
        if val.strip() in allowed:
            # The exact failure ins1 §6 calls out by name.
            self.add(row, col, repr(val),
                     f"whitespace: {val.strip()!r} is valid, {val!r} is not")
        elif val.upper() in [a.upper() for a in allowed]:
            right = next(a for a in allowed if a.upper() == val.upper())
            self.add(row, col, repr(val), f"casing: should be {right!r}")
        else:
            self.add(row, col, repr(val),
                     f"not an allowed value ({'/'.join(allowed[:6])}…)")


def check_ins1(rows: list[dict], rep: Report, args) -> None:
    allowed = dict(INS1)
    if args.v12:
        allowed["error_class"] = INS1["error_class"] + INS1_V12_ERROR_CLASS
    for i, r in enumerate(rows, 2):  # row 1 is the header
        status = (r.get("status") or "")
        if args.filled_only and not status.strip():
            continue
        for col, vals in allowed.items():
            rep.enum(i, col, r.get(col, ""), vals)
        ec, fx = r.get("error_class", ""), r.get("fix_applied", "")

        # §6 cross-field rules.
        if status == "GREEN":
            if ec != "NONE":
                rep.add(i, "error_class", ec, "status=GREEN requires error_class=NONE")
            if fx != "none":
                rep.add(i, "fix_applied", fx, "status=GREEN requires fix_applied=none")
        if status == "AMBER" and ec != "NONE":
            rep.add(i, "error_class", ec, "status=AMBER requires error_class=NONE")
        if status == "RED" and ec == "NONE":
            rep.add(i, "error_class", ec, "status=RED requires error_class != NONE")
        if args.v12 and ec in INS1_V12_ERROR_CLASS:
            if status != "RED":
                rep.add(i, "status", status,
                        f"error_class={ec} requires status=RED (amendment §2.3)")
            if r.get("n_failing") != "na":
                rep.add(i, "n_failing", r.get("n_failing", ""),
                        f"error_class={ec} requires n_failing=na (amendment §2.3)")

        # n_failing: a number, or 0, or collect_fail, or na (+ collect_partial in v1.2)
        nf = r.get("n_failing", "")
        ok_nf = ["collect_fail", "na"] + (["collect_partial"] if args.v12 else [])
        if nf and not INT_RE.match(nf) and nf not in ok_nf:
            rep.add(i, "n_failing", repr(nf),
                    f"must be a whole number, or one of {'/'.join(ok_nf)}")

        ms = r.get("minutes_spent", "")
        if not ms.strip():
            rep.add(i, "minutes_spent", "''", "required: a whole number of minutes")
        elif not INT_RE.match(ms):
            rep.add(i, "minutes_spent", repr(ms), "must be a whole number")

        # notes required only for OTHER / UNCLEAR / MISSING_SYSTEM_LIB
        if (ec in ("OTHER", "MISSING_SYSTEM_LIB") or status == "UNCLEAR"):
            if (r.get("notes") or "-").strip() in ("", "-"):
                rep.add(i, "notes", "'-'",
                        f"notes are required when status/error_class is "
                        f"{status or ec}")
        check_common(i, r, rep)


def check_ins2(rows: list[dict], rep: Report, args) -> None:
    for i, r in enumerate(rows, 2):
        if args.filled_only and not (r.get("command") or "").strip():
            continue
        for col, vals in INS2.items():
            rep.enum(i, col, r.get(col, ""), vals,
                     required=col == "sheet_version")
        cid = r.get("candidate_id", "")
        if cid and not re.match(r"^[A-Za-z0-9_.\-]+_c\d{2}$", cid):
            rep.add(i, "candidate_id", repr(cid), "expected <name>_cNN, e.g. click_c01")
        check_common(i, r, rep)


def check_ins3(rows: list[dict], rep: Report, args) -> None:
    for i, r in enumerate(rows, 2):
        if args.filled_only and (r.get("part3_status") or "") in ("", "not_started"):
            continue
        for col, vals in INS3.items():
            rep.enum(i, col, r.get(col, ""), vals)
        ms = r.get("minutes_spent", "")
        if ms and not INT_RE.match(ms):
            rep.add(i, "minutes_spent", repr(ms), "must be a whole number")
        check_common(i, r, rep)


def check_ins3r(rows: list[dict], rep: Report, args) -> None:
    for i, r in enumerate(rows, 2):
        lic = r.get("licence", "")
        if args.filled_only and not lic.strip():
            continue
        rep.enum(i, "licence", lic, INS3_LICENCE)
        if lic == "OTHER" and (r.get("notes") or "-").strip() in ("", "-"):
            rep.add(i, "notes", "'-'",
                    "ins3 §4: licence=OTHER requires the first line pasted into notes")
        if lic and not (r.get("licence_reviewed_by") or "").strip():
            rep.add(i, "licence_reviewed_by", "''",
                    "ins3 §4: set this to your name on a reviewed row")
        check_common(i, r, rep)


def check_common(i: int, r: dict, rep: Report) -> None:
    """Columns the script fills and nobody should be editing."""
    url = r.get("repo_url", "")
    if url and not URL_RE.match(url):
        rep.add(i, "repo_url", repr(url[:70]),
                "not a plain https://github.com/<owner>/<name> URL "
                "(a search URL or a trailing path means the wrong target was worked)")
    sha = r.get("sha", "")
    if sha and not SHA_RE.match(sha):
        rep.add(i, "sha", repr(sha[:50]), "expected a 40-char lowercase hex sha")
    d = r.get("date", "")
    if d.strip() and not DATE_RE.match(d):
        rep.add(i, "date", repr(d), "expected YYYY-MM-DD")


CHECKS = {"ins1": check_ins1, "ins2": check_ins2,
          "ins3": check_ins3, "ins3r": check_ins3r}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=sorted(CHECKS))
    ap.add_argument("sheet", type=Path)
    ap.add_argument("--filled-only", action="store_true",
                    help="skip rows the operator has not started")
    ap.add_argument("--v12", action="store_true",
                    help="allow the OOM/TIMEOUT/KILLED and collect_partial values "
                         "proposed in ins1_v1.1_amendment_draft.md")
    args = ap.parse_args()

    if not args.sheet.exists():
        log(f"FATAL: no sheet at {args.sheet}")
        return 2
    with args.sheet.open(newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        header = reader.fieldnames or []

    rep = Report()
    if args.kind == "ins1" and "result_line_seen" not in header:
        rep.add(1, "result_line_seen", "<missing>",
                "ins1 §6 requires this column ('the most useful column on the "
                "sheet'); run make_operator_sheets.py --qc-fix")
    CHECKS[args.kind](rows, rep, args)

    log(f"[validate] {args.sheet.name}: {len(rows)} rows, {len(header)} columns, "
        f"mode={args.kind}{' +v1.2' if args.v12 else ''}")
    if not rep.bad:
        log("[validate] clean — every value is in its allowed set")
        return 0

    bad_rows = len({r for r, _, _, _ in rep.bad})
    log(f"[validate] {len(rep.bad)} violations across {bad_rows} of {len(rows)} rows")
    log("")
    log(f"{'row':>5}  {'column':<22}{'value':<24}why")
    for row, col, val, why in rep.bad[: args.limit if hasattr(args, "limit") else 200]:
        log(f"{row:>5}  {col:<22}{val[:23]:<24}{why}")
    if len(rep.bad) > 200:
        log(f"        … {len(rep.bad) - 200} more (not truncated silently: "
            f"{len(rep.bad)} total)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
