"""Worker service entrypoint with health endpoint and broker consumer loop."""

from __future__ import annotations

import json
import os
import threading
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.worker.app import run_worker_forever


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return

        payload = json.dumps({"status": "ok", "service": "worker"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def _run_health_server() -> None:
    host = os.getenv("WORKER_HEALTH_HOST", "127.0.0.1")
    port = int(os.getenv("WORKER_HEALTH_PORT") or os.getenv("PORT", "8001"))
    server = ThreadingHTTPServer((host, port), _HealthHandler)
    server.serve_forever()


def main() -> None:
    health_thread = threading.Thread(target=_run_health_server, daemon=True)
    health_thread.start()
    asyncio.run(run_worker_forever())


if __name__ == "__main__":
    main()
