"""Read-only Docker container metrics collection.

``container.stats(stream=False)`` is the only Docker API call made here.
No destructive operations are performed.  Stats payloads vary significantly
across Docker versions and cgroups v1/v2; every parser degrades gracefully
to 0 / ``None`` rather than raising.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Individual stat parsers ───────────────────────────────────────────────────

def parse_cpu_percent(stats: dict) -> float:
    """Return CPU usage as a percentage of all available CPUs.

    Formula (Docker documentation)::

        cpu_delta    = cpu_stats.cpu_usage.total_usage
                     - precpu_stats.cpu_usage.total_usage
        system_delta = cpu_stats.system_cpu_usage
                     - precpu_stats.system_cpu_usage
        online_cpus  = cpu_stats.online_cpus
                       or len(cpu_stats.cpu_usage.percpu_usage) or 1
        cpu_percent  = (cpu_delta / system_delta) * online_cpus * 100

    Returns ``0.0`` if any delta is missing, zero, or otherwise invalid.
    Never raises.
    """
    try:
        cpu = stats.get("cpu_stats") or {}
        pre = stats.get("precpu_stats") or {}
        cpu_usage = cpu.get("cpu_usage") or {}
        pre_usage = pre.get("cpu_usage") or {}

        cpu_delta    = (cpu_usage.get("total_usage") or 0) - (pre_usage.get("total_usage") or 0)
        system_delta = (cpu.get("system_cpu_usage") or 0) - (pre.get("system_cpu_usage") or 0)

        if system_delta <= 0 or cpu_delta < 0:
            return 0.0

        online_cpus = cpu.get("online_cpus")
        if not online_cpus:
            percpu = cpu_usage.get("percpu_usage") or []
            online_cpus = len(percpu) if percpu else 1

        return round((cpu_delta / system_delta) * online_cpus * 100.0, 2)
    except (TypeError, ZeroDivisionError, KeyError, AttributeError):
        return 0.0


def parse_memory(stats: dict) -> Dict[str, Any]:
    """Return memory usage, limit, and percent from a Docker stats payload.

    Returns zeroes (not ``None``) on any error so callers can always
    do arithmetic without guards.
    """
    try:
        mem   = stats.get("memory_stats") or {}
        usage = mem.get("usage") or 0
        limit = mem.get("limit") or 0
        pct   = round(usage / limit * 100.0, 2) if limit > 0 else 0.0
        return {
            "memoryUsageBytes": usage,
            "memoryLimitBytes": limit,
            "memoryPercent":    pct,
        }
    except (TypeError, ZeroDivisionError, AttributeError):
        return {"memoryUsageBytes": 0, "memoryLimitBytes": 0, "memoryPercent": 0.0}


def parse_network(stats: dict) -> Dict[str, int]:
    """Return total network rx/tx bytes aggregated across all interfaces."""
    try:
        networks = stats.get("networks") or {}
        rx = sum((v or {}).get("rx_bytes", 0) for v in networks.values())
        tx = sum((v or {}).get("tx_bytes", 0) for v in networks.values())
        return {"networkRxBytes": rx, "networkTxBytes": tx}
    except (TypeError, AttributeError):
        return {"networkRxBytes": 0, "networkTxBytes": 0}


def parse_blkio(stats: dict) -> Dict[str, int]:
    """Return total block-IO read/write bytes from ``blkio_stats``."""
    try:
        blkio   = stats.get("blkio_stats") or {}
        entries = blkio.get("io_service_bytes_recursive") or []
        read_b = write_b = 0
        for e in entries:
            op  = ((e or {}).get("op") or "").lower()
            val = (e or {}).get("value") or 0
            if op == "read":
                read_b += val
            elif op == "write":
                write_b += val
        return {"blockReadBytes": read_b, "blockWriteBytes": write_b}
    except (TypeError, AttributeError):
        return {"blockReadBytes": 0, "blockWriteBytes": 0}


def parse_pids(stats: dict) -> Optional[int]:
    """Return the current PID count, or ``None`` if unavailable."""
    try:
        current = ((stats or {}).get("pids_stats") or {}).get("current")
        return int(current) if current is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def parse_container_stats(
    container_id: str,
    name: str,
    status: str,
    stats: dict,
) -> Dict[str, Any]:
    """Parse all metric categories from a single container stats payload.

    Parameters
    ----------
    container_id:
        Node-id form ``container:<short_id>`` so the browser can match
        against topology nodes by id.
    name:
        Container name (leading ``/`` stripped).
    status:
        Container status string (``"running"``, ``"exited"``, …).
    stats:
        Raw dict returned by ``container.stats(stream=False)``.
    """
    result: Dict[str, Any] = {
        "id":         container_id,
        "name":       name,
        "status":     status,
        "cpuPercent": parse_cpu_percent(stats),
    }
    result.update(parse_memory(stats))
    result.update(parse_network(stats))
    result.update(parse_blkio(stats))
    pids = parse_pids(stats)
    if pids is not None:
        result["pids"] = pids
    return result


# ── Document-level helpers ────────────────────────────────────────────────────

def _build_summary(containers: List[Dict[str, Any]]) -> Dict[str, Any]:
    running   = [c for c in containers if c.get("status") == "running"]
    cpu_vals  = [c["cpuPercent"] for c in running if "cpuPercent" in c]
    return {
        "containers":            len(containers),
        "runningContainers":     len(running),
        "avgCpuPercent":         round(sum(cpu_vals) / len(cpu_vals), 2) if cpu_vals else 0.0,
        "maxCpuPercent":         round(max(cpu_vals), 2) if cpu_vals else 0.0,
        "totalMemoryUsageBytes": sum(c.get("memoryUsageBytes", 0) for c in containers),
        "totalNetworkRxBytes":   sum(c.get("networkRxBytes",   0) for c in containers),
        "totalNetworkTxBytes":   sum(c.get("networkTxBytes",   0) for c in containers),
    }


# ── Live collection ───────────────────────────────────────────────────────────

def collect_live_metrics() -> Dict[str, Any]:
    """Collect a point-in-time metrics snapshot from all running containers.

    Uses ``container.stats(stream=False)`` — a single read-only API call per
    container.  Containers whose stats call fails are skipped with a warning;
    they do not abort the whole collection.

    Raises
    ------
    RuntimeError
        If the *docker* package is not installed.
    docker.errors.DockerException
        If the Docker daemon is unreachable.
    """
    try:
        import docker  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "The 'docker' package is required for live metrics. "
            "Install it with:  pip install docker"
        ) from exc

    client = docker.from_env()
    containers_out: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for container in client.containers.list():          # running containers only
        cname = (getattr(container, "name", "") or "").lstrip("/")
        try:
            raw_stats = container.stats(stream=False)   # read-only
            full_id   = str(getattr(container, "id", "") or "")
            node_id   = f"container:{full_id[:12]}"
            status    = str(getattr(container, "status", "unknown") or "unknown")
            containers_out.append(
                parse_container_stats(node_id, cname, status, raw_stats)
            )
        except Exception:  # noqa: BLE001
            logger.warning("Stats collection failed for container %r", cname, exc_info=True)
            warnings.append(f"Stats unavailable for {cname!r}")

    return {
        "schemaVersion": "1.0",
        "generatedAt":   _now_iso(),
        "source":        {"engine": "docker", "host": "local"},
        "sample":        False,
        "containers":    containers_out,
        "summary":       _build_summary(containers_out),
        "warnings":      warnings,
    }


# ── Sample data ───────────────────────────────────────────────────────────────

def build_sample_metrics() -> Dict[str, Any]:
    """Return deterministic sample metrics without contacting Docker.

    Container IDs match those in ``scanner.build_sample()`` so the browser
    can correlate glow data with topology nodes.

    Demonstrates four load levels:
    * ``web``     — low CPU, low memory
    * ``api``     — medium CPU, moderate memory
    * ``db``      — high CPU, high memory (triggers glow-critical)
    * ``cache``   — near-idle
    * ``worker-crashed`` — exited, all zeros
    """
    containers: List[Dict[str, Any]] = [
        {
            "id":               "container:abc123abc123",
            "name":             "web",
            "status":           "running",
            "cpuPercent":       1.5,
            "memoryUsageBytes": 52_428_800,       # 50 MiB
            "memoryLimitBytes": 1_073_741_824,    # 1 GiB
            "memoryPercent":    4.88,
            "networkRxBytes":   102_400,
            "networkTxBytes":   204_800,
            "blockReadBytes":   0,
            "blockWriteBytes":  4_096,
            "pids":             5,
        },
        {
            "id":               "container:def456def456",
            "name":             "api",
            "status":           "running",
            "cpuPercent":       32.1,
            "memoryUsageBytes": 209_715_200,      # 200 MiB
            "memoryLimitBytes": 1_073_741_824,
            "memoryPercent":    19.53,
            "networkRxBytes":   512_000,
            "networkTxBytes":   1_024_000,
            "blockReadBytes":   8_192,
            "blockWriteBytes":  16_384,
            "pids":             12,
        },
        {
            "id":               "container:ghi789ghi789",
            "name":             "db",
            "status":           "running",
            "cpuPercent":       87.4,             # triggers glow-critical
            "memoryUsageBytes": 536_870_912,      # 512 MiB
            "memoryLimitBytes": 1_073_741_824,
            "memoryPercent":    50.0,
            "networkRxBytes":   20_480,
            "networkTxBytes":   40_960,
            "blockReadBytes":   4_096_000,
            "blockWriteBytes":  8_192_000,
            "pids":             8,
        },
        {
            "id":               "container:jkl012jkl012",
            "name":             "cache",
            "status":           "running",
            "cpuPercent":       0.3,
            "memoryUsageBytes": 10_485_760,       # 10 MiB
            "memoryLimitBytes": 1_073_741_824,
            "memoryPercent":    0.98,
            "networkRxBytes":   2_048,
            "networkTxBytes":   1_024,
            "blockReadBytes":   0,
            "blockWriteBytes":  0,
            "pids":             4,
        },
        {
            "id":               "container:mno345mno345",
            "name":             "worker-crashed",
            "status":           "exited",
            "cpuPercent":       0.0,
            "memoryUsageBytes": 0,
            "memoryLimitBytes": 0,
            "memoryPercent":    0.0,
            "networkRxBytes":   0,
            "networkTxBytes":   0,
            "blockReadBytes":   0,
            "blockWriteBytes":  0,
        },
    ]

    return {
        "schemaVersion": "1.0",
        "generatedAt":   "2024-01-15T12:00:00Z",
        "source":        {"engine": "sample", "host": "demo"},
        "sample":        True,
        "containers":    containers,
        "summary":       _build_summary(containers),
        "warnings":      [],
    }
