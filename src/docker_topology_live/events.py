"""Server-Sent Events support and Docker event watcher.

No destructive Docker operations are performed (no stop/remove/kill/prune/exec/run).
Raw Docker event dicts are normalised into a small safe subset before entering any
SSE payload.  Python tracebacks are logged server-side but never sent to clients.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── Event filtering ───────────────────────────────────────────────────────────

_RELEVANT_TYPES: frozenset[str] = frozenset({"container", "network"})

_RELEVANT_ACTIONS: frozenset[str] = frozenset({
    # Container lifecycle
    "create", "start", "stop", "die", "destroy", "remove",
    "pause", "unpause", "restart", "rename", "health_status",
    # Network membership
    "connect", "disconnect",
})


def is_relevant_event(event: dict) -> bool:
    """Return *True* when the event should trigger a topology rescan.

    Only ``container`` and ``network`` events with a lifecycle or membership
    action are considered relevant.  All other events (image pull, volume
    create, plugin events, etc.) are filtered out.
    """
    return (
        event.get("Type") in _RELEVANT_TYPES
        and event.get("Action") in _RELEVANT_ACTIONS
    )


def normalize_event(event: dict) -> dict:
    """Extract a small, safe subset of a raw Docker event dictionary.

    Keys emitted: ``type``, ``action``, ``id``, ``name``, ``time``, ``scope``.
    No raw container metadata, environment variables, or host paths are
    included.
    """
    actor: dict = event.get("Actor") or {}
    attrs: dict = actor.get("Attributes") or {}
    return {
        "type":   str(event.get("Type",   "")),
        "action": str(event.get("Action", "")),
        "id":     str(actor.get("ID", event.get("id", ""))),
        "name":   str(attrs.get("name", "")),
        "time":   str(event.get("time", "")),
        "scope":  "docker",
    }


# ── SSE wire encoding ─────────────────────────────────────────────────────────

def format_sse(event_type: str, data: str) -> bytes:
    """Encode one SSE event block (terminated by a blank line).

    Example output for a topology event::

        event: topology\\n
        data: {"schemaVersion":"1.0",...}\\n
        \\n

    Multi-line *data* is split into multiple ``data:`` lines as required by
    the SSE specification.
    """
    lines = [f"event: {event_type}"]
    for line in data.splitlines():
        lines.append(f"data: {line}")
    lines.append("")
    lines.append("")
    return "\n".join(lines).encode("utf-8")


# ── Thread-safe SSE writer ────────────────────────────────────────────────────

class SSEWriter:
    """Thread-safe wrapper around an HTTP response *wfile* for SSE output.

    Multiple threads (e.g. the debounce timer thread, the metrics thread,
    and the main event-loop thread) may call :meth:`write` concurrently.
    A :class:`threading.Lock` serialises all writes.

    Parameters
    ----------
    wfile:
        The writable file-like object from
        :class:`~http.server.BaseHTTPRequestHandler`.
    """

    def __init__(self, wfile: Any) -> None:
        self._wfile  = wfile
        self._lock   = threading.Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        """*True* once the connection is known to be closed."""
        return self._closed

    def write(self, event_type: str, data: str) -> bool:
        """Write and flush one SSE event.

        Returns
        -------
        bool
            *False* if the connection was already closed or a write error
            occurred (client disconnected).  Never raises.
        """
        if self._closed:
            return False
        with self._lock:
            try:
                payload = format_sse(event_type, data)
                self._wfile.write(payload)
                self._wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError, OSError):
                self._closed = True
                return False

    def close(self) -> None:
        """Mark the writer as closed without touching the underlying file."""
        self._closed = True


# ── Debounced topology rescan ─────────────────────────────────────────────────

class _DebounceRescan:
    """Schedule topology rescans with debounce to absorb compose-up/down bursts.

    When :meth:`trigger` is called, any pending scan is cancelled and a new
    one is scheduled after *delay* seconds.  This prevents dozens of scans
    during a rapid ``docker compose up`` sequence.
    """

    def __init__(
        self,
        scan_fn: Callable,
        writer: SSEWriter,
        delay: float = 0.35,
    ) -> None:
        self._scan_fn = scan_fn
        self._writer  = writer
        self._delay   = delay
        self._timer: Optional[threading.Timer] = None
        self._lock    = threading.Lock()

    def trigger(self) -> None:
        """Schedule a debounced rescan, cancelling any already-pending one."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            t = threading.Timer(self._delay, self._run)
            t.daemon = True
            self._timer = t
            t.start()

    def _run(self) -> None:
        try:
            topo = self._scan_fn()
            self._writer.write("topology", topo.to_json())
        except Exception:  # noqa: BLE001
            logger.exception("Debounced topology rescan failed")
            safe = json.dumps({"error": "Rescan failed", "recoverable": True})
            self._writer.write("error", safe)

    def cancel(self) -> None:
        """Cancel any pending scan timer."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


# ── Periodic metrics emitter ──────────────────────────────────────────────────

class _PeriodicMetrics:
    """Collect and emit ``metrics`` SSE events on a background thread.

    Runs in a daemon thread alongside the main Docker-event or heartbeat
    loop.  Stops automatically when the :class:`SSEWriter` is closed or
    when :meth:`stop` is called.

    Metrics collection is **opt-in** — this class is only instantiated when
    ``--metrics`` is passed to the server.

    Parameters
    ----------
    writer:
        Thread-safe SSE writer shared with the caller.
    metrics_fn:
        Callable returning a metrics document dict.
        Typically :func:`~docker_topology_live.metrics.collect_live_metrics`
        or :func:`~docker_topology_live.metrics.build_sample_metrics`.
    interval:
        Seconds between metric snapshots (default 2.0).
    """

    def __init__(
        self,
        writer: SSEWriter,
        metrics_fn: Callable,
        interval: float = 2.0,
    ) -> None:
        self._writer     = writer
        self._metrics_fn = metrics_fn
        self._interval   = interval
        self._stop       = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background metrics thread."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the metrics thread to exit (non-blocking)."""
        self._stop.set()

    def _emit_once(self) -> bool:
        """Emit one metrics snapshot. Returns *False* if writer is closed."""
        if self._writer.closed:
            return False
        try:
            doc = self._metrics_fn()
            return self._writer.write("metrics", json.dumps(doc))
        except Exception:  # noqa: BLE001
            logger.exception("Metrics collection failed in SSE stream")
            safe = json.dumps({"error": "Metrics collection failed", "recoverable": True})
            return self._writer.write("error", safe)

    def _run(self) -> None:
        # Initial snapshot on connect
        if not self._emit_once():
            return
        # Periodic snapshots
        while not self._stop.wait(timeout=self._interval):
            if self._writer.closed:
                break
            if not self._emit_once():
                break


# ── Streaming helpers ─────────────────────────────────────────────────────────

def stream_live(
    writer: SSEWriter,
    scan_fn: Callable,
    metrics_fn: Optional[Callable] = None,
    metrics_interval: float = 2.0,
) -> None:
    """Stream Docker events and full topology snapshots to *writer*.

    Behaviour
    ---------
    1. Sends an initial ``topology`` event immediately on connection.
    2. Subscribes to the Docker event stream (read-only).
    3. For each relevant container/network event:
       a. Sends a ``docker-event`` notification.
       b. Schedules a debounced (350 ms) topology rescan and sends the
          resulting ``topology`` snapshot.
    4. If *metrics_fn* is provided, starts a background thread that emits
       ``metrics`` events every *metrics_interval* seconds.
    5. Sends an ``error`` event if the Docker daemon disconnects; the client
       can fall back to polling.

    Python tracebacks are **never** forwarded to the client.

    Parameters
    ----------
    writer:
        Thread-safe SSE writer for the open connection.
    scan_fn:
        Callable that returns a :class:`~docker_topology_live.models.Topology`.
        Typically :func:`~docker_topology_live.scanner.scan_live`.
    metrics_fn:
        Optional callable returning a metrics document dict.  When *None*,
        no ``metrics`` events are emitted.
    metrics_interval:
        Seconds between metric snapshots (used only when *metrics_fn* is set).
    """
    try:
        import docker  # type: ignore
    except ImportError:
        logger.warning("docker package not available in live event stream")
        writer.write("error", json.dumps({
            "error": "docker package not installed; start with --sample flag",
            "recoverable": False,
        }))
        return

    try:
        client = docker.from_env()
    except Exception:  # noqa: BLE001
        logger.exception("Docker connection failed in SSE stream")
        writer.write("error", json.dumps({
            "error": "Cannot connect to Docker daemon",
            "recoverable": True,
        }))
        return

    # Initial topology snapshot
    try:
        topo = scan_fn()
        if not writer.write("topology", topo.to_json()):
            return
    except Exception:  # noqa: BLE001
        logger.exception("Initial SSE topology scan failed")
        writer.write("error", json.dumps({
            "error": "Initial topology scan failed",
            "recoverable": True,
        }))

    debouncer      = _DebounceRescan(scan_fn, writer, delay=0.35)
    metrics_thread: Optional[_PeriodicMetrics] = None

    if metrics_fn is not None:
        metrics_thread = _PeriodicMetrics(writer, metrics_fn, interval=metrics_interval)
        metrics_thread.start()

    try:
        for raw in client.events(decode=True):
            if writer.closed:
                break
            if not is_relevant_event(raw):
                continue
            norm = normalize_event(raw)
            if not writer.write("docker-event", json.dumps(norm)):
                break
            debouncer.trigger()
    except Exception:  # noqa: BLE001
        logger.exception("Docker event stream error in SSE handler")
        writer.write("error", json.dumps({
            "error": "Docker event stream disconnected",
            "recoverable": True,
        }))
    finally:
        debouncer.cancel()
        if metrics_thread is not None:
            metrics_thread.stop()


# Heartbeat loop parameters (kept as module-level so tests can override)
_HEARTBEAT_STEP: float = 1.0    # seconds between disconnect-check iterations
_HEARTBEAT_INTERVAL: float = 30.0  # seconds between heartbeat SSE events


def stream_sample(
    writer: SSEWriter,
    scan_fn: Callable,
    heartbeat_interval: float = _HEARTBEAT_INTERVAL,
    metrics_fn: Optional[Callable] = None,
    metrics_interval: float = 2.0,
) -> None:
    """Stream a sample topology with periodic heartbeat events.

    Does **not** require the Docker package or daemon.  Sends one initial
    ``topology`` event, optionally starts a metrics thread, then emits
    ``heartbeat`` events every *heartbeat_interval* seconds until the
    client disconnects.

    Parameters
    ----------
    writer:
        Thread-safe SSE writer.
    scan_fn:
        Callable returning a sample :class:`~docker_topology_live.models.Topology`.
        Typically :func:`~docker_topology_live.scanner.build_sample`.
    heartbeat_interval:
        Seconds between heartbeat events (default 30).
    metrics_fn:
        Optional callable returning a sample metrics document dict.
    metrics_interval:
        Seconds between metrics events (used only when *metrics_fn* is set).
    """
    try:
        topo = scan_fn()
        if not writer.write("topology", topo.to_json()):
            return
    except Exception:  # noqa: BLE001
        logger.exception("Sample topology build failed in SSE stream")
        writer.write("error", json.dumps({
            "error": "Sample topology build failed",
            "recoverable": True,
        }))
        return

    metrics_thread: Optional[_PeriodicMetrics] = None
    if metrics_fn is not None:
        metrics_thread = _PeriodicMetrics(writer, metrics_fn, interval=metrics_interval)
        metrics_thread.start()

    try:
        elapsed = 0.0
        while not writer.closed:
            time.sleep(_HEARTBEAT_STEP)
            if writer.closed:
                break
            elapsed += _HEARTBEAT_STEP
            if elapsed >= heartbeat_interval:
                elapsed = 0.0
                ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                if not writer.write("heartbeat", json.dumps({"ok": True, "ts": ts})):
                    break
    finally:
        if metrics_thread is not None:
            metrics_thread.stop()
