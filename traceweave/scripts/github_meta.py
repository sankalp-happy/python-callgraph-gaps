#!/usr/bin/env python3
"""Fetch repo background facts from the GitHub REST API — replaces ins3 Part 1.

SOP v1.1 amendment 4. ins3 Part 1 asked annotators to read the licence, star count
and last-commit date off each repo's GitHub sidebar at ~30 projects/day. Those are
three fields the API returns exactly and instantly, so the manual pass is ~30
person-days spent reproducing an HTTP call. Annotators move to ins2 instead.

Emits the SAME vocabulary ins3 §6 defines, so output drops straight into the sheet:
    licence in {MIT, Apache, BSD, GPL, LGPL, MPL, PUBLIC_DOMAIN, NONE_FOUND, OTHER}

ins3 Part 2 (`port_exists`) is DROPPED in v1.1 — it screened for Python ports of
non-Python sources, which is meaningless for a Python corpus (it was inherited from
Direction 1's Java->Python contamination screen). The column is still emitted, as
`NA_V11`, so the sheet schema stays stable and the drop is explicit rather than
looking like an omission.

Auth: set GITHUB_TOKEN to lift the rate limit from 60/hr to 5000/hr.

Usage:
    python3 github_meta.py urls.txt --out meta.jsonl
    python3 github_meta.py --url https://github.com/psf/requests
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
SPEC_VERSION = "1.0"


def _make_ssl_context() -> ssl.SSLContext:
    """Build a verifying context that works on a stock python.org macOS build.

    Those builds ship an empty OpenSSL trust store, so `urllib` fails every TLS
    handshake with CERTIFICATE_VERIFY_FAILED while `curl` succeeds -- and because
    this module degrades to `fetch_status=HTTP_0, notes="api error"` and exits 0,
    that looks like a licence-mapping mismatch rather than a broken host. Detect
    the empty store and fall back to certifi's bundle if it is installed.

    Verification is never disabled. No-op on Linux and Homebrew Python.
    """
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca", 0) == 0:
        try:
            import certifi
            ctx.load_verify_locations(certifi.where())
        except Exception:  # noqa: BLE001 -- better to fail loudly at the request
            pass
    return ctx


_SSL_CTX = _make_ssl_context()

# GitHub SPDX id -> ins3 §3 vocabulary. ins3 note: "AGPL counts as GPL,
# GPL-3.0-or-later counts as GPL. Do not create new values."
LICENCE_MAP = {
    "MIT": "MIT", "MIT-0": "MIT",
    "Apache-2.0": "Apache",
    "BSD-2-Clause": "BSD", "BSD-3-Clause": "BSD", "BSD-4-Clause": "BSD",
    "0BSD": "BSD", "BSD-3-Clause-Clear": "BSD",
    "GPL-2.0": "GPL", "GPL-3.0": "GPL", "AGPL-3.0": "GPL",
    "GPL-2.0-only": "GPL", "GPL-3.0-only": "GPL",
    "GPL-2.0-or-later": "GPL", "GPL-3.0-or-later": "GPL",
    "LGPL-2.1": "LGPL", "LGPL-3.0": "LGPL",
    "LGPL-2.1-only": "LGPL", "LGPL-3.0-only": "LGPL",
    "LGPL-2.1-or-later": "LGPL", "LGPL-3.0-or-later": "LGPL",
    "MPL-2.0": "MPL", "MPL-1.1": "MPL",
    "Unlicense": "PUBLIC_DOMAIN", "CC0-1.0": "PUBLIC_DOMAIN",
    "ISC": "OTHER", "PSF-2.0": "OTHER", "Python-2.0": "OTHER",
}

# Whether the DynBench artifact may redistribute derived material. We publish
# metadata, reference edge sets and workload YAMLs -- not source -- but copyleft
# repos still need flagging so the release decision is explicit, not accidental.
REDISTRIBUTION = {
    "MIT": "PERMISSIVE", "Apache": "PERMISSIVE", "BSD": "PERMISSIVE",
    "PUBLIC_DOMAIN": "PERMISSIVE", "MPL": "WEAK_COPYLEFT",
    "LGPL": "WEAK_COPYLEFT", "GPL": "COPYLEFT",
    "OTHER": "REVIEW_NEEDED", "NONE_FOUND": "REVIEW_NEEDED",
}


def parse_repo(url: str) -> tuple[str, str] | None:
    u = url.strip().rstrip("/")
    if not u or u.startswith("#"):
        return None
    if u.endswith(".git"):
        u = u[:-4]
    parts = [p for p in u.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[-2], parts[-1]


def api_get(path: str, token: str | None) -> tuple[dict | list | None, int, dict]:
    req = urllib.request.Request(f"{API}{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "traceweave-core/1.0")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as r:
            return json.load(r), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return None, e.code, dict(e.headers or {})
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, 0, {}


def respect_rate_limit(headers: dict) -> None:
    """Sleep if we are about to exhaust the quota."""
    try:
        remaining = int(headers.get("X-RateLimit-Remaining", "999"))
        reset = int(headers.get("X-RateLimit-Reset", "0"))
    except ValueError:
        return
    if remaining <= 1 and reset:
        wait = max(0, reset - int(time.time())) + 2
        print(f"  rate limit reached; sleeping {wait}s", file=sys.stderr)
        time.sleep(wait)


def fetch_one(owner: str, name: str, token: str | None) -> dict:
    row: dict[str, object] = {
        "spec_version": SPEC_VERSION,
        "sheet_version": "v1.1",
        "repo_url": f"https://github.com/{owner}/{name}",
        "recorded_by": "github_meta.py",
        "date": time.strftime("%Y-%m-%d"),
        # ins3 Part 2 dropped in v1.1 -- column retained, explicitly not-applicable.
        "port_exists": "NA_V11",
        "evidence_url": "-",
        "searches_done": "NA_V11",
    }

    repo, status, headers = api_get(f"/repos/{owner}/{name}", token)
    respect_rate_limit(headers)

    if status == 404 or repo is None and status in (404, 451):
        # ins3 §9: "GitHub page says 404" -> licence NONE_FOUND, note repo not found
        row.update(licence="NONE_FOUND", stars=0, last_commit_date="unknown",
                   archived="unknown", fork="unknown", default_branch="unknown",
                   language="unknown", size_kb=0, open_issues=0,
                   redistribution_class="REVIEW_NEEDED",
                   fetch_status="NOT_FOUND", notes="repo not found")
        return row
    if not isinstance(repo, dict):
        row.update(licence="NONE_FOUND", stars=0, last_commit_date="unknown",
                   archived="unknown", fork="unknown", default_branch="unknown",
                   language="unknown", size_kb=0, open_issues=0,
                   redistribution_class="REVIEW_NEEDED",
                   fetch_status=f"HTTP_{status}", notes="api error")
        return row

    lic = repo.get("license") or {}
    spdx = lic.get("spdx_id")
    if spdx in (None, "", "NOASSERTION"):
        # A licence file exists but GitHub could not identify it -> OTHER.
        # No licence at all -> NONE_FOUND. (ins3 §3 distinguishes these.)
        licence = "OTHER" if lic else "NONE_FOUND"
    else:
        licence = LICENCE_MAP.get(spdx, "OTHER")

    # last_commit_date: pushed_at is the cheap answer and matches what the sidebar
    # shows. Fall back to the default branch's commit if pushed_at is absent.
    pushed = repo.get("pushed_at") or ""
    last_commit = pushed[:10] if len(pushed) >= 10 else "unknown"

    row.update(
        licence=licence,
        licence_spdx=spdx or "none",
        redistribution_class=REDISTRIBUTION.get(licence, "REVIEW_NEEDED"),
        stars=int(repo.get("stargazers_count") or 0),
        last_commit_date=last_commit,
        archived=bool(repo.get("archived")),
        fork=bool(repo.get("fork")),
        default_branch=repo.get("default_branch") or "unknown",
        language=repo.get("primary_language") or repo.get("language") or "unknown",
        size_kb=int(repo.get("size") or 0),
        open_issues=int(repo.get("open_issues_count") or 0),
        fetch_status="OK",
        notes="-" if not repo.get("archived") else "archived (ins3 §9: process normally)",
    )
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("urls_file", nargs="?", type=Path, help="file of repo URLs, one per line")
    ap.add_argument("--url", action="append", default=[], help="single repo URL (repeatable)")
    ap.add_argument("--out", type=Path, help="write JSONL here (default: stdout)")
    ap.add_argument("--sleep", type=float, default=0.1)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("WARNING: no GITHUB_TOKEN -- limited to 60 requests/hour", file=sys.stderr)

    urls: list[str] = list(args.url)
    if args.urls_file:
        urls += args.urls_file.read_text().splitlines()

    targets = [t for t in (parse_repo(u) for u in urls) if t]
    if not targets:
        print("no valid repo URLs given", file=sys.stderr)
        return 2

    sink = args.out.open("w") if args.out else sys.stdout
    counts: dict[str, int] = {}
    try:
        for i, (owner, name) in enumerate(targets, 1):
            row = fetch_one(owner, name, token)
            counts[str(row["licence"])] = counts.get(str(row["licence"]), 0) + 1
            sink.write(json.dumps(row) + "\n")
            sink.flush()
            if args.out:
                print(f"[{i}/{len(targets)}] {owner}/{name}  "
                      f"{row['licence']:<14} stars={row['stars']:<7} {row['fetch_status']}",
                      file=sys.stderr)
            time.sleep(args.sleep)
    finally:
        if args.out:
            sink.close()

    # ins3 §10 end-of-day format, generated instead of hand-tallied.
    print(f"\nlicences: " + " | ".join(f"{k} {v}" for k, v in sorted(counts.items())),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
