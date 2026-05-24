"""Statistics and summary computation for topology data."""
from __future__ import annotations

from .models import Topology, TopologySummary


def compute_summary(topology: Topology) -> TopologySummary:
    """Compute aggregated summary statistics from a topology."""
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}

    for node in topology.nodes:
        by_kind[node.kind] = by_kind.get(node.kind, 0) + 1
        if node.kind == "container" and node.status:
            by_status[node.status] = by_status.get(node.status, 0) + 1

    return TopologySummary(
        nodes=len(topology.nodes),
        links=len(topology.links),
        containers=by_kind.get("container", 0),
        running_containers=by_status.get("running", 0),
        networks=by_kind.get("network", 0),
        by_kind=by_kind,
        by_container_status=by_status,
    )
