#!/usr/bin/env python3
"""Print the pinned base-image ref for a Python version on the current platform.

Single source of truth for platform selection, so no script and no doc ever
hardcodes a digest. `config/base_images.json` carries both linux/amd64 and
linux/arm64; this resolves whichever matches the running Docker daemon.

Usage:
    python3 resolve_image.py 3.12
    python3 resolve_image.py 3.12 --platform linux/arm64     # force (will emulate)
    python3 resolve_image.py 3.12 --print-platform           # just the platform

Exit codes: 0 ok, 2 bad args / unknown version, 3 cannot detect platform.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ARCH_MAP = {
    "amd64": "linux/amd64", "x86_64": "linux/amd64",
    "arm64": "linux/arm64", "aarch64": "linux/arm64",
}


def detect_platform() -> str | None:
    """Ask the Docker daemon, then fall back to the host machine type."""
    try:
        out = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Arch}}"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        if out in ARCH_MAP:
            return ARCH_MAP[out]
    except (OSError, subprocess.SubprocessError):
        pass
    # platform.machine() rather than os.uname(), which does not exist on Windows --
    # there the fallback would raise AttributeError instead of returning a clean
    # "cannot detect platform" error. Windows reports "AMD64"/"ARM64", hence lower().
    return ARCH_MAP.get(platform.machine().lower())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pyver", help="e.g. 3.12")
    ap.add_argument("--platform", help="force linux/amd64 or linux/arm64")
    ap.add_argument("--config", type=Path,
                    default=Path(__file__).resolve().parent.parent / "config" / "base_images.json")
    ap.add_argument("--print-platform", action="store_true")
    args = ap.parse_args()

    try:
        cfg = json.loads(args.config.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read {args.config}: {e}", file=sys.stderr)
        return 2

    want = args.platform or os.environ.get("TW_PLATFORM") or cfg.get("active_platform", "auto")
    if want == "auto":
        detected = detect_platform()
        if not detected:
            print("cannot detect platform; pass --platform", file=sys.stderr)
            return 3
        want = detected

    if args.print_platform:
        print(want)
        return 0

    img = cfg.get("images", {}).get(args.pyver)
    if not img:
        print(f"no pinned image for python {args.pyver}", file=sys.stderr)
        return 2
    digest = img.get("digests", {}).get(want)
    if not digest:
        print(f"no {want} digest for python {args.pyver}", file=sys.stderr)
        return 2

    print(f"python@{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
