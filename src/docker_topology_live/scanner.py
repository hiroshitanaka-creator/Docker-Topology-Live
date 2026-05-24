"""Docker topology scanner with sample-mode fallback.

No destructive Docker operations are performed (no stop/remove/prune).
Secret-like label values are redacted before any data enters the topology.
"""
from __future__ import annotations

import datetime
import logging
from typing import List, Optional

from .models import (
    MountInfo,
    PortMapping,
    Topology,
    TopologyLink,
    TopologyNode,
)
from .stats import compute_summary

logger = logging.getLogger(__name__)

# Label key substrings that trigger value redaction
_SECRET_FRAGMENTS = frozenset(
    {
        "password", "passwd", "secret", "token", "apikey", "api_key",
        "credential", "auth", "private_key", "privatekey", "access_key",
        "access_secret",
    }
)


def _redact_labels(labels: Optional[dict]) -> dict:
    """Return a copy of *labels* with secret-like values replaced by a marker.

    Keys whose lower-cased text contains any fragment from ``_SECRET_FRAGMENTS``
    have their values replaced with ``"***REDACTED***"``.
    """
    out: dict = {}
    for k, v in (labels or {}).items():
        if any(frag in k.lower() for frag in _SECRET_FRAGMENTS):
            out[k] = "***REDACTED***"
        else:
            out[k] = v
    return out


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _short(raw_id: str, length: int = 12) -> str:
    return (raw_id or "")[:length]


def _parse_ports(attrs: dict) -> List[PortMapping]:
    """Extract port mappings from container attrs.

    Reads ``NetworkSettings.Ports`` which has the form::

        {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}], "443/tcp": null}
    """
    ports: List[PortMapping] = []
    raw = (attrs.get("NetworkSettings") or {}).get("Ports") or {}
    for port_proto, bindings in raw.items():
        try:
            port_str, proto = port_proto.split("/", 1)
            cport = int(port_str)
        except (ValueError, AttributeError):
            continue
        if bindings:
            for b in bindings:
                hport_str = (b or {}).get("HostPort", "")
                hport = int(hport_str) if hport_str else None
                hip = (b or {}).get("HostIp") or None
                ports.append(PortMapping(container_port=cport, host_port=hport, protocol=proto, host_ip=hip))
        else:
            # Port exposed but not published to the host
            ports.append(PortMapping(container_port=cport, host_port=None, protocol=proto))
    return ports


def _categorize_mount_source(source: str) -> str:
    """Return a safe category label for a bind mount source path.

    The category describes the *class* of host path without exposing the
    literal value.  Categories are used by the diagnostics engine so that
    sensitivity rules still fire even when the raw path is redacted.

    Returns
    -------
    str
        One of:

        ``"docker-socket"``
            The Docker daemon socket ``/var/run/docker.sock``.
        ``"root"``
            Exactly ``/`` — the entire host root filesystem.
        ``"system"``
            A sensitive system path (``/etc``, ``/proc``, ``/sys``,
            ``/var/run``, ``/root``).
        ``"home"``
            A user home directory (``/home/*`` or ``/Users/*``).
        ``"absolute-path"``
            Any other absolute host path.
        ``"named-volume"``
            A Docker named-volume source (non-path string).
        ``"unknown"``
            Empty or unrecognised source.
    """
    if not source:
        return "unknown"
    if source == "/var/run/docker.sock":
        return "docker-socket"
    if source == "/":
        return "root"
    _SYSTEM_PREFIXES = ("/etc", "/proc", "/sys", "/var/run", "/root")
    if any(source.startswith(p) for p in _SYSTEM_PREFIXES):
        return "system"
    if source.startswith("/home") or source.startswith("/Users"):
        return "home"
    if source.startswith("/"):
        return "absolute-path"
    # Non-path: Docker named volume or relative-path volume
    return "named-volume"


def _parse_mounts(attrs: dict, redact_host_paths: bool = False) -> List[MountInfo]:
    """Extract mount information from container attrs.

    Only ``Type``, ``Source``, ``Destination``, ``Mode``, and ``RW`` are read.
    When *redact_host_paths* is ``True``, the ``source`` of every bind mount
    is replaced with the literal string ``"[redacted]"`` and
    ``source_redacted`` is set to ``True``.  The ``source_category`` field is
    always populated for bind mounts so that diagnostics can reason about
    sensitivity without the raw path.
    """
    mounts: List[MountInfo] = []
    for m in attrs.get("Mounts") or []:
        mtype = str(m.get("Type", "volume"))
        source = str(m.get("Source", ""))
        dest = str(m.get("Destination", ""))
        mode = str(m.get("Mode", ""))
        rw = bool(m.get("RW", True))

        category: Optional[str] = None
        source_redacted = False
        if mtype == "bind":
            category = _categorize_mount_source(source)
            if redact_host_paths:
                source = "[redacted]"
                source_redacted = True

        mounts.append(MountInfo(
            type=mtype,
            destination=dest,
            mode=mode,
            rw=rw,
            source=source,
            source_redacted=source_redacted,
            source_category=category,
        ))
    return mounts


def _compose_fields(labels: dict) -> dict:
    """Extract Docker Compose metadata from a redacted labels dict."""
    return {
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
        "compose_container_number": labels.get("com.docker.compose.container-number"),
    }


def scan_live(redact_host_paths: bool = False) -> Topology:
    """Connect to the Docker daemon and return the current topology.

    Parameters
    ----------
    redact_host_paths:
        When ``True``, bind mount source paths are replaced with
        ``"[redacted]"`` in the topology document.  The ``sourceCategory``
        field is always included for bind mounts so diagnostics can still
        assess sensitivity without the raw path.  Off by default.

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
            "The 'docker' package is required for live scanning. "
            "Install it with:  pip install docker"
        ) from exc

    client = docker.from_env()
    nodes: list[TopologyNode] = []
    links: list[TopologyLink] = []
    net_id_map: dict[str, str] = {}   # full_id -> node_id
    net_name_map: dict[str, str] = {} # name   -> node_id

    for net in client.networks.list():
        attrs = net.attrs or {}
        full_id = str(getattr(net, "id", None) or attrs.get("Id", ""))
        name = str(getattr(net, "name", None) or attrs.get("Name", "network"))
        short_id = _short(full_id)
        node_id = f"network:{short_id}"
        net_id_map[full_id] = node_id
        net_name_map[name] = node_id
        nodes.append(
            TopologyNode(
                id=node_id,
                label=name,
                kind="network",
                driver=attrs.get("Driver", "unknown"),
                scope=attrs.get("Scope", "local"),
                internal=bool(attrs.get("Internal", False)),
            )
        )

    for container in client.containers.list(all=True):
        attrs = container.attrs or {}
        full_id = str(getattr(container, "id", None) or attrs.get("Id", ""))
        name = str(
            getattr(container, "name", None) or attrs.get("Name", "container")
        ).lstrip("/")
        status = str(
            getattr(container, "status", None)
            or (attrs.get("State") or {}).get("Status", "unknown")
        )
        state = (attrs.get("State") or {}).get("Status", "")

        image_obj = getattr(container, "image", None)
        tags = getattr(image_obj, "tags", []) or []
        image = tags[0] if tags else ((attrs.get("Config") or {}).get("Image") or "unknown")

        # Redact labels before they enter any data structure
        raw_labels = dict(getattr(container, "labels", None) or {})
        labels = _redact_labels(raw_labels)
        compose = _compose_fields(labels)

        node_id = f"container:{_short(full_id)}"
        nodes.append(
            TopologyNode(
                id=node_id,
                label=name,
                kind="container",
                status=status,
                state=state,
                image=str(image),
                ports=_parse_ports(attrs),
                mounts=_parse_mounts(attrs, redact_host_paths=redact_host_paths),
                labels=labels,
                compose_project=compose["compose_project"],
                compose_service=compose["compose_service"],
                compose_container_number=compose["compose_container_number"],
            )
        )

        raw_nets = ((attrs.get("NetworkSettings") or {}).get("Networks") or {})
        for net_name, ep in raw_nets.items():
            ep = ep or {}
            full_net_id = ep.get("NetworkID", "")
            target = (
                net_id_map.get(full_net_id)
                or net_name_map.get(net_name)
                or f"network:{_short(full_net_id or net_name)}"
            )
            ip = ep.get("IPAddress") or ep.get("GlobalIPv6Address") or ""
            links.append(TopologyLink(source=node_id, target=target, kind="attached-to", label=ip))

    topo = Topology(
        schema_version="1.0",
        generated_at=_now_iso(),
        source={"engine": "docker", "host": "local"},
        nodes=nodes,
        links=links,
        warnings=[],
        sample=False,
    )
    topo.summary = compute_summary(topo)
    return topo


def build_sample(redact_host_paths: bool = False) -> Topology:
    """Return a representative sample topology without contacting Docker.

    Parameters
    ----------
    redact_host_paths:
        When ``True``, bind mount source paths in the sample topology are
        replaced with ``"[redacted]"``.  Off by default.
    """
    # Bind mount used by the api container: /etc/ssl/certs → category "system"
    _api_bind_source = "/etc/ssl/certs"
    _api_bind_category = _categorize_mount_source(_api_bind_source)
    _api_bind_redacted = redact_host_paths
    _api_bind_displayed = "[redacted]" if redact_host_paths else _api_bind_source

    nodes = [
        TopologyNode(
            id="network:aaa000aaa000", label="demo_frontend", kind="network",
            driver="bridge", scope="local", internal=False,
        ),
        TopologyNode(
            id="network:bbb111bbb111", label="demo_backend", kind="network",
            driver="bridge", scope="local", internal=True,
        ),
        TopologyNode(
            id="container:abc123abc123", label="web", kind="container",
            status="running", state="running", image="nginx:latest",
            ports=[PortMapping(80, 8080, "tcp", "0.0.0.0"), PortMapping(443, 8443, "tcp", "0.0.0.0")],
            labels={
                "com.docker.compose.project": "demo",
                "com.docker.compose.service": "web",
                "com.docker.compose.container-number": "1",
                "app.api_key": "***REDACTED***",
            },
            compose_project="demo", compose_service="web", compose_container_number="1",
        ),
        TopologyNode(
            id="container:def456def456", label="api", kind="container",
            status="running", state="running", image="myapp/api:1.0",
            ports=[PortMapping(3000, 3000, "tcp", "127.0.0.1")],
            mounts=[MountInfo(
                type="bind", destination="/app/certs", mode="ro", rw=False,
                source=_api_bind_displayed,
                source_redacted=_api_bind_redacted,
                source_category=_api_bind_category,
            )],
            labels={
                "com.docker.compose.project": "demo",
                "com.docker.compose.service": "api",
                "com.docker.compose.container-number": "1",
            },
            compose_project="demo", compose_service="api", compose_container_number="1",
        ),
        TopologyNode(
            id="container:ghi789ghi789", label="db", kind="container",
            status="running", state="running", image="postgres:15",
            ports=[PortMapping(5432, None, "tcp")],
            mounts=[MountInfo(type="volume", destination="/var/lib/postgresql/data",
                              mode="z", rw=True, source="demo_pgdata")],
            labels={
                "com.docker.compose.project": "demo",
                "com.docker.compose.service": "db",
                "com.docker.compose.container-number": "1",
            },
            compose_project="demo", compose_service="db", compose_container_number="1",
        ),
        TopologyNode(
            id="container:jkl012jkl012", label="cache", kind="container",
            status="running", state="running", image="redis:7-alpine",
            labels={
                "com.docker.compose.project": "demo",
                "com.docker.compose.service": "cache",
                "com.docker.compose.container-number": "1",
            },
            compose_project="demo", compose_service="cache", compose_container_number="1",
        ),
        TopologyNode(
            id="container:mno345mno345", label="worker-crashed", kind="container",
            status="exited", state="exited", image="myapp/worker:1.0",
            labels={
                "com.docker.compose.project": "demo",
                "com.docker.compose.service": "worker",
                "com.docker.compose.container-number": "1",
            },
            compose_project="demo", compose_service="worker", compose_container_number="1",
        ),
    ]

    links = [
        TopologyLink("container:abc123abc123", "network:aaa000aaa000", "attached-to", "172.20.0.2"),
        TopologyLink("container:def456def456", "network:aaa000aaa000", "attached-to", "172.20.0.3"),
        TopologyLink("container:def456def456", "network:bbb111bbb111", "attached-to", "172.21.0.2"),
        TopologyLink("container:ghi789ghi789", "network:bbb111bbb111", "attached-to", "172.21.0.3"),
        TopologyLink("container:jkl012jkl012", "network:bbb111bbb111", "attached-to", "172.21.0.4"),
        TopologyLink("container:mno345mno345", "network:bbb111bbb111", "attached-to", ""),
    ]

    topo = Topology(
        schema_version="1.0",
        generated_at="2024-01-15T12:00:00Z",
        source={"engine": "sample", "host": "demo"},
        nodes=nodes,
        links=links,
        warnings=[],
        sample=True,
    )
    topo.summary = compute_summary(topo)
    return topo
