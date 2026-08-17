#!/usr/bin/env python3
"""A minimal LSP client over stdio, for driving `pyright-langserver`.

Phase 1 §1.2. Exists because Pyright has no batch mode that answers the one
question baseline 2 needs -- "what definition does this call site resolve
to?". `--outputjson` returns diagnostics; `--verifytypes` returns coverage.
Neither returns a resolution. The language server does, via
`textDocument/definition`, so the language server is what we drive.

Deliberately small and synchronous. It handles exactly what pyright does on the
wire and nothing else:

  * `Content-Length` framing over a pipe, read through a raw fd with a deadline
    (a buffered reader plus `select` will happily block forever with a complete
    message sitting in the buffer).
  * Pipelined requests -- N requests are written, then N responses collected.
    One round trip per call site would dominate the runtime on a repo with
    50k call sites; per-file batching is what makes the corpus run feasible.
  * Any server-initiated request gets a reply. An unanswered
    `client/registerCapability` leaves pyright waiting, and the whole run then
    looks like a timeout in every file after the first.
  * `workspace/configuration` support is NOT declared, so pyright uses its own
    defaults instead of asking us -- one less thing to answer, and one less
    thing that could differ between machines.

UTF-16 is not a detail to skip: LSP character offsets are UTF-16 code units,
`ast.col_offset` is UTF-8 bytes. On any line with a non-ASCII character the two
disagree and the request silently resolves the wrong token. `utf16_column`
converts.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


def utf16_column(line: str, char_col: int) -> int:
    """CHARACTER column -> LSP UTF-16 code-unit column.

    Takes characters, not `ast` bytes: every caller already holds a character
    column (`callsites.py` converts once, via `nodes.char_col`, because it also
    has to compare against `tokenize`, which is character-based). Feeding this a
    byte offset is silently correct on ASCII and wrong on every line with a
    non-ASCII character before the callee -- which is why the conversion happens
    in exactly one place and this function refuses to guess which unit it got.

    Only characters outside the BMP (emoji, rare CJK) differ from their character
    index, each counting as a surrogate pair.
    """
    if char_col <= 0:
        return 0
    return len(line[:char_col].encode("utf-16-le")) // 2


def path_to_uri(path: Path) -> str:
    return "file://" + str(path)


def uri_to_path(uri: str) -> str:
    if uri.startswith("file://"):
        return uri[len("file://"):]
    return uri


class LspError(RuntimeError):
    pass


@dataclass
class _Reader:
    """Deadline-aware reader over a raw fd, with its own buffer."""

    fd: int
    buf: bytearray = field(default_factory=bytearray)
    eof: bool = False

    def _fill(self, deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("lsp read timed out")
        ready, _, _ = select.select([self.fd], [], [], remaining)
        if not ready:
            raise TimeoutError("lsp read timed out")
        chunk = os.read(self.fd, 65536)
        if not chunk:
            self.eof = True
            raise LspError("language server closed its output")
        self.buf.extend(chunk)

    def read_exactly(self, n: int, deadline: float) -> bytes:
        while len(self.buf) < n:
            self._fill(deadline)
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def read_line(self, deadline: float) -> bytes:
        while b"\r\n" not in self.buf:
            self._fill(deadline)
        idx = self.buf.index(b"\r\n")
        out = bytes(self.buf[:idx])
        del self.buf[: idx + 2]
        return out


class LspClient:
    def __init__(self, argv: list[str], root: Path, cwd: Path | None = None,
                 timeout: float = 120.0, stderr_path: Path | None = None):
        self.argv = argv
        self.root = root
        self.timeout = timeout
        self._stderr_path = stderr_path
        # Kept open for the process's lifetime: when the server dies mid-run,
        # its last words on stderr are the only explanation available, and
        # DEVNULL turns that into an unexplained "closed its output".
        self._stderr = (open(stderr_path, "ab") if stderr_path
                        else subprocess.DEVNULL)
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._stderr, cwd=str(cwd) if cwd else None,
        )
        self._reader = _Reader(self.proc.stdout.fileno())
        self._next_id = 1
        self.server_requests_answered = 0
        self.diagnostics: dict[str, list] = {}

    # -- wire -------------------------------------------------------------

    def _send(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        assert self.proc.stdin is not None
        self.proc.stdin.write(header + body)
        self.proc.stdin.flush()

    def notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request_async(self, method: str, params: dict) -> int:
        rid = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        return rid

    def _read_message(self, deadline: float) -> dict:
        length = None
        while True:
            line = self._reader.read_line(deadline)
            if not line:
                break
            name, _, value = line.decode("ascii", errors="replace").partition(":")
            if name.strip().lower() == "content-length":
                length = int(value.strip())
        if length is None:
            raise LspError("message without Content-Length")
        return json.loads(self._reader.read_exactly(length, deadline).decode("utf-8"))

    def _handle_incoming(self, msg: dict) -> None:
        """Notifications we care about, plus a reply to every server request."""
        method = msg.get("method")
        if method == "textDocument/publishDiagnostics":
            params = msg.get("params", {})
            self.diagnostics[params.get("uri", "")] = params.get("diagnostics", [])
        if "id" in msg and method:
            # A server-initiated request. Any answer beats no answer.
            self._send({"jsonrpc": "2.0", "id": msg["id"], "result": None})
            self.server_requests_answered += 1

    def collect(self, ids: set[int], deadline: float) -> dict[int, dict]:
        """Read until every id in `ids` has answered, or the deadline passes.

        A timeout returns what arrived rather than raising: a single call site
        pyright will not answer must not cost us the other 2000 in the file.
        """
        out: dict[int, dict] = {}
        while ids - out.keys():
            try:
                msg = self._read_message(deadline)
            except TimeoutError:
                break
            if "id" in msg and "method" not in msg:
                rid = msg["id"]
                if isinstance(rid, int) and rid in ids:
                    out[rid] = msg
                continue
            self._handle_incoming(msg)
        return out

    def request(self, method: str, params: dict, timeout: float | None = None) -> dict:
        rid = self.request_async(method, params)
        deadline = time.monotonic() + (timeout or self.timeout)
        got = self.collect({rid}, deadline)
        if rid not in got:
            raise TimeoutError(f"{method} timed out")
        return got[rid]

    # -- lifecycle --------------------------------------------------------

    def initialize(self) -> dict:
        params = {
            "processId": os.getpid(),
            "rootPath": str(self.root),
            "rootUri": path_to_uri(self.root),
            "workspaceFolders": [{"uri": path_to_uri(self.root), "name": self.root.name}],
            "capabilities": {
                "textDocument": {
                    "synchronization": {"dynamicRegistration": False},
                    "definition": {"linkSupport": True},
                    "publishDiagnostics": {"relatedInformation": False},
                },
                # `workspace.configuration` is deliberately absent -- see the
                # module docstring.
                "workspace": {"workspaceFolders": True},
            },
        }
        result = self.request("initialize", params, timeout=self.timeout)
        self.notify("initialized", {})
        return result

    def did_open(self, path: Path, text: str, version: int = 1) -> str:
        uri = path_to_uri(path)
        self.notify("textDocument/didOpen", {
            "textDocument": {"uri": uri, "languageId": "python",
                             "version": version, "text": text},
        })
        return uri

    def did_close(self, uri: str) -> None:
        self.notify("textDocument/didClose", {"textDocument": {"uri": uri}})

    def wait_for_diagnostics(self, uri: str, timeout: float = 60.0) -> bool:
        """Pyright publishes diagnostics for a file once it has analysed it.

        That is the readiness signal: a `definition` request sent before
        analysis can legitimately come back empty, and an empty answer is
        indistinguishable from "unresolvable" -- which would quietly become a
        static miss. Returns False on timeout so the caller can record the file
        as unready instead of trusting its results.
        """
        deadline = time.monotonic() + timeout
        while uri not in self.diagnostics:
            try:
                msg = self._read_message(deadline)
            except (TimeoutError, LspError):
                return False
            if "id" in msg and "method" not in msg:
                continue
            self._handle_incoming(msg)
        return True

    def definition(self, uri: str, line0: int, char0: int) -> int:
        return self.request_async("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line0, "character": char0},
        })

    def shutdown(self) -> None:
        try:
            self.request("shutdown", {}, timeout=15)
            self.notify("exit", {})
        except (TimeoutError, LspError, BrokenPipeError, OSError):
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)


def locations_from_result(result) -> list[tuple[str, int, int]]:
    """Flatten Location | Location[] | LocationLink[] to (path, line0, char0)."""
    if result is None:
        return []
    items = result if isinstance(result, list) else [result]
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        uri = item.get("uri") or item.get("targetUri")
        rng = item.get("range") or item.get("targetSelectionRange") or item.get("targetRange")
        if not uri or not rng:
            continue
        start = rng.get("start", {})
        out.append((uri_to_path(uri), start.get("line", 0), start.get("character", 0)))
    return out
