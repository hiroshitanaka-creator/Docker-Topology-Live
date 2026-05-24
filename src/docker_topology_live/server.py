"""HTTP server for Docker Topology Live.

Uses :class:`~http.server.ThreadingHTTPServer` so that long-lived SSE
connections on ``/api/events`` do not block concurrent requests to
``/api/topology``, ``/api/stats``, or static assets.

Security
--------
* Binds to ``127.0.0.1`` by default (loopback only).
* ``Access-Control-Allow-Origin: *`` is **never** sent by default; it is
  opt-in via the ``--allow-cors`` CLI flag.
* Python tracebacks are never forwarded to clients.
* No destructive Docker operations are performed anywhere in this module.
* Metrics collection (``--metrics``) is opt-in and read-only.
* Diagnostics (``--diagnostics``) is opt-in, local, and read-only.
"""
from __future__ import annotations

import json
import logging
import pathlib
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from typing import Optional

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


def _get_metrics(use_sample: bool) -> dict:
    """Return a metrics document (sample or live)."""
    from .metrics import build_sample_metrics, collect_live_metrics
    if use_sample:
        return build_sample_metrics()
    return collect_live_metrics()


def _get_diagnostics(use_sample: bool, use_metrics: bool = False) -> dict:
    """Return a diagnostics document (sample or live)."""
    from .diagnostics import analyze_topology, build_sample_diagnostics
    if use_sample:
        return build_sample_diagnostics()
    topo = _get_topology(use_sample=False)
    metrics = None
    warnings: list = []
    if use_metrics:
        try:
            metrics = _get_metrics(use_sample=False)
        except Exception:
            logger.warning("Metrics unavailable for diagnostics; continuing without metrics")
            warnings.append(
                "Metrics unavailable for diagnostics; resource rules were skipped."
            )
    return analyze_topology(topo, metrics, warnings=warnings)


class _TopologyHandler(BaseHTTPRequestHandler):
    """HTTP request handler for topology endpoints."""

    use_sample:           bool  = True    # overridden via make_handler()
    allow_cors:           bool  = False   # overridden via make_handler(); CORS is opt-in only
    enable_metrics:       bool  = False   # overridden via make_handler()
    metrics_interval:     float = 2.0    # overridden via make_handler()
    enable_diagnostics:   bool  = False   # overridden via make_handler()
    diagnostics_interval: float = 5.0    # overridden via make_handler()

    def log_message(self, fmt: str, *args: object) -> None:  # type: ignore[override]
        logger.debug("HTTP %s", fmt % args)

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
        """Handle GET /api/events: Server-Sent Events stream."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        if self.allow_cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Resolve metrics callable (only when opted in)
        metrics_fn = None
        if self.enable_metrics:
            from .metrics import build_sample_metrics, collect_live_metrics
            metrics_fn = build_sample_metrics if self.use_sample else collect_live_metrics

        # Resolve diagnostics callable (only when opted in)
        diag_fn = None
        if self.enable_diagnostics:
            from .diagnostics import analyze_topology, build_sample_diagnostics
            if self.use_sample:
                diag_fn = build_sample_diagnostics
            else:
                _use_metrics = self.enable_metrics

                def _live_diag(_scan=scan_live, _um=_use_metrics):
                    topo = _scan()
                    metrics = None
                    _warnings: list = []
                    if _um:
                        try:
                            from .metrics import collect_live_metrics as _clm
                            metrics = _clm()
                        except Exception:
                            _warnings.append(
                                "Metrics unavailable for diagnostics; "
                                "resource rules were skipped."
                            )
                    return analyze_topology(topo, metrics, warnings=_warnings)

                diag_fn = _live_diag

        writer = SSEWriter(self.wfile)
        if self.use_sample:
            stream_sample(
                writer,
                build_sample,
                metrics_fn=metrics_fn,
                metrics_interval=self.metrics_interval,
                diag_fn=diag_fn,
                diag_interval=self.diagnostics_interval,
            )
        else:
            stream_live(
                writer,
                scan_live,
                metrics_fn=metrics_fn,
                metrics_interval=self.metrics_interval,
                diag_fn=diag_fn,
                diag_interval=self.diagnostics_interval,
            )

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

        elif path == "/api/metrics":
            try:
                data = _get_metrics(self.use_sample)
                self._send_json(data)
            except Exception as exc:
                logger.exception("Metrics collection failed")
                self._send_json({"error": str(exc)}, 500)

        elif path == "/api/diagnostics":
            try:
                data = _get_diagnostics(self.use_sample, use_metrics=self.enable_metrics)
                self._send_json(data)
            except Exception as exc:
                logger.exception("Diagnostics failed")
                self._send_json({"error": str(exc)}, 500)

        elif path == "/api/events":
            try:
                self._handle_events()
            except Exception:
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


def make_handler(
    use_sample:           bool  = False,
    allow_cors:           bool  = False,
    enable_metrics:       bool  = False,
    metrics_interval:     float = 2.0,
    enable_diagnostics:   bool  = False,
    diagnostics_interval: float = 5.0,
) -> type:
    """Return a handler class configured with the supplied options."""

    class Handler(_TopologyHandler):
        pass

    Handler.use_sample           = use_sample
    Handler.allow_cors           = allow_cors
    Handler.enable_metrics       = enable_metrics
    Handler.metrics_interval     = metrics_interval
    Handler.enable_diagnostics   = enable_diagnostics
    Handler.diagnostics_interval = diagnostics_interval
    return Handler


def serve(
    host:                 str   = "127.0.0.1",
    port:                 int   = 8080,
    use_sample:           bool  = False,
    allow_cors:           bool  = False,
    enable_metrics:       bool  = False,
    metrics_interval:     float = 2.0,
    enable_diagnostics:   bool  = False,
    diagnostics_interval: float = 5.0,
) -> None:
    """Start the HTTP server and block until interrupted."""
    handler_cls = make_handler(
        use_sample=use_sample,
        allow_cors=allow_cors,
        enable_metrics=enable_metrics,
        metrics_interval=metrics_interval,
        enable_diagnostics=enable_diagnostics,
        diagnostics_interval=diagnostics_interval,
    )
    httpd = ThreadingHTTPServer((host, port), handler_cls)
    httpd.daemon_threads = True

    mode      = "sample" if use_sample else "live"
    cors_note = "  [CORS: *]"         if allow_cors         else ""
    met_note  = "  [metrics on]"      if enable_metrics     else ""
    diag_note = "  [diagnostics on]"  if enable_diagnostics else ""
    print(
        f"Docker Topology Live [{mode}] -> http://{host}:{port}/{cors_note}{met_note}{diag_note}\n"
        f"  Topology stream:  http://{host}:{port}/api/events  (SSE)\n"
        f"  Metrics:          http://{host}:{port}/api/metrics"
        + ("  (also in SSE)" if enable_metrics else "  (HTTP only)") + "\n"
        f"  Diagnostics:      http://{host}:{port}/api/diagnostics"
        + ("  (also in SSE)" if enable_diagnostics else "  (HTTP only)"),
        flush=True,
    )
    logger.info(
        "Listening on http://%s:%d/ [%s] allow_cors=%s enable_metrics=%s "
        "metrics_interval=%.1fs enable_diagnostics=%s diagnostics_interval=%.1fs "
        "(ThreadingHTTPServer)",
        host, port, mode, allow_cors, enable_metrics, metrics_interval,
        enable_diagnostics, diagnostics_interval,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
