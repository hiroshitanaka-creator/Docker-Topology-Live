"""Rule-based diagnostics engine for Docker Topology Live.

Analyses a :class:`~docker_topology_live.models.Topology` object (or its
``dict`` representation) and returns a structured report describing security,
reliability, resource, and maintenance findings.

No Docker API calls are made here.  The engine works entirely from the data
already captured in the topology and (optionally) a metrics snapshot.

Usage
-----
    from docker_topology_live.diagnostics import analyze_topology, build_sample_diagnostics

    # From live data
    report = analyze_topology(topology_object, metrics_dict)

    # From sample data (no Docker required)
    report = build_sample_diagnostics()
"""
from __future__ import annotations

import datetime
import hashlib
import re
from typing import Any, Dict, List, Optional, Sequence, Union

# ── Constants ─────────────────────────────────────────────────────────────────

_SCHEMA_VERSION = "1.0"

#: Regex that matches container IDs used as names (12+ hex chars)
_HEX_ID_RE = re.compile(r"^[a-f0-9]{12,}$", re.IGNORECASE)

#: Sensitive bind-mount source paths
_HIGH_BIND_SOURCES = frozenset({"/var/run/docker.sock"})

#: Source prefixes that trigger medium-severity broad-bind-mount
_MEDIUM_BIND_PREFIXES = (
    "/etc",
    "/home",
    "/Users",
    "/proc",
    "/sys",
    "/var/run",
    "/root",
    "/",        # exactly "/" is also medium (handled separately)
)

#: 1 GiB in bytes
_GIB = 1024 ** 3


# ── Finding ID helpers ────────────────────────────────────────────────────────

def _finding_id(rule_id: str, target_id: str, extra: str = "") -> str:
    """Return a deterministic finding ID as ``finding:<sha256[:12]>``."""
    raw = f"{rule_id}:{target_id}:{extra}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"finding:{digest}"


# ── Topology normalisation ────────────────────────────────────────────────────

def _coerce_topology(topology: Any) -> Dict[str, Any]:
    """Return a plain ``dict`` regardless of whether *topology* is a
    :class:`~docker_topology_live.models.Topology` or already a ``dict``.
    """
    if isinstance(topology, dict):
        return topology
    # Topology dataclass — call to_dict() if available
    if hasattr(topology, "to_dict"):
        return topology.to_dict()
    raise TypeError(f"Expected Topology or dict, got {type(topology)!r}")


# ── Node helpers ──────────────────────────────────────────────────────────────

def _containers(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [n for n in nodes if n.get("kind") == "container"]


def _networks(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [n for n in nodes if n.get("kind") == "network"]


def _container_ids_with_links(links: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Map container node-id → list of network node-ids it is linked to."""
    result: Dict[str, List[str]] = {}
    for lnk in links:
        src = lnk.get("source", "")
        tgt = lnk.get("target", "")
        if src.startswith("container:") and tgt.startswith("network:"):
            result.setdefault(src, []).append(tgt)
    return result


def _network_ids_with_containers(links: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Map network node-id → list of container node-ids attached to it."""
    result: Dict[str, List[str]] = {}
    for lnk in links:
        src = lnk.get("source", "")
        tgt = lnk.get("target", "")
        if src.startswith("container:") and tgt.startswith("network:"):
            result.setdefault(tgt, []).append(src)
    return result


# ── Individual rule implementations ──────────────────────────────────────────

def _rule_exposed_port(container: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One finding per published port (host_port is not None)."""
    findings: List[Dict[str, Any]] = []
    node_id = container.get("id", "")
    label = container.get("label", node_id)

    for port in container.get("ports", []):
        host_port = port.get("hostPort")
        if host_port is None:
            continue  # not published to the host — skip

        host_ip: str = port.get("hostIp") or ""
        container_port = port.get("containerPort", "?")
        protocol = port.get("protocol", "tcp")

        # Determine severity from host_ip
        if host_ip in ("127.0.0.1", "::1"):
            severity = "low"
        else:
            # "0.0.0.0", "", None, or anything else → medium
            severity = "medium"

        extra = f"{host_ip}:{host_port}:{container_port}/{protocol}"
        fid = _finding_id("exposed-port", node_id, extra)

        findings.append({
            "id": fid,
            "ruleId": "exposed-port",
            "severity": severity,
            "category": "security",
            "target": {"kind": "container", "id": node_id, "label": label},
            "title": f"Port {container_port}/{protocol} published to host",
            "description": (
                f"Container port {container_port}/{protocol} is published to "
                f"host port {host_port}"
                + (f" on {host_ip}" if host_ip else "")
                + ".  Published ports increase the attack surface of the host."
            ),
            "evidence": {
                "hostIp": host_ip,
                "hostPort": host_port,
                "containerPort": container_port,
                "protocol": protocol,
            },
            "recommendation": (
                "Bind to 127.0.0.1 instead of 0.0.0.0 unless external access "
                "is explicitly required.  Use a reverse proxy for public traffic."
            ) if severity == "medium" else (
                "Verify that localhost-published port is intentional."
            ),
            "confidence": 1.0,
        })
    return findings


def _rule_secret_label(container: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flag containers that carry labels whose values are the redaction marker."""
    node_id = container.get("id", "")
    label = container.get("label", node_id)
    labels: Dict[str, str] = container.get("labels") or {}

    redacted_keys = [k for k, v in labels.items() if v == "***REDACTED***"]
    if not redacted_keys:
        return []

    fid = _finding_id("secret-like-label-redacted", node_id, ",".join(sorted(redacted_keys)))

    return [{
        "id": fid,
        "ruleId": "secret-like-label-redacted",
        "severity": "low",
        "category": "security",
        "target": {"kind": "container", "id": node_id, "label": label},
        "title": "Secret-like label values detected (redacted)",
        "description": (
            f"{len(redacted_keys)} label(s) on container '{label}' contain "
            "secret-like key names whose values have been redacted.  "
            "Embedding secrets in container labels is a security risk."
        ),
        "evidence": {
            "redactedKeyCount": len(redacted_keys),
            "redactedKeys": redacted_keys,
        },
        "recommendation": (
            "Use Docker secrets, environment variables from a secrets manager, "
            "or a vault integration rather than container labels for sensitive values."
        ),
        "confidence": 1.0,
    }]


def _rule_broad_bind_mount(container: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flag bind mounts that expose sensitive host paths."""
    findings: List[Dict[str, Any]] = []
    node_id = container.get("id", "")
    label = container.get("label", node_id)

    for mount in container.get("mounts", []):
        if mount.get("type") != "bind":
            continue  # only bind mounts
        source: str = mount.get("source") or ""
        destination: str = mount.get("destination") or ""

        if source in _HIGH_BIND_SOURCES:
            severity = "high"
        elif source == "/":
            severity = "medium"
        elif any(source.startswith(pfx) for pfx in _MEDIUM_BIND_PREFIXES if pfx != "/"):
            severity = "medium"
        else:
            continue  # not a sensitive path

        fid = _finding_id("broad-bind-mount", node_id, source)
        findings.append({
            "id": fid,
            "ruleId": "broad-bind-mount",
            "severity": severity,
            "category": "security",
            "target": {"kind": "container", "id": node_id, "label": label},
            "title": f"Broad bind mount from sensitive host path: {source}",
            "description": (
                f"Container '{label}' has a bind mount from host path '{source}' "
                f"to '{destination}'.  "
                + (
                    "Mounting the Docker socket grants the container full control "
                    "over the Docker daemon."
                    if source == "/var/run/docker.sock"
                    else f"Mounting '{source}' exposes sensitive host filesystem content."
                )
            ),
            "evidence": {
                "source": source,
                "destination": destination,
                "mode": mount.get("mode", ""),
                "rw": mount.get("rw", True),
            },
            "recommendation": (
                "Remove the Docker socket mount unless this container is a "
                "management tool (e.g. Portainer).  Consider using the Docker "
                "TCP API with TLS instead."
            ) if source == "/var/run/docker.sock" else (
                f"Restrict the mount to the minimum required subdirectory of "
                f"'{source}' and mount it read-only (ro) if possible."
            ),
            "confidence": 1.0,
        })
    return findings


def _rule_privileged_label(container: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flag containers with label keys containing 'privileged' set to truthy values."""
    findings: List[Dict[str, Any]] = []
    node_id = container.get("id", "")
    label_name = container.get("label", node_id)
    labels: Dict[str, str] = container.get("labels") or {}

    for k, v in labels.items():
        if "privileged" in k.lower() and str(v).lower() in {"true", "1", "yes"}:
            fid = _finding_id("privileged-label", node_id, k)
            findings.append({
                "id": fid,
                "ruleId": "privileged-label",
                "severity": "high",
                "category": "security",
                "target": {"kind": "container", "id": node_id, "label": label_name},
                "title": f"Privileged mode indicated by label '{k}'",
                "description": (
                    f"Container '{label_name}' has label '{k}={v}' which suggests "
                    "it may be running in privileged mode.  Privileged containers "
                    "have full access to the host kernel."
                ),
                "evidence": {"labelKey": k, "labelValue": v},
                "recommendation": (
                    "Remove the privileged flag unless absolutely required.  "
                    "Use specific Linux capabilities (--cap-add) instead of "
                    "full privileged mode."
                ),
                "confidence": 0.75,
            })
    return findings


def _rule_exited_container(container: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flag containers in exited, dead, or restarting state."""
    node_id = container.get("id", "")
    label = container.get("label", node_id)
    status = (container.get("status") or "").lower()

    if status not in {"exited", "dead", "restarting"}:
        return []

    severity = "high" if status == "dead" else "medium"
    fid = _finding_id("exited-container", node_id, status)

    return [{
        "id": fid,
        "ruleId": "exited-container",
        "severity": severity,
        "category": "reliability",
        "target": {"kind": "container", "id": node_id, "label": label},
        "title": f"Container is in '{status}' state",
        "description": (
            f"Container '{label}' is currently in the '{status}' state.  "
            + (
                "A dead container could not be stopped normally and may indicate "
                "a serious problem."
                if status == "dead"
                else f"A container in '{status}' state is not serving traffic."
            )
        ),
        "evidence": {"status": status},
        "recommendation": (
            "Investigate the container logs (`docker logs`), resolve the "
            "underlying issue, and restart or remove the container."
        ),
        "confidence": 1.0,
    }]


def _rule_no_network(
    container: Dict[str, Any],
    container_link_map: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """Flag running/paused containers with no network links."""
    node_id = container.get("id", "")
    label = container.get("label", node_id)
    status = (container.get("status") or "").lower()

    # Only flag running or paused containers — skip exited/dead/restarting
    if status not in {"running", "paused"}:
        return []

    if container_link_map.get(node_id):
        return []  # has at least one network link

    fid = _finding_id("no-network", node_id, "")

    return [{
        "id": fid,
        "ruleId": "no-network",
        "severity": "low",
        "category": "reliability",
        "target": {"kind": "container", "id": node_id, "label": label},
        "title": f"Running container '{label}' has no network connections",
        "description": (
            f"Container '{label}' is running but is not attached to any network.  "
            "It cannot communicate with other containers or the host."
        ),
        "evidence": {"status": status, "networkCount": 0},
        "recommendation": (
            "Attach the container to a Docker network with "
            "`docker network connect` or update its Compose/run configuration."
        ),
        "confidence": 1.0,
    }]


def _rule_multi_network(
    container: Dict[str, Any],
    container_link_map: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """Flag containers attached to 2 or more networks (informational)."""
    node_id = container.get("id", "")
    label = container.get("label", node_id)
    networks = container_link_map.get(node_id, [])

    if len(networks) < 2:
        return []

    fid = _finding_id("multi-network-container", node_id, "")

    return [{
        "id": fid,
        "ruleId": "multi-network-container",
        "severity": "info",
        "category": "reliability",
        "target": {"kind": "container", "id": node_id, "label": label},
        "title": f"Container '{label}' is attached to {len(networks)} networks",
        "description": (
            f"Container '{label}' is connected to {len(networks)} networks.  "
            "Multi-network containers act as bridges and warrant a review to "
            "confirm that network segmentation is intentional."
        ),
        "evidence": {"networkCount": len(networks), "networkIds": networks},
        "recommendation": (
            "Review the network topology to ensure that cross-network connectivity "
            "is intentional and that network isolation requirements are met."
        ),
        "confidence": 1.0,
    }]


def _rule_high_cpu(
    container_id: str,
    label: str,
    cpu_percent: float,
) -> Optional[Dict[str, Any]]:
    """High CPU usage rule (requires metrics)."""
    if cpu_percent >= 80:
        severity = "high"
    elif cpu_percent >= 40:
        severity = "medium"
    else:
        return None

    fid = _finding_id("high-cpu", container_id, "")

    return {
        "id": fid,
        "ruleId": "high-cpu",
        "severity": severity,
        "category": "resource",
        "target": {"kind": "container", "id": container_id, "label": label},
        "title": f"High CPU usage: {cpu_percent:.1f}%",
        "description": (
            f"Container '{label}' is consuming {cpu_percent:.1f}% CPU, "
            f"which exceeds the {'critical (80%)' if severity == 'high' else 'warning (40%)'} "
            "threshold."
        ),
        "evidence": {"cpuPercent": cpu_percent},
        "recommendation": (
            "Investigate the workload, profile the application, add CPU limits, "
            "or scale horizontally."
        ),
        "confidence": 1.0,
    }


def _rule_high_memory(
    container_id: str,
    label: str,
    memory_percent: float,
) -> Optional[Dict[str, Any]]:
    """High memory usage rule (requires metrics)."""
    if memory_percent >= 85:
        severity = "high"
    elif memory_percent >= 70:
        severity = "medium"
    else:
        return None

    fid = _finding_id("high-memory", container_id, "")

    return {
        "id": fid,
        "ruleId": "high-memory",
        "severity": severity,
        "category": "resource",
        "target": {"kind": "container", "id": container_id, "label": label},
        "title": f"High memory usage: {memory_percent:.1f}%",
        "description": (
            f"Container '{label}' is using {memory_percent:.1f}% of its memory limit, "
            f"which exceeds the {'critical (85%)' if severity == 'high' else 'warning (70%)'} "
            "threshold."
        ),
        "evidence": {"memoryPercent": memory_percent},
        "recommendation": (
            "Investigate memory leaks, increase the memory limit, or reduce "
            "the application's memory footprint."
        ),
        "confidence": 1.0,
    }


def _rule_high_pids(
    container_id: str,
    label: str,
    pids: int,
) -> Optional[Dict[str, Any]]:
    """High PID count rule (requires metrics)."""
    if pids < 200:
        return None

    fid = _finding_id("high-pids", container_id, "")

    return {
        "id": fid,
        "ruleId": "high-pids",
        "severity": "medium",
        "category": "resource",
        "target": {"kind": "container", "id": container_id, "label": label},
        "title": f"High PID count: {pids}",
        "description": (
            f"Container '{label}' has {pids} running processes, which exceeds "
            "the warning threshold of 200.  A high PID count may indicate a "
            "fork bomb or runaway process."
        ),
        "evidence": {"pids": pids},
        "recommendation": (
            "Investigate the running processes inside the container.  "
            "Consider setting --pids-limit in the container configuration."
        ),
        "confidence": 1.0,
    }


def _rule_high_block_write(
    container_id: str,
    label: str,
    block_write_bytes: int,
) -> Optional[Dict[str, Any]]:
    """High block-write IO rule (requires metrics, heuristic)."""
    if block_write_bytes < _GIB:
        return None

    fid = _finding_id("high-block-write", container_id, "")
    gib_val = round(block_write_bytes / _GIB, 2)

    return {
        "id": fid,
        "ruleId": "high-block-write",
        "severity": "medium",
        "category": "resource",
        "target": {"kind": "container", "id": container_id, "label": label},
        "title": f"High block write IO: {gib_val} GiB (heuristic)",
        "description": (
            f"Container '{label}' has written {gib_val} GiB to block storage "
            "since it started.  This is a cumulative heuristic — high values "
            "may be normal for databases but could also indicate excessive "
            "logging or a write-amplification issue."
        ),
        "evidence": {"blockWriteBytes": block_write_bytes},
        "recommendation": (
            "Review the application's write patterns.  For databases, verify "
            "that WAL/redo log sizes are within expected bounds.  Consider "
            "enabling volume-level IO throttling."
        ),
        "confidence": 0.5,
    }


def _rule_unnamed_container(container: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flag containers with autogenerated or very short names."""
    node_id = container.get("id", "")
    label = container.get("label", node_id)

    if len(label) < 3 or _HEX_ID_RE.match(label):
        fid = _finding_id("unnamed-container", node_id, "")
        return [{
            "id": fid,
            "ruleId": "unnamed-container",
            "severity": "low",
            "category": "maintenance",
            "target": {"kind": "container", "id": node_id, "label": label},
            "title": f"Container has an autogenerated or very short name: '{label}'",
            "description": (
                f"Container '{label}' appears to have an autogenerated or unnamed "
                "identifier.  Descriptive names improve operational clarity."
            ),
            "evidence": {"name": label},
            "recommendation": (
                "Assign a meaningful name with `--name` or via the Compose "
                "`container_name` field."
            ),
            "confidence": 0.6,
        }]
    return []


def _rule_missing_compose_labels(
    container: Dict[str, Any],
    any_container_has_compose: bool,
) -> List[Dict[str, Any]]:
    """Flag containers missing compose labels when others in the env have them."""
    node_id = container.get("id", "")
    label = container.get("label", node_id)
    labels: Dict[str, str] = container.get("labels") or {}

    has_compose = bool(
        labels.get("com.docker.compose.project")
        or labels.get("com.docker.compose.service")
    )

    if has_compose or not any_container_has_compose:
        return []

    fid = _finding_id("missing-compose-labels", node_id, "")
    return [{
        "id": fid,
        "ruleId": "missing-compose-labels",
        "severity": "info",
        "category": "maintenance",
        "target": {"kind": "container", "id": node_id, "label": label},
        "title": f"Container '{label}' is missing Docker Compose labels",
        "description": (
            f"Container '{label}' lacks Docker Compose metadata labels "
            "(com.docker.compose.project / com.docker.compose.service) while "
            "other containers in the environment do have them.  This may indicate "
            "the container was started outside of Compose."
        ),
        "evidence": {"hasComposeProject": False, "hasComposeService": False},
        "recommendation": (
            "Add this container to your docker-compose.yml file, or verify that "
            "it is intentionally managed outside of Compose."
        ),
        "confidence": 0.6,
    }]


def _rule_orphan_network(
    network: Dict[str, Any],
    network_container_map: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """Flag network nodes with no attached containers (excluding default networks)."""
    node_id = network.get("id", "")
    label = network.get("label", node_id)

    # Default Docker networks are never flagged
    if label in {"bridge", "host", "none"}:
        return []

    attached = network_container_map.get(node_id, [])
    if attached:
        return []

    fid = _finding_id("orphan-network", node_id, "")
    return [{
        "id": fid,
        "ruleId": "orphan-network",
        "severity": "low",
        "category": "maintenance",
        "target": {"kind": "network", "id": node_id, "label": label},
        "title": f"Orphan network: '{label}' has no attached containers",
        "description": (
            f"Network '{label}' exists but has no containers attached to it.  "
            "Orphan networks consume resources and clutter the Docker environment."
        ),
        "evidence": {"attachedContainerCount": 0},
        "recommendation": (
            "Remove the network if it is no longer needed: "
            "`docker network rm " + label + "`"
        ),
        "confidence": 0.85,
    }]


# ── Summary helpers ───────────────────────────────────────────────────────────

def _build_findings_summary(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate finding counts by severity and category."""
    by_severity: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "unknown")
        cat = f.get("category", "unknown")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "findings": len(findings),
        "bySeverity": by_severity,
        "byCategory": by_category,
    }


# ── Core engine ───────────────────────────────────────────────────────────────

def analyze_topology(
    topology: Any,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Analyse a topology and return a structured diagnostics report.

    Parameters
    ----------
    topology:
        A :class:`~docker_topology_live.models.Topology` instance **or** its
        ``dict`` representation (as returned by ``Topology.to_dict()``).
    metrics:
        Optional metrics document returned by ``build_sample_metrics()`` or
        ``collect_live_metrics()``.  Resource rules are skipped when *metrics*
        is ``None``.

    Returns
    -------
    dict
        Structured diagnostics report with schema version, findings list, and
        summary.
    """
    topo_dict = _coerce_topology(topology)
    nodes: List[Dict[str, Any]] = topo_dict.get("nodes") or []
    links: List[Dict[str, Any]] = topo_dict.get("links") or []
    is_sample: bool = bool(topo_dict.get("sample", False))
    source: Dict[str, Any] = dict(topo_dict.get("source") or {})

    containers = _containers(nodes)
    networks = _networks(nodes)

    # Pre-compute link maps
    container_link_map = _container_ids_with_links(links)
    network_container_map = _network_ids_with_containers(links)

    # Does any container in the environment have compose labels?
    any_container_has_compose = any(
        bool(
            (c.get("labels") or {}).get("com.docker.compose.project")
            or (c.get("labels") or {}).get("com.docker.compose.service")
        )
        for c in containers
    )

    # Build metrics lookup: container_id → metrics dict
    metrics_by_id: Dict[str, Dict[str, Any]] = {}
    if metrics:
        for cm in (metrics.get("containers") or []):
            cid = cm.get("id")
            if cid:
                metrics_by_id[cid] = cm

    findings: List[Dict[str, Any]] = []

    # ── Security rules ─────────────────────────────────────────────────────
    for c in containers:
        findings.extend(_rule_exposed_port(c))
        findings.extend(_rule_secret_label(c))
        findings.extend(_rule_broad_bind_mount(c))
        findings.extend(_rule_privileged_label(c))

    # ── Reliability rules ──────────────────────────────────────────────────
    for c in containers:
        findings.extend(_rule_exited_container(c))
        findings.extend(_rule_no_network(c, container_link_map))
        findings.extend(_rule_multi_network(c, container_link_map))

    # ── Resource rules (metrics required) ─────────────────────────────────
    if metrics_by_id:
        for c in containers:
            cid = c.get("id", "")
            label = c.get("label", cid)
            m = metrics_by_id.get(cid)
            if m is None:
                continue

            cpu = m.get("cpuPercent")
            if cpu is not None:
                result = _rule_high_cpu(cid, label, float(cpu))
                if result:
                    findings.append(result)

            mem_pct = m.get("memoryPercent")
            if mem_pct is not None:
                result = _rule_high_memory(cid, label, float(mem_pct))
                if result:
                    findings.append(result)

            pids = m.get("pids")
            if pids is not None:
                result = _rule_high_pids(cid, label, int(pids))
                if result:
                    findings.append(result)

            bw = m.get("blockWriteBytes")
            if bw is not None:
                result = _rule_high_block_write(cid, label, int(bw))
                if result:
                    findings.append(result)

    # ── Maintenance rules ──────────────────────────────────────────────────
    for c in containers:
        findings.extend(_rule_unnamed_container(c))
        findings.extend(_rule_missing_compose_labels(c, any_container_has_compose))

    for n in networks:
        findings.extend(_rule_orphan_network(n, network_container_map))

    # ── Assemble report ────────────────────────────────────────────────────
    generated_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "schemaVersion": _SCHEMA_VERSION,
        "generatedAt": generated_at,
        "source": source,
        "sample": is_sample,
        "summary": _build_findings_summary(findings),
        "findings": findings,
        "warnings": [],
    }


def build_sample_diagnostics() -> Dict[str, Any]:
    """Return a diagnostics report from sample data without contacting Docker.

    Internally calls :func:`~docker_topology_live.scanner.build_sample` and
    :func:`~docker_topology_live.metrics.build_sample_metrics`.  Neither
    function requires the *docker* package.
    """
    from .scanner import build_sample
    from .metrics import build_sample_metrics

    topology = build_sample()
    metrics = build_sample_metrics()
    return analyze_topology(topology, metrics)
