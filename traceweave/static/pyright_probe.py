#!/usr/bin/env python3
"""Runs INSIDE the static image. Answers a batch of definition requests.

Sibling of `pycg_graph.py`: the tool runs in the container, the interpretation
happens on the host. Here that split is not just tidiness, it is what makes the
run survive.

### Why the session is in here and not on the host

The first build drove `pyright-langserver` through `docker run -i` from the
host. It worked for the first hundred-odd requests of a real repo and then the
server's stdout hit EOF with container `ExitCode 1`, `OOMKilled: false`, empty
stderr, and nothing in `docker logs`. Measured, in case it comes back:

  * 400 requests at the SAME position: fine. Not a per-request count limit.
  * `--max-old-space-size` 384 vs 2048: died after 241 and 209 requests. Not
    the node heap.
  * 32-deep pipelining vs one-at-a-time: died at 96 and at ~200. Not in-flight
    depth.
  * The individual position that died in a batch answers correctly in
    isolation. Not a poison request.

So the failure sits in docker's attach path, not in pyright and not in the
protocol -- and it is not something this project can fix from the outside. Move
the pipe inside the container and it is a plain local subprocess again, which
also means a death is something we can *handle*: restart the server, reopen the
file, carry on, and record how many times that happened.

### Contract

    /repo    read-only bind mount of the repository
    /work    writable bind mount: requests.json in, definitions.json out

    requests.json  {"root": "/repo",
                    "chunk": 64,
                    "files": [{"relative_path": "src/click/core.py",
                               "positions": [{"id": "...", "line": 0based,
                                              "char": utf16-col}]}]}

    definitions.json  {"status": "ok", "server_restarts": N,
                       "results": {"<id>": [{"path": "...", "line": 0based}]},
                       "files": [...], "reasons": {...}}

A position that never gets an answer is absent from `results` -- absent means
"no answer", `[]` means "Pyright answered, with nothing". The host must treat
those differently: the first is a harness failure, the second is a finding.

Python 3.10-compatible (the image is 3.10 -- MANIFEST §2.1).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lsp import LspClient, LspError, locations_from_result, uri_to_path  # noqa: E402

SERVER = ["pyright-langserver", "--stdio"]
MAX_RESTARTS = 8


def write_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload))
    os.replace(tmp, path)


class Session:
    """A language server that can be replaced without losing the run."""

    def __init__(self, root: Path, ready_timeout: float, request_timeout: float):
        self.root = root
        self.ready_timeout = ready_timeout
        self.request_timeout = request_timeout
        self.client: LspClient | None = None
        self.restarts = 0
        self.reasons: dict[str, int] = {}

    def note(self, reason: str) -> None:
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def start(self) -> LspClient:
        self.client = LspClient(SERVER, self.root, cwd=self.root,
                                timeout=self.ready_timeout)
        self.client.initialize()
        return self.client

    def restart(self) -> LspClient | None:
        if self.restarts >= MAX_RESTARTS:
            return None
        self.restarts += 1
        self.note("server_restart")
        if self.client is not None:
            try:
                self.client.proc.kill()
                self.client.proc.wait(timeout=10)
            except Exception:  # noqa: BLE001 - the process is already gone
                pass
        return self.start()

    def alive(self) -> bool:
        return self.client is not None and self.client.proc.poll() is None

    def open_file(self, rel: str, text: str) -> tuple[str, bool]:
        assert self.client is not None
        uri = self.client.did_open(self.root / rel, text)
        ready = self.client.wait_for_diagnostics(uri, timeout=self.ready_timeout)
        return uri, ready

    def resolve(self, uri: str, positions: list[dict], chunk: int) -> dict[str, list]:
        """Answers for as many positions as the server will give us.

        Chunked so a death costs at most one chunk of work, and so the amount of
        in-flight state stays bounded on a 5000-call-site file.
        """
        assert self.client is not None
        results: dict[str, list] = {}
        i = 0
        while i < len(positions):
            batch = positions[i:i + chunk]
            try:
                ids = {}
                for pos in batch:
                    rid = self.client.definition(uri, pos["line"], pos["char"])
                    ids[rid] = pos["id"]
                deadline = time.monotonic() + self.request_timeout + 0.05 * len(batch)
                answers = self.client.collect(set(ids), deadline)
            except (LspError, BrokenPipeError, OSError):
                answers = {}
                ids = {}
                self.note("chunk_lost_to_server_death")
            for rid, sid in ids.items():
                reply = answers.get(rid)
                if reply is None:
                    self.note("unanswered")
                    continue
                if "error" in reply:
                    self.note("request_error")
                    results[sid] = []
                    continue
                locs = locations_from_result(reply.get("result"))
                results[sid] = [{"path": p, "line": ln} for p, ln, _c in locs]
            if not self.alive():
                if self.restart() is None:
                    self.note("restart_budget_exhausted")
                    break
                # The new server knows nothing about the open document.
                return results | self._reopen_and_continue(uri, positions[i:], chunk)
            i += chunk
        return results

    def _reopen_and_continue(self, uri: str, remaining: list[dict],
                             chunk: int) -> dict[str, list]:
        assert self.client is not None
        path = Path(uri_to_path(uri))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {}
        rel = str(path.relative_to(self.root)) if str(path).startswith(str(self.root)) else path.name
        new_uri, ready = self.open_file(rel, text)
        if not ready:
            self.note("unready_after_restart")
            return {}
        return self.resolve(new_uri, remaining, chunk)


def main() -> int:
    work = Path(os.environ.get("WORK_DIR", "/work"))
    spec = json.loads((work / "requests.json").read_text())
    root = Path(spec.get("root", "/repo"))
    chunk = int(spec.get("chunk", 64))
    ready_timeout = float(spec.get("ready_timeout", 180))
    request_timeout = float(spec.get("request_timeout", 60))

    session = Session(root, ready_timeout, request_timeout)
    out: dict = {"status": "ok", "results": {}, "files": [], "reasons": {},
                 "server_restarts": 0,
                 "pyright": os.environ.get("PYRIGHT_VERSION", "")}
    try:
        session.start()
    except (FileNotFoundError, LspError, TimeoutError) as exc:
        out["status"] = f"server_unavailable: {type(exc).__name__}: {exc}"
        write_atomic(work / "definitions.json", out)
        return 3

    started = time.time()
    for entry in spec["files"]:
        rel = entry["relative_path"]
        positions = entry["positions"]
        file_started = time.time()
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            out["files"].append({"relative_path": rel, "error": str(exc)})
            continue
        if not session.alive() and session.restart() is None:
            out["status"] = "restart_budget_exhausted"
            break
        try:
            uri, ready = session.open_file(rel, text)
        except (LspError, BrokenPipeError, OSError):
            if session.restart() is None:
                out["status"] = "restart_budget_exhausted"
                break
            uri, ready = session.open_file(rel, text)
        answered = {}
        if ready:
            answered = session.resolve(uri, positions, chunk)
            out["results"].update(answered)
        try:
            if session.alive():
                assert session.client is not None
                session.client.did_close(uri)
        except (LspError, BrokenPipeError, OSError):
            pass
        out["files"].append({
            "relative_path": rel,
            "positions": len(positions),
            "ready": ready,
            "answered": len(answered),
            "seconds": round(time.time() - file_started, 2),
        })
        print(f"[{len(out['files'])}/{len(spec['files'])}] {rel} "
              f"{len(answered)}/{len(positions)}"
              f"{'' if ready else ' UNREADY'}", file=sys.stderr)

    out["server_restarts"] = session.restarts
    out["reasons"] = dict(sorted(session.reasons.items()))
    out["wall_seconds"] = round(time.time() - started, 2)
    if session.client is not None:
        session.client.shutdown()
    write_atomic(work / "definitions.json", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
