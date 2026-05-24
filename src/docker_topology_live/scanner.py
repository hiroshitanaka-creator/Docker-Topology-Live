"""Docker topology scanner with sample-mode fallback.

No destructive Docker operations are performed (no stop/remove/prune).
Secret-like label values are redacted before inclusion in the topology.
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

from .models import Topology, TopologyLink, TopologyNode
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


def _redact_labels(labels: dict) -> dict:
    """Return *labels* copy with secret-like values replaced by a redaction marker."""
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


def scan_live() -> Topology:
    """Connect to the Docker daemon and return the current topology.

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
    net_id_map: dict[str, str] = {}  # full_id -> short_id
    net_name_map: dict[str, str] = {}  # name -> node_id

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
        name = str(getattr(container, "name", None) or attrs.get("Name", "container")).lstrip("/")
        status = str(getattr(container, "status", None) or (attrs.get("State") or {}).get("Status", "unknown"))
        state = (attrs.get("State") or {}).get("Status", "")
        image_obj = getattr(container, "image", None)
        tags = getattr(image_obj, "tags", []) or []
        image = tags[0] if tags else ((attrs.get("Config") or {}).get("Image") or "unknown")

        node_id = f"container:{_short(full_id)}"
        nodes.append(
            TopologyNode(
                id=node_id,
                label=name,
                kind="container",
                status=status,
                state=state,
                image=str(image),
            )
        )

        raw_nets = ((attrs.get("NetworkSettings") or {}).get("Networks") or {})
        for net_name, ep in raw_nets.items():
            ep = ep or {}
            full_net_id = ep.get("NetworkID", "")
            target = net_id_map.get(full_net_id) or net_name_map.get(net_name) or f"network:{_short(full_net_id or net_name)}"
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


def build_sample() -> Topology:
    """Return a representative sample topology without contacting Docker."""
    nodes = [
        TopologyNode(id="network:aaa000aaa000", label="demo_frontend", kind="network",
                     driver="bridge", scope="local", internal=False),
        TopologyNode(id="network:bbb111bbb111", label="demo_backend", kind="network",
                     driver="bridge", scope="local", internal=True),
        TopologyNode(id="container:abc123abc123", label="web", kind="container",
                     status="running", state="running", image="nginx:latest"),
        TopologyNode(id="container:def456def456", label="api", kind="container",
                     status="running", state="running", image="myapp/api:1.0"),
        TopologyNode(id="container:ghi789ghi789", label="db", kind="container",
                     status="running", state="running", image="postgres:15"),
        TopologyNode(id="container:jkl012jkl012", label="cache", kind="container",
                     status="running", state="running", image="redis:7-alpine"),
        TopologyNode(id="container:mno345mno345", label="worker-crashed", kind="container",
                     status="exited", state="exited", image="myapp/worker:1.0"),
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
