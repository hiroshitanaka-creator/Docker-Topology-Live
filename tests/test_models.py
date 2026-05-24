"""Tests for docker_topology_live.models."""
import json
import unittest

from docker_topology_live.models import (
    Topology,
    TopologyLink,
    TopologyNode,
    TopologySummary,
)


class TestTopologyNode(unittest.TestCase):
    def test_container_to_dict(self):
        n = TopologyNode(
            id="container:abc123",
            label="web",
            kind="container",
            status="running",
            image="nginx:latest",
        )
        d = n.to_dict()
        self.assertEqual(d["id"], "container:abc123")
        self.assertEqual(d["label"], "web")
        self.assertEqual(d["kind"], "container")
        self.assertEqual(d["status"], "running")
        self.assertEqual(d["image"], "nginx:latest")
        self.assertNotIn("driver", d)
        self.assertNotIn("scope", d)

    def test_network_to_dict(self):
        n = TopologyNode(
            id="network:xyz",
            label="frontend",
            kind="network",
            driver="bridge",
            scope="local",
            internal=False,
        )
        d = n.to_dict()
        self.assertEqual(d["driver"], "bridge")
        self.assertEqual(d["scope"], "local")
        self.assertFalse(d["internal"])
        self.assertNotIn("status", d)
        self.assertNotIn("image", d)

    def test_none_fields_excluded(self):
        n = TopologyNode(id="container:abc", label="web", kind="container")
        d = n.to_dict()
        self.assertNotIn("status", d)
        self.assertNotIn("image", d)
        self.assertNotIn("driver", d)
        self.assertNotIn("scope", d)

    def test_internal_false_included(self):
        n = TopologyNode(id="network:x", label="n", kind="network", internal=False)
        d = n.to_dict()
        self.assertIn("internal", d)
        self.assertFalse(d["internal"])


class TestTopologyLink(unittest.TestCase):
    def test_to_dict(self):
        lnk = TopologyLink("container:a", "network:b", "attached-to", "10.0.0.2")
        d = lnk.to_dict()
        self.assertEqual(d["source"], "container:a")
        self.assertEqual(d["target"], "network:b")
        self.assertEqual(d["kind"], "attached-to")
        self.assertEqual(d["label"], "10.0.0.2")

    def test_defaults(self):
        lnk = TopologyLink("container:a", "network:b")
        d = lnk.to_dict()
        self.assertEqual(d["kind"], "attached-to")
        self.assertEqual(d["label"], "")


class TestTopologySummary(unittest.TestCase):
    def test_to_dict_keys(self):
        s = TopologySummary(
            nodes=5,
            links=4,
            containers=3,
            running_containers=2,
            networks=2,
            by_kind={"container": 3, "network": 2},
            by_container_status={"running": 2, "exited": 1},
        )
        d = s.to_dict()
        self.assertEqual(d["nodes"], 5)
        self.assertEqual(d["links"], 4)
        self.assertEqual(d["containers"], 3)
        self.assertEqual(d["runningContainers"], 2)
        self.assertEqual(d["networks"], 2)
        self.assertIn("byKind", d)
        self.assertIn("byContainerStatus", d)


class TestTopology(unittest.TestCase):
    def test_to_json_roundtrip(self):
        topo = Topology(
            schema_version="1.0",
            generated_at="2024-01-01T00:00:00Z",
            nodes=[
                TopologyNode("container:abc", "web", "container", status="running")
            ],
            links=[],
        )
        raw = topo.to_json()
        data = json.loads(raw)
        self.assertEqual(data["schemaVersion"], "1.0")
        self.assertEqual(len(data["nodes"]), 1)
        self.assertEqual(data["nodes"][0]["label"], "web")

    def test_to_dict_required_keys(self):
        topo = Topology()
        d = topo.to_dict()
        for key in ("schemaVersion", "generatedAt", "source", "nodes", "links",
                    "summary", "warnings", "sample"):
            self.assertIn(key, d, f"Missing key: {key}")

    def test_nodes_and_links_empty_by_default(self):
        topo = Topology()
        d = topo.to_dict()
        self.assertEqual(d["nodes"], [])
        self.assertEqual(d["links"], [])

    def test_sample_false_by_default(self):
        topo = Topology()
        self.assertFalse(topo.sample)
