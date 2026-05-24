"""Tests for docker_topology_live.scanner (sample mode – no Docker required)."""
import json
import unittest

from docker_topology_live.scanner import _redact_labels, build_sample
from docker_topology_live.models import Topology


class TestBuildSample(unittest.TestCase):
    def setUp(self):
        self.topo = build_sample()

    def test_returns_topology(self):
        self.assertIsInstance(self.topo, Topology)

    def test_has_nodes(self):
        self.assertGreater(len(self.topo.nodes), 0)

    def test_has_links(self):
        self.assertGreater(len(self.topo.links), 0)

    def test_contains_containers(self):
        kinds = {n.kind for n in self.topo.nodes}
        self.assertIn("container", kinds)

    def test_contains_networks(self):
        kinds = {n.kind for n in self.topo.nodes}
        self.assertIn("network", kinds)

    def test_sample_flag_true(self):
        self.assertTrue(self.topo.sample)

    def test_summary_computed(self):
        self.assertIsNotNone(self.topo.summary)
        self.assertGreater(self.topo.summary.containers, 0)
        self.assertGreater(self.topo.summary.networks, 0)

    def test_links_reference_existing_nodes(self):
        node_ids = {n.id for n in self.topo.nodes}
        for link in self.topo.links:
            self.assertIn(link.source, node_ids,
                          f"Link source {link.source!r} not in nodes")
            self.assertIn(link.target, node_ids,
                          f"Link target {link.target!r} not in nodes")

    def test_serializable_to_json(self):
        raw = self.topo.to_json()
        data = json.loads(raw)
        self.assertIn("nodes", data)
        self.assertIn("links", data)
        self.assertEqual(data.get("schemaVersion"), "1.0")

    def test_node_ids_have_prefix(self):
        for node in self.topo.nodes:
            self.assertTrue(
                node.id.startswith("container:") or node.id.startswith("network:"),
                f"Node id {node.id!r} missing expected prefix"
            )

    def test_running_containers_present(self):
        running = [n for n in self.topo.nodes
                   if n.kind == "container" and n.status == "running"]
        self.assertGreater(len(running), 0)


class TestRedactLabels(unittest.TestCase):
    def test_password_redacted(self):
        labels = {"com.example.password": "hunter2"}
        result = _redact_labels(labels)
        self.assertEqual(result["com.example.password"], "***REDACTED***")

    def test_token_redacted(self):
        labels = {"app.token": "abc123"}
        result = _redact_labels(labels)
        self.assertEqual(result["app.token"], "***REDACTED***")

    def test_secret_redacted(self):
        labels = {"my.secret.key": "supersecret"}
        result = _redact_labels(labels)
        self.assertEqual(result["my.secret.key"], "***REDACTED***")

    def test_normal_label_preserved(self):
        labels = {"com.docker.compose.project": "myapp",
                  "com.docker.compose.service": "web"}
        result = _redact_labels(labels)
        self.assertEqual(result["com.docker.compose.project"], "myapp")
        self.assertEqual(result["com.docker.compose.service"], "web")

    def test_empty_dict(self):
        self.assertEqual(_redact_labels({}), {})

    def test_none_input(self):
        self.assertEqual(_redact_labels(None), {})

    def test_mixed_labels(self):
        labels = {
            "app.name": "myapp",
            "app.db.password": "secret123",
            "app.version": "1.0",
            "api.token": "tok_xyz",
        }
        result = _redact_labels(labels)
        self.assertEqual(result["app.name"], "myapp")
        self.assertEqual(result["app.version"], "1.0")
        self.assertEqual(result["app.db.password"], "***REDACTED***")
        self.assertEqual(result["api.token"], "***REDACTED***")
