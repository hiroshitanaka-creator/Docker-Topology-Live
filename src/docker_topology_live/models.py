"""Data models for Docker Topology Live."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PortMapping:
    """A single port mapping exposed by a container."""

    container_port: int
    host_port: Optional[int]       # None when not bound to the host
    protocol: str = "tcp"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "containerPort": self.container_port,
            "protocol": self.protocol,
        }
        if self.host_port is not None:
            d["hostPort"] = self.host_port
        return d


@dataclass
class MountInfo:
    """A single mount attached to a container.

    Sensitive host paths are included as-is; callers may strip them if
    desired.  ``source`` is omitted from serialisation when empty so that
    anonymous volumes do not produce a misleading empty string.
    """

    type: str        # "bind", "volume", "tmpfs", …
    destination: str
    mode: str = ""
    rw: bool = True
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": self.type,
            "destination": self.destination,
            "mode": self.mode,
            "rw": self.rw,
        }
        if self.source:
            d["source"] = self.source
        return d


@dataclass
class TopologyNode:
    """A node in the topology graph (container or network)."""

    id: str
    label: str
    kind: str  # 'container' or 'network'

    # ── Container fields ────────────────────────────────────────────────────
    status: Optional[str] = None
    image: Optional[str] = None
    state: Optional[str] = None
    ports: List[PortMapping] = field(default_factory=list)
    mounts: List[MountInfo] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)

    # Docker Compose convenience fields (derived from labels)
    compose_project: Optional[str] = None
    compose_service: Optional[str] = None
    compose_container_number: Optional[str] = None

    # ── Network fields ───────────────────────────────────────────────────────
    driver: Optional[str] = None
    scope: Optional[str] = None
    internal: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"id": self.id, "label": self.label, "kind": self.kind}

        # Shared optional scalars
        for attr in ("status", "image", "state", "driver", "scope"):
            val = getattr(self, attr)
            if val is not None:
                d[attr] = val
        if self.internal is not None:
            d["internal"] = self.internal

        # Container-only collections
        if self.kind == "container":
            if self.ports:
                d["ports"] = [p.to_dict() for p in self.ports]
            if self.mounts:
                d["mounts"] = [m.to_dict() for m in self.mounts]
            if self.labels:
                d["labels"] = dict(self.labels)
            # Compose metadata
            for attr in ("compose_project", "compose_service", "compose_container_number"):
                val = getattr(self, attr)
                if val is not None:
                    d[attr] = val

        return d


@dataclass
class TopologyLink:
    """A directed link between two nodes."""

    source: str
    target: str
    kind: str = "attached-to"
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TopologySummary:
    """Aggregated statistics about a topology."""

    nodes: int = 0
    links: int = 0
    containers: int = 0
    running_containers: int = 0
    networks: int = 0
    by_kind: Dict[str, int] = field(default_factory=dict)
    by_container_status: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": self.nodes,
            "links": self.links,
            "containers": self.containers,
            "runningContainers": self.running_containers,
            "networks": self.networks,
            "byKind": self.by_kind,
            "byContainerStatus": self.by_container_status,
        }


@dataclass
class Topology:
    """Full topology document."""

    schema_version: str = "1.0"
    generated_at: str = ""
    source: Dict[str, str] = field(default_factory=lambda: {"engine": "docker", "host": "local"})
    nodes: List[TopologyNode] = field(default_factory=list)
    links: List[TopologyLink] = field(default_factory=list)
    summary: Optional[TopologySummary] = None
    warnings: List[str] = field(default_factory=list)
    sample: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "generatedAt": self.generated_at,
            "source": dict(self.source),
            "nodes": [n.to_dict() for n in self.nodes],
            "links": [l.to_dict() for l in self.links],
            "summary": self.summary.to_dict() if self.summary else {},
            "warnings": list(self.warnings),
            "sample": self.sample,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
