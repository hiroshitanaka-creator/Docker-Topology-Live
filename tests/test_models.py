"""Tests for docker_topology_live.models."""
import json
import unittest

from docker_topology_live.models import (
    MountInfo,
    PortMapping,
    Topology,
    TopologyLink,
    TopologyNode,
    TopologySummary,
)


class TestPortMapping(unittest.TestCase):
    def test_to_dict_with_host_port(self):
        p = PortMapping(container_port=80, host_port=8080, protocol="tcp")
        d = p.to_dict()
        self.assertEqual(d["containerPort"], 80)
        self.assertEqual(d["hostPort"], 8080)
        self.assertEqual(d["protocol"], "tcp")

    def test_to_dict_without_host_port(self):
        p = PortMapping(container_port=5432, host_port=None, protocol="tcp")
        d = p.to_dict()
        self.assertEqual(d["containerPort"], 5432)
        self.assertNotIn("hostPort", d)

    def test_default_protocol_tcp(self):
        p = PortMapping(container_port=80, host_port=None)
        self.assertEqual(p.protocol, "tcp")

    def test_udp_protocol(self):
        p = PortMapping(container_port=53, host_port=53, protocol="udp")
        d = p.to_dict()
        self.assertEqual(d["protocol"], "udp")


class TestMountInfo(unittest.TestCase):
    def test_to_dict_volume_with_source(self):
        m = MountInfo(type="volume", destination="/data", source="myvolume",
                      mode="z", rw=True)
        d = m.to_dict()
        self.assertEqual(d["type"], "volume")
        self.assertEqual(d["destination"], "/data")
        self.assertEqual(d["source"], "myvolume")
        self.assertEqual(d["mode"], "z")
        self.assertTrue(d["rw"])

    def test_to_dict_source_omitted_when_empty(self):
        m = MountInfo(type="tmpfs", destination="/tmp", source="")
        d = m.to_dict()
        self.assertNotIn("source", d)

    def test_read_only_mount(self):
        m = MountInfo(type="bind", destination="/etc/config", source="/host/config",
                      mode="ro", rw=False)
        d = m.to_dict()
        self.assertFalse(d["rw"])

    def test_default_rw_true(self):
        m = MountInfo(type="volume", destination="/data")
        self.assertTrue(m.rw)


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

    def test_ports_serialised(self):
        n = TopologyNode(
            id="container:abc", label="web", kind="container",
            ports=[PortMapping(80, 8080, "tcp"), PortMapping(443, None, "tcp")],
        )
        d = n.to_dict()
        self.assertIn("ports", d)
        self.assertEqual(len(d["ports"]), 2)
        self.assertEqual(d["ports"][0]["containerPort"], 80)
        self.assertEqual(d["ports"][0]["hostPort"], 8080)
        self.assertNotIn("hostPort", d["ports"][1])

    def test_mounts_serialised(self):
        n = TopologyNode(
            id="container:abc", label="db", kind="container",
            mounts=[MountInfo(type="volume", destination="/data", source="pgdata",
                              mode="z", rw=True)],
        )
        d = n.to_dict()
        self.assertIn("mounts", d)
        self.assertEqual(d["mounts"][0]["destination"], "/data")
        self.assertEqual(d["mounts"][0]["source"], "pgdata")

    def test_labels_serialised(self):
        n = TopologyNode(
            id="container:abc", label="web", kind="container",
            labels={"com.docker.compose.project": "demo",
                    "com.docker.compose.service": "web"},
        )
        d = n.to_dict()
        self.assertIn("labels", d)
        self.assertEqual(d["labels"]["com.docker.compose.project"], "demo")

    def test_empty_ports_omitted(self):
        n = TopologyNode(id="container:abc", label="web", kind="container")
        d = n.to_dict()
        self.assertNotIn("ports", d)

    def test_empty_mounts_omitted(self):
        n = TopologyNode(id="container:abc", label="web", kind="container")
        d = n.to_dict()
        self.assertNotIn("mounts", d)

    def test_empty_labels_omitted(self):
        n = TopologyNode(id="container:abc", label="web", kind="container")
        d = n.to_dict()
        self.assertNotIn("labels", d)

    def test_compose_fields_serialised(self):
        n = TopologyNode(
            id="container:abc", label="web", kind="container",
            compose_project="demo", compose_service="web",
            compose_container_number="1",
        )
        d = n.to_dict()
        self.assertEqual(d["compose_project"], "demo")
        self.assertEqual(d["compose_service"], "web")
        self.assertEqual(d["compose_container_number"], "1")

    def test_network_node_no_ports_mounts_labels(self):
        n = TopologyNode(id="network:abc", label="net", kind="network",
                         driver="bridge", scope="local", internal=False)
        d = n.to_dict()
        self.assertNotIn("ports", d)
        self.assertNotIn("mounts", d)
        self.assertNotIn("labels", d)


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
