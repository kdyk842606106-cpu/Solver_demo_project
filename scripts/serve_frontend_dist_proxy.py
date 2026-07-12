"""Serve a built frontend directory and proxy API requests to the backend.

This helper is intentionally small and dependency-free so it can run from the
project virtual environment during local browser review.
"""

from __future__ import annotations

import argparse
import http.server
import mimetypes
import socketserver
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class FrontendProxyHandler(http.server.SimpleHTTPRequestHandler):
    dist_dir: Path
    backend_url: str

    def translate_path(self, path: str) -> str:
        parsed = urllib.parse.urlparse(path)
        relative = parsed.path.lstrip("/")
        candidate = (self.dist_dir / relative).resolve()
        try:
            candidate.relative_to(self.dist_dir)
        except ValueError:
            candidate = self.dist_dir / "index.html"
        return str(candidate)

    def do_GET(self) -> None:
        if self._is_backend_path():
            self._proxy()
            return

        requested = Path(self.translate_path(self.path))
        if requested.exists() and requested.is_file():
            self._serve_file(requested)
            return

        self._serve_file(self.dist_dir / "index.html")

    def do_HEAD(self) -> None:
        if self._is_backend_path():
            self._proxy()
            return
        requested = Path(self.translate_path(self.path))
        if not requested.exists() or not requested.is_file():
            requested = self.dist_dir / "index.html"
        self._serve_file(requested, head_only=True)

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_PATCH(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def _is_backend_path(self) -> bool:
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path.startswith("/api/") or parsed.path == "/health"

    def _serve_file(self, path: Path, head_only: bool = False) -> None:
        if not path.exists():
            self.send_error(404, f"Not found: {path.name}")
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def _proxy(self) -> None:
        target = urllib.parse.urljoin(self.backend_url.rstrip("/") + "/", self.path.lstrip("/"))
        body = None
        if "Content-Length" in self.headers:
            body = self.rfile.read(int(self.headers["Content-Length"]))

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        request = urllib.request.Request(target, data=body, headers=headers, method=self.command)

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in {"transfer-encoding", "connection"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as error:
            payload = error.read()
            self.send_response(error.code)
            for key, value in error.headers.items():
                if key.lower() not in {"transfer-encoding", "connection"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:
            message = f"Backend proxy failed: {exc}".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve frontend dist and proxy API calls.")
    parser.add_argument("--dist", default="frontend/dist", help="Built frontend dist directory.")
    parser.add_argument("--backend", default="http://127.0.0.1:8000", help="Backend base URL.")
    parser.add_argument("--host", default="127.0.0.1", help="Listen host.")
    parser.add_argument("--port", type=int, default=5173, help="Listen port.")
    args = parser.parse_args()

    dist_dir = Path(args.dist).resolve()
    index_file = dist_dir / "index.html"
    if not index_file.exists():
        print(f"Missing frontend build: {index_file}", file=sys.stderr)
        return 1

    handler = type(
        "ConfiguredFrontendProxyHandler",
        (FrontendProxyHandler,),
        {"dist_dir": dist_dir, "backend_url": args.backend},
    )

    with socketserver.ThreadingTCPServer((args.host, args.port), handler) as server:
        server.allow_reuse_address = True
        print(f"Serving {dist_dir} at http://{args.host}:{args.port}")
        print(f"Proxying /api and /health to {args.backend}")
        server.serve_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
