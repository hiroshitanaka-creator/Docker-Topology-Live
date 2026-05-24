"""Data models for Docker Topology Live."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TopologyNode:
    """A node in the topology graph (container or network)."""

    id: str
    label: str
    kind: str  # 'container' or 'network'
    status: Optional[str] = None       # container only
    image: Optional[str] = None        # container only
    state: Optional[str] = None        # container only
    driver: Optional[str] = None       # network only
    scope: Optional[str] = None        # network only
    internal: Optional[bool] = None    # network only

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"id": self.id, "label": self.label, "kind": self.kind}
        if self.status is not None:
            d["status"] = self.status
        if self.image is not None:
            d["image"] = self.image
        if self.state is not None:
            d["state"] = self.state
        if self.driver is not None:
            d["driver"] = self.driver
        if self.scope is not None:
            d["scope"] = self.scope
        if self.internal is not None:
            d["internal"] = self.internal
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
