from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class FrontendRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self) -> None:
        self.path = self._spa_path(self.path)
        super().do_GET()

    def do_HEAD(self) -> None:
        self.path = self._spa_path(self.path)
        super().do_HEAD()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _spa_path(self, request_path: str) -> str:
        parsed = urlparse(request_path)
        route_path = parsed.path.rstrip("/") or "/"
        candidate = FRONTEND_DIR / route_path.lstrip("/")

        if route_path.startswith("/admin") and not candidate.suffix:
            return "/index.html"

        if route_path != "/" and not candidate.exists() and not candidate.suffix:
            return "/index.html"

        return request_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the static frontend with minimal SPA rewrites.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=3000, help="Port to listen on")
    args = parser.parse_args()

    if not FRONTEND_DIR.exists():
        raise SystemExit(f"frontend directory does not exist: {FRONTEND_DIR}")

    server = ThreadingHTTPServer((args.host, args.port), FrontendRequestHandler)
    print(f"Serving frontend at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
