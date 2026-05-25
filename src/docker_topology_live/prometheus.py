"""Prometheus text exposition format exporter for Docker Topology Live.

Converts a metrics document (from :mod:`docker_topology_live.metrics`) into
Prometheus text exposition format version 0.0.4.

This module is **read-only** and **stateless**: every call to
:func:`format_prometheus_metrics` produces a fresh point-in-time snapshot.
Nothing is persisted.  No external services are contacted.

Text format reference:
  https://prometheus.io/docs/instrumenting/exposition_formats/#text-format-details

Security notes:
  - Only already-normalised metric fields from the metrics document are
    exposed (container id, name, status, numeric counters).
  - Raw Docker labels, environment variables, mount paths, and host paths
    are never included in the output.
  - Label values are escaped per the Prometheus spec.
"""
from __future__ import annotations

from typing import List, Tuple

# Common prefix for every exported metric name
_PREFIX = "docker_topology_live"

# Prometheus text-format content type
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


# ── Label helpers ─────────────────────────────────────────────────────────────

def escape_label_value(value: str) -> str:
    r"""Escape a Prometheus label value per the text exposition format spec.

    The spec requires three characters to be escaped:

    - ``\`` (backslash)  →  ``\\``
    - ``"`` (double-quote)  →  ``\"``
    - newline (``\n``)  →  ``\\n``

    Parameters
    ----------
    value:
        Raw label value string.

    Returns
    -------
    str
        Escaped string safe to embed inside ``"…"`` in a Prometheus label set.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("\n", "\\n")
    return value


def _label_set(pairs: List[Tuple[str, str]]) -> str:
    """Format a list of ``(name, value)`` pairs as a Prometheus label set.

    Returns an empty string when *pairs* is empty; otherwise
    ``{name="value",...}``.
    """
    if not pairs:
        return ""
    inner = ",".join(
        '{}="{}"'.format(name, escape_label_value(str(value)))
        for name, value in pairs
    )
    return "{" + inner + "}"


def _fmt_value(value: float) -> str:
    """Format a numeric value for Prometheus output.

    Integer-valued floats are written without a decimal point (``42`` not
    ``42.0``) to keep the output clean.  The result is always a valid
    Prometheus float literal.
    """
    f = float(value)
    if f == int(f) and not (f != f):  # not NaN
        return str(int(f))
    return repr(f)


def _metric_line(metric_name: str, labels: List[Tuple[str, str]], value: float) -> str:
    """Return a single Prometheus sample line (no trailing newline)."""
    full_name = "{}_{}".format(_PREFIX, metric_name)
    return "{}{} {}".format(full_name, _label_set(labels), _fmt_value(value))


def _gauge_block(
    metric_name: str,
    help_text: str,
    sample_lines: List[str],
) -> str:
    """Return ``# HELP``, ``# TYPE``, and sample lines joined by newlines."""
    full_name = "{}_{}".format(_PREFIX, metric_name)
    parts: List[str] = [
        "# HELP {} {}".format(full_name, help_text),
        "# TYPE {} gauge".format(full_name),
    ]
    parts.extend(sample_lines)
    return "\n".join(parts)


# ── Public formatter ──────────────────────────────────────────────────────────

# Per-container metric specifications:
# (metric_name, help_text, field_in_container_doc)
_CONTAINER_METRICS: List[Tuple[str, str, str]] = [
    (
        "container_cpu_percent",
        "Container CPU usage as a percentage of all available CPUs (point-in-time).",
        "cpuPercent",
    ),
    (
        "container_memory_usage_bytes",
        "Container memory usage in bytes (point-in-time).",
        "memoryUsageBytes",
    ),
    (
        "container_memory_limit_bytes",
        "Container memory limit in bytes as reported by the Docker daemon.",
        "memoryLimitBytes",
    ),
    (
        "container_memory_percent",
        "Container memory usage as a percentage of the memory limit (point-in-time).",
        "memoryPercent",
    ),
    (
        "container_network_rx_bytes",
        "Container cumulative network receive bytes.",
        "networkRxBytes",
    ),
    (
        "container_network_tx_bytes",
        "Container cumulative network transmit bytes.",
        "networkTxBytes",
    ),
    (
        "container_block_read_bytes",
        "Container cumulative block device read bytes.",
        "blockReadBytes",
    ),
    (
        "container_block_write_bytes",
        "Container cumulative block device write bytes.",
        "blockWriteBytes",
    ),
]


def format_prometheus_metrics(metrics_doc: dict) -> str:
    """Format a metrics document as Prometheus text exposition format.

    Parameters
    ----------
    metrics_doc:
        Dict produced by
        :func:`~docker_topology_live.metrics.build_sample_metrics` or
        :func:`~docker_topology_live.metrics.collect_live_metrics`.

    Returns
    -------
    str
        A valid Prometheus text exposition string that ends with a newline.
        Never raises; an empty or partial metrics document produces a minimal
        valid response with ``metrics_warnings_total`` reflecting any
        collection warnings.
    """
    containers: list = list(metrics_doc.get("containers") or [])
    summary:    dict = dict(metrics_doc.get("summary") or {})
    warnings:   list = list(metrics_doc.get("warnings") or [])

    # Sort containers deterministically by id
    containers_sorted = sorted(containers, key=lambda c: str(c.get("id", "")))

    blocks: List[str] = []

    # ── Summary counters ──────────────────────────────────────────────────────

    total = summary.get("containers", len(containers))
    blocks.append(
        _gauge_block(
            "containers_total",
            "Total number of containers in the metrics snapshot.",
            [_metric_line("containers_total", [], total)],
        )
    )

    running = summary.get("runningContainers", 0)
    blocks.append(
        _gauge_block(
            "running_containers",
            "Number of running containers in the metrics snapshot.",
            [_metric_line("running_containers", [], running)],
        )
    )

    # ── Per-container gauges ──────────────────────────────────────────────────

    for metric_name, help_text, field in _CONTAINER_METRICS:
        sample_lines: List[str] = []
        for c in containers_sorted:
            value = c.get(field)
            if value is None:
                continue
            labels = [
                ("container_id",   str(c.get("id",     ""))),
                ("container_name", str(c.get("name",   ""))),
                ("status",         str(c.get("status", ""))),
            ]
            sample_lines.append(_metric_line(metric_name, labels, float(value)))
        if sample_lines:
            blocks.append(_gauge_block(metric_name, help_text, sample_lines))

    # PIDs — optional field, omit when absent
    pid_lines: List[str] = []
    for c in containers_sorted:
        pids = c.get("pids")
        if pids is None:
            continue
        labels = [
            ("container_id",   str(c.get("id",     ""))),
            ("container_name", str(c.get("name",   ""))),
            ("status",         str(c.get("status", ""))),
        ]
        pid_lines.append(_metric_line("container_pids", labels, int(pids)))
    if pid_lines:
        blocks.append(
            _gauge_block(
                "container_pids",
                "Number of processes (PIDs) running inside the container.",
                pid_lines,
            )
        )

    # ── Exporter health ───────────────────────────────────────────────────────

    blocks.append(
        _gauge_block(
            "metrics_warnings_total",
            "Number of warnings produced during the last metrics collection.",
            [_metric_line("metrics_warnings_total", [], len(warnings))],
        )
    )

    return "\n".join(blocks) + "\n"
