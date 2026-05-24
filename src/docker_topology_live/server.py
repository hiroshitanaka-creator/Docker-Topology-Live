"""HTTP server for Docker Topology Live.

Uses :class:`~http.server.ThreadingHTTPServer` so that long-lived SSE
connections on ``/api/events`` do not block concurrent requests to
``/api/topology``, ``/api/stats``, or static assets.

Security
--------
* Binds to ``127.0.0.1`` by default (loopback only).
* ``Access-Control-Allow-Origin: *`` is **never** sent by default; it is
  opt-in via the ``--allow-cors`` CLI flag.
* Python tracebacks are never forwarded to clients — all error responses
  contain only a safe string derived from the exception message.
* No destructive Docker operations are performed anywhere in this module.
"""
from __future__ import annotations

import json
import logging
import pathlib
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

from .events import SSEWriter, stream_live, stream_sample
from .models import Topology
from .scanner import build_sample, scan_live
from .stats import compute_summary

logger = logging.getLogger(__name__)

_WEB_DIR = pathlib.Path(__file__).parent / "web"


def _get_topology(use_sample: bool) -> Topology:
    if use_sample:
        return build_sample()
    return scan_live()


class _TopologyHandler(BaseHTTPRequestHandler):
    """HTTP request handler for topology endpoints."""

    use_sample: bool = True   # overridden via make_handler()
    allow_cors: bool = False  # overridden via make_handler(); CORS is opt-in only

    def log_message(self, fmt: str, *args: object) -> None:  # type: ignore[override]
        logger.debug("HTTP %s", fmt % args)

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # CORS header is only emitted when explicitly enabled (--allow-cors flag).
        # Sending Access-Control-Allow-Origin: * by default would let any page on
        # the host machine read the full Docker topology including container names,
        # images, network layouts, and labels.
        if self.allow_cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _serve_file(self, rel: str, content_type: str) -> None:
        p = _WEB_DIR / rel
        if not p.is_file():
            self._send_json({"error": "Not found"}, 404)
            return
        self._send_bytes(p.read_bytes(), content_type)

    def _handle_events(self) -> None:
        """Handle ``GET /api/events``: Server-Sent Events stream.

        Sends an initial ``topology`` event and then:

        * **Live mode**: streams Docker container/network events via the
          Docker SDK (read-only); triggers a debounced full rescan on each
          relevant event.
        * **Sample mode**: sends periodic ``heartbeat`` events; no Docker
          required.

        CORS obeys the same ``allow_cors`` flag as all other endpoints.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        if self.allow_cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        writer = SSEWriter(self.wfile)
        if self.use_sample:
            stream_sample(writer, build_sample)
        else:
            stream_live(writer, scan_live)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/healthz":
            self._send_json({"status": "ok"})

        elif path == "/api/topology":
            try:
                topo = _get_topology(self.use_sample)
                self._send_json(topo.to_dict())
            except Exception as exc:
                logger.exception("Topology scan failed")
                self._send_json({"error": str(exc)}, 500)

        elif path == "/api/stats":
            try:
                topo = _get_topology(self.use_sample)
                self._send_json(compute_summary(topo).to_dict())
            except Exception as exc:
                logger.exception("Stats failed")
                self._send_json({"error": str(exc)}, 500)

        elif path == "/api/events":
            try:
                self._handle_events()
            except Exception:
                # Headers may already be sent; log only — do not send error body.
                logger.exception("Unhandled exception in SSE handler")

        elif path == "/assets/styles.css":
            self._serve_file("assets/styles.css", "text/css; charset=utf-8")

        elif path == "/assets/app.js":
            self._serve_file("assets/app.js", "application/javascript; charset=utf-8")

        elif path in ("/", "/index.html"):
            idx = _WEB_DIR / "index.html"
            if idx.is_file():
                self._send_bytes(idx.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send_bytes(b"<h1>Docker Topology Live</h1>", "text/html; charset=utf-8")

        else:
            self._send_json({"error": "Not found"}, 404)


def make_handler(use_sample: bool = False, allow_cors: bool = False) -> type:
    """Return a handler class configured for *use_sample* and *allow_cors*.

    Parameters
    ----------
    use_sample:
        When *True* the handler returns sample topology data without
        contacting the Docker daemon.
    allow_cors:
        When *True* responses include ``Access-Control-Allow-Origin: *``.
        Defaults to *False* — wildcard CORS is **not** sent by default
        because the server exposes Docker metadata and binds to loopback.
    """

    class Handler(_TopologyHandler):
        pass

    Handler.use_sample = use_sample
    Handler.allow_cors = allow_cors
    return Handler


def serve(
    host: str = "127.0.0.1",
    port: int = 8080,
    use_sample: bool = False,
    allow_cors: bool = False,
) -> None:
    """Start the HTTP server and block until interrupted.

    Uses :class:`~http.server.ThreadingHTTPServer` with ``daemon_threads=True``
    so that long-lived ``/api/events`` SSE connections run in daemon threads
    and do not prevent a clean shutdown on ``KeyboardInterrupt``.

    Parameters
    ----------
    host:
        Interface to bind (default ``127.0.0.1`` — loopback only).
    port:
        TCP port (default ``8080``).
    use_sample:
        Serve sample topology data instead of querying Docker.
    allow_cors:
        Emit ``Access-Control-Allow-Origin: *`` on every response.
        Off by default; pass ``True`` only when cross-origin access
        is deliberately required (e.g. a separate front-end dev server).
    """
    handler_cls = make_handler(use_sample=use_sample, allow_cors=allow_cors)
    httpd = ThreadingHTTPServer((host, port), handler_cls)
    # SSE connections are long-lived; use daemon threads so they do not
    # block a clean shutdown when the user presses Ctrl-C.
    httpd.daemon_threads = True

    mode = "sample" if use_sample else "live"
    cors_note = "  [CORS: *]" if allow_cors else ""
    print(
        f"Docker Topology Live [{mode}] → http://{host}:{port}/{cors_note}\n"
        f"  Live stream: http://{host}:{port}/api/events  (SSE)",
        flush=True,
    )
    logger.info(
        "Listening on http://%s:%d/ [%s] allow_cors=%s (ThreadingHTTPServer)",
        host, port, mode, allow_cors,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
