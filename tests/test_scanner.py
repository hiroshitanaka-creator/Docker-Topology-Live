"""Tests for docker_topology_live.scanner (sample mode – no Docker required)."""
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

from docker_topology_live.models import Topology
from docker_topology_live.scanner import (
    _compose_fields,
    _parse_mounts,
    _parse_ports,
    _redact_labels,
    build_sample,
)


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


class TestParsePorts(unittest.TestCase):
    """Unit tests for _parse_ports() — no Docker daemon required."""

    def test_published_port(self):
        attrs = {
            "NetworkSettings": {
                "Ports": {
                    "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]
                }
            }
        }
        ports = _parse_ports(attrs)
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0].container_port, 80)
        self.assertEqual(ports[0].host_port, 8080)
        self.assertEqual(ports[0].protocol, "tcp")

    def test_unpublished_port(self):
        attrs = {
            "NetworkSettings": {
                "Ports": {"5432/tcp": None}
            }
        }
        ports = _parse_ports(attrs)
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0].container_port, 5432)
        self.assertIsNone(ports[0].host_port)

    def test_multiple_ports(self):
        attrs = {
            "NetworkSettings": {
                "Ports": {
                    "80/tcp":   [{"HostIp": "0.0.0.0", "HostPort": "8080"}],
                    "443/tcp":  [{"HostIp": "0.0.0.0", "HostPort": "8443"}],
                    "9000/udp": None,
                }
            }
        }
        ports = _parse_ports(attrs)
        self.assertEqual(len(ports), 3)
        protos = {p.protocol for p in ports}
        self.assertIn("tcp", protos)
        self.assertIn("udp", protos)

    def test_empty_network_settings(self):
        self.assertEqual(_parse_ports({}), [])
        self.assertEqual(_parse_ports({"NetworkSettings": {}}), [])

    def test_malformed_port_key_skipped(self):
        attrs = {
            "NetworkSettings": {
                "Ports": {"notaport": [{"HostIp": "0.0.0.0", "HostPort": "9999"}]}
            }
        }
        # Should not raise; malformed entries are skipped
        ports = _parse_ports(attrs)
        self.assertEqual(ports, [])


class TestParseMounts(unittest.TestCase):
    """Unit tests for _parse_mounts() — no Docker daemon required."""

    def test_volume_mount(self):
        attrs = {
            "Mounts": [
                {
                    "Type": "volume",
                    "Source": "pgdata",
                    "Destination": "/var/lib/postgresql/data",
                    "Mode": "z",
                    "RW": True,
                }
            ]
        }
        mounts = _parse_mounts(attrs)
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0].type, "volume")
        self.assertEqual(mounts[0].source, "pgdata")
        self.assertEqual(mounts[0].destination, "/var/lib/postgresql/data")
        self.assertTrue(mounts[0].rw)

    def test_bind_mount_read_only(self):
        attrs = {
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/host/config",
                    "Destination": "/etc/config",
                    "Mode": "ro",
                    "RW": False,
                }
            ]
        }
        mounts = _parse_mounts(attrs)
        self.assertEqual(len(mounts), 1)
        self.assertFalse(mounts[0].rw)
        self.assertEqual(mounts[0].mode, "ro")

    def test_empty_mounts(self):
        self.assertEqual(_parse_mounts({}), [])
        self.assertEqual(_parse_mounts({"Mounts": []}), [])


class TestComposeFields(unittest.TestCase):
    """Unit tests for _compose_fields() — no Docker daemon required."""

    def test_all_fields_present(self):
        labels = {
            "com.docker.compose.project": "myapp",
            "com.docker.compose.service": "web",
            "com.docker.compose.container-number": "2",
        }
        result = _compose_fields(labels)
        self.assertEqual(result["compose_project"], "myapp")
        self.assertEqual(result["compose_service"], "web")
        self.assertEqual(result["compose_container_number"], "2")

    def test_missing_compose_labels(self):
        result = _compose_fields({"unrelated": "value"})
        self.assertIsNone(result["compose_project"])
        self.assertIsNone(result["compose_service"])
        self.assertIsNone(result["compose_container_number"])


# ── Helpers to build mock Docker SDK objects ──────────────────────────────────

def _make_mock_container(
    cid="abc123abc123abc1",
    name="/mycontainer",
    status="running",
    image_tags=None,
    labels=None,
    state_status="running",
    ports=None,
    mounts=None,
    network_settings=None,
):
    """Return a MagicMock that mimics a docker.models.containers.Container."""
    container = MagicMock()
    container.id = cid
    container.name = name
    container.status = status

    img = MagicMock()
    img.tags = image_tags or ["nginx:latest"]
    container.image = img
    container.labels = labels or {}

    container.attrs = {
        "State": {"Status": state_status},
        "Config": {"Image": (image_tags or ["nginx:latest"])[0]},
        "NetworkSettings": {
            "Ports": ports or {},
            "Networks": network_settings or {},
        },
        "Mounts": mounts or [],
    }
    return container


def _make_mock_network(nid="net0net0net0", name="bridge"):
    net = MagicMock()
    net.id = nid
    net.name = name
    net.attrs = {
        "Driver": "bridge",
        "Scope": "local",
        "Internal": False,
    }
    return net


class TestScanLiveMocked(unittest.TestCase):
    """Integration-style tests for scan_live() using mock Docker SDK objects."""

    def _run_scan(self, containers, networks=None):
        """Patch docker.from_env and run scan_live(), returning the Topology."""
        mock_client = MagicMock()
        mock_client.networks.list.return_value = networks or []
        mock_client.containers.list.return_value = containers

        mock_docker = MagicMock()
        mock_docker.from_env.return_value = mock_client

        with patch.dict(sys.modules, {"docker": mock_docker}):
            from docker_topology_live.scanner import scan_live
            return scan_live()

    def test_basic_container_in_topology(self):
        container = _make_mock_container(cid="abc123abc123abc1", name="/web",
                                         status="running")
        topo = self._run_scan([container])
        container_nodes = [n for n in topo.nodes if n.kind == "container"]
        self.assertEqual(len(container_nodes), 1)
        self.assertEqual(container_nodes[0].label, "web")  # leading slash stripped
        self.assertEqual(container_nodes[0].status, "running")

    def test_ports_extracted(self):
        ports = {
            "80/tcp":   [{"HostIp": "0.0.0.0", "HostPort": "8080"}],
            "443/tcp":  [{"HostIp": "0.0.0.0", "HostPort": "8443"}],
        }
        container = _make_mock_container(ports=ports)
        topo = self._run_scan([container])
        node = next(n for n in topo.nodes if n.kind == "container")
        self.assertEqual(len(node.ports), 2)
        host_ports = {p.host_port for p in node.ports}
        self.assertIn(8080, host_ports)
        self.assertIn(8443, host_ports)

    def test_unpublished_port_has_no_host_port(self):
        ports = {"5432/tcp": None}
        container = _make_mock_container(ports=ports)
        topo = self._run_scan([container])
        node = next(n for n in topo.nodes if n.kind == "container")
        self.assertEqual(len(node.ports), 1)
        self.assertIsNone(node.ports[0].host_port)

    def test_mounts_extracted(self):
        mounts = [
            {
                "Type": "volume",
                "Source": "pgdata",
                "Destination": "/var/lib/postgresql/data",
                "Mode": "z",
                "RW": True,
            }
        ]
        container = _make_mock_container(mounts=mounts)
        topo = self._run_scan([container])
        node = next(n for n in topo.nodes if n.kind == "container")
        self.assertEqual(len(node.mounts), 1)
        self.assertEqual(node.mounts[0].destination, "/var/lib/postgresql/data")
        self.assertEqual(node.mounts[0].source, "pgdata")

    def test_compose_labels_extracted(self):
        labels = {
            "com.docker.compose.project": "myproject",
            "com.docker.compose.service": "api",
            "com.docker.compose.container-number": "1",
        }
        container = _make_mock_container(labels=labels)
        topo = self._run_scan([container])
        node = next(n for n in topo.nodes if n.kind == "container")
        self.assertEqual(node.compose_project, "myproject")
        self.assertEqual(node.compose_service, "api")
        self.assertEqual(node.compose_container_number, "1")

    def test_secret_labels_redacted(self):
        labels = {
            "app.name": "myapp",
            "app.db.password": "hunter2",
            "app.api.token": "tok_abc123",
            "com.docker.compose.project": "myproject",
        }
        container = _make_mock_container(labels=labels)
        topo = self._run_scan([container])
        node = next(n for n in topo.nodes if n.kind == "container")
        # Secret-like labels must be redacted
        self.assertEqual(node.labels["app.db.password"], "***REDACTED***")
        self.assertEqual(node.labels["app.api.token"], "***REDACTED***")
        # Safe labels must be preserved
        self.assertEqual(node.labels["app.name"], "myapp")
        self.assertEqual(node.labels["com.docker.compose.project"], "myproject")

    def test_secret_label_not_in_compose_project(self):
        """Compose project derived from a secret-labelled key is still fine
        because _compose_fields reads from the already-redacted dict."""
        labels = {
            "com.docker.compose.project": "safe_project",
            "db.password": "s3cr3t",
        }
        container = _make_mock_container(labels=labels)
        topo = self._run_scan([container])
        node = next(n for n in topo.nodes if n.kind == "container")
        # compose_project must be the real value (not redacted)
        self.assertEqual(node.compose_project, "safe_project")
        # The raw password label in node.labels must be redacted
        self.assertEqual(node.labels["db.password"], "***REDACTED***")

    def test_network_node_created(self):
        network = _make_mock_network(nid="net000net000", name="my_bridge")
        topo = self._run_scan([], networks=[network])
        net_nodes = [n for n in topo.nodes if n.kind == "network"]
        self.assertEqual(len(net_nodes), 1)
        self.assertEqual(net_nodes[0].label, "my_bridge")
        self.assertEqual(net_nodes[0].driver, "bridge")

    def test_container_linked_to_network(self):
        network = _make_mock_network(nid="abcdef000000", name="front")
        net_settings = {
            "front": {
                "NetworkID": "abcdef000000",
                "IPAddress": "172.20.0.5",
                "GlobalIPv6Address": "",
            }
        }
        container = _make_mock_container(network_settings=net_settings)
        topo = self._run_scan([container], networks=[network])
        # There must be a link from the container to the network
        container_id = next(n.id for n in topo.nodes if n.kind == "container")
        network_id   = next(n.id for n in topo.nodes if n.kind == "network")
        links = [(l.source, l.target) for l in topo.links]
        self.assertIn((container_id, network_id), links)

    def test_live_topology_sample_flag_false(self):
        topo = self._run_scan([])
        self.assertFalse(topo.sample)

    def test_serialisable_to_json(self):
        ports = {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}
        mounts = [{"Type": "volume", "Source": "vol", "Destination": "/data",
                   "Mode": "", "RW": True}]
        labels = {"app.name": "test", "app.password": "secret"}
        container = _make_mock_container(ports=ports, mounts=mounts, labels=labels)
        topo = self._run_scan([container])
        raw = topo.to_json()
        data = json.loads(raw)
        self.assertIn("nodes", data)
        self.assertIn("links", data)


class TestSampleDataRichness(unittest.TestCase):
    """Verify that build_sample() returns the richer metadata fields."""

    def setUp(self):
        self.topo = build_sample()

    def test_some_containers_have_ports(self):
        containers_with_ports = [
            n for n in self.topo.nodes
            if n.kind == "container" and n.ports
        ]
        self.assertGreater(len(containers_with_ports), 0)

    def test_some_containers_have_mounts(self):
        containers_with_mounts = [
            n for n in self.topo.nodes
            if n.kind == "container" and n.mounts
        ]
        self.assertGreater(len(containers_with_mounts), 0)

    def test_containers_have_compose_project(self):
        containers = [n for n in self.topo.nodes if n.kind == "container"]
        for c in containers:
            self.assertIsNotNone(c.compose_project,
                                 f"{c.label} missing compose_project")

    def test_containers_have_labels(self):
        containers = [n for n in self.topo.nodes if n.kind == "container"]
        for c in containers:
            self.assertGreater(len(c.labels), 0,
                               f"{c.label} has no labels")

    def test_exited_container_present(self):
        exited = [n for n in self.topo.nodes
                  if n.kind == "container" and n.status == "exited"]
        self.assertGreater(len(exited), 0)
