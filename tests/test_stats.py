"""Tests for docker_topology_live.stats."""
import unittest

from docker_topology_live.models import Topology, TopologyLink, TopologyNode
from docker_topology_live.stats import compute_summary


def _make_topology() -> Topology:
    nodes = [
        TopologyNode("network:n1", "front", "network", driver="bridge"),
        TopologyNode("network:n2", "back",  "network", driver="bridge"),
        TopologyNode("container:c1", "web",  "container", status="running"),
        TopologyNode("container:c2", "api",  "container", status="running"),
        TopologyNode("container:c3", "db",   "container", status="exited"),
    ]
    links = [
        TopologyLink("container:c1", "network:n1"),
        TopologyLink("container:c2", "network:n1"),
        TopologyLink("container:c2", "network:n2"),
        TopologyLink("container:c3", "network:n2"),
    ]
    return Topology(nodes=nodes, links=links)


class TestComputeSummary(unittest.TestCase):
    def setUp(self):
        self.summary = compute_summary(_make_topology())

    def test_node_count(self):
        self.assertEqual(self.summary.nodes, 5)

    def test_link_count(self):
        self.assertEqual(self.summary.links, 4)

    def test_container_count(self):
        self.assertEqual(self.summary.containers, 3)

    def test_network_count(self):
        self.assertEqual(self.summary.networks, 2)

    def test_running_containers(self):
        self.assertEqual(self.summary.running_containers, 2)

    def test_by_kind(self):
        self.assertEqual(self.summary.by_kind.get("container"), 3)
        self.assertEqual(self.summary.by_kind.get("network"), 2)

    def test_by_container_status(self):
        self.assertEqual(self.summary.by_container_status.get("running"), 2)
        self.assertEqual(self.summary.by_container_status.get("exited"), 1)

    def test_to_dict_keys(self):
        d = self.summary.to_dict()
        for k in ("nodes", "links", "containers", "runningContainers",
                  "networks", "byKind", "byContainerStatus"):
            self.assertIn(k, d, f"Missing key in summary dict: {k}")

    def test_empty_topology(self):
        s = compute_summary(Topology())
        self.assertEqual(s.nodes, 0)
        self.assertEqual(s.containers, 0)
        self.assertEqual(s.networks, 0)
        self.assertEqual(s.running_containers, 0)
