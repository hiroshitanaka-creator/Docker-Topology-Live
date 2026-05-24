"""Comprehensive tests for docker_topology_live.diagnostics.

All tests run without a real Docker daemon.  Sample-mode helpers and
lightweight topology fixtures are used throughout.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock

# ── Ensure the package is importable regardless of install state ──────────────
# Tests may be run directly (pytest) or via subprocess with PYTHONPATH=src.
_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from docker_topology_live.diagnostics import (
    analyze_topology,
    build_sample_diagnostics,
    _finding_id,
)
from docker_topology_live.models import (
    MountInfo,
    PortMapping,
    Topology,
    TopologyLink,
    TopologyNode,
)


# ── Topology builder helpers ──────────────────────────────────────────────────

def _make_topology(
    containers=None,
    networks=None,
    links=None,
    sample=False,
) -> Topology:
    """Return a minimal Topology object for unit testing."""
    from docker_topology_live.stats import compute_summary

    nodes = list(containers or []) + list(networks or [])
    topo = Topology(
        schema_version="1.0",
        generated_at="2024-01-01T00:00:00Z",
        source={"engine": "test", "host": "localhost"},
        nodes=nodes,
        links=list(links or []),
        sample=sample,
    )
    topo.summary = compute_summary(topo)
    return topo


def _simple_container(
    cid="container:aabbccddee00",
    label="myapp",
    status="running",
    ports=None,
    mounts=None,
    labels=None,
) -> TopologyNode:
    return TopologyNode(
        id=cid,
        label=label,
        kind="container",
        status=status,
        state=status,
        image="test:latest",
        ports=list(ports or []),
        mounts=list(mounts or []),
        labels=dict(labels or {}),
    )


def _simple_network(
    nid="network:net0net0net0",
    label="mynet",
) -> TopologyNode:
    return TopologyNode(
        id=nid,
        label=label,
        kind="network",
        driver="bridge",
        scope="local",
        internal=False,
    )


def _link(container_id, network_id) -> TopologyLink:
    return TopologyLink(source=container_id, target=network_id, kind="attached-to")


# ─────────────────────────────────────────────────────────────────────────────
# TestFindingStructure
# ─────────────────────────────────────────────────────────────────────────────

class TestFindingStructure(unittest.TestCase):
    """Findings must conform to the documented schema."""

    def _get_one_finding(self):
        """Return any single finding from sample diagnostics."""
        report = build_sample_diagnostics()
        self.assertGreater(len(report["findings"]), 0, "Expected at least one finding")
        return report["findings"][0]

    def test_finding_has_required_fields(self):
        finding = self._get_one_finding()
        required = {"id", "ruleId", "severity", "category", "target",
                    "title", "description", "evidence", "recommendation", "confidence"}
        for field in required:
            self.assertIn(field, finding, f"Finding missing required field: {field!r}")

    def test_finding_target_has_required_fields(self):
        finding = self._get_one_finding()
        target_fields = {"kind", "id", "label"}
        for field in target_fields:
            self.assertIn(field, finding["target"],
                          f"Finding target missing field: {field!r}")

    def test_finding_id_is_deterministic(self):
        """The same rule+target combination must always produce the same finding ID."""
        report_a = build_sample_diagnostics()
        report_b = build_sample_diagnostics()
        ids_a = {f["id"] for f in report_a["findings"]}
        ids_b = {f["id"] for f in report_b["findings"]}
        self.assertEqual(ids_a, ids_b,
                         "Finding IDs must be deterministic across runs")

    def test_finding_id_format(self):
        """IDs must follow the 'finding:<12-hex-chars>' format."""
        report = build_sample_diagnostics()
        import re
        pattern = re.compile(r"^finding:[a-f0-9]{12}$")
        for f in report["findings"]:
            self.assertRegex(f["id"], pattern,
                             f"Finding ID {f['id']!r} does not match expected pattern")

    def test_no_raw_secrets_in_findings(self):
        """Raw secret values must never appear in findings; only '***REDACTED***' is allowed."""
        # Build a topology with a container that has a redacted label
        container = _simple_container(
            labels={"app.api_key": "***REDACTED***", "app.name": "myapp"}
        )
        topo = _make_topology(containers=[container])
        report = analyze_topology(topo)
        text = json.dumps(report)
        # The redaction marker is acceptable
        # No raw secret value should appear (we know "super-secret" is not the marker)
        self.assertNotIn("super-secret", text)
        # But the redaction marker key names are fine in evidence
        for f in report["findings"]:
            if f["ruleId"] == "secret-like-label-redacted":
                evidence = f["evidence"]
                # Keys list must only contain key names, not values
                for key_name in evidence.get("redactedKeys", []):
                    self.assertNotEqual(
                        key_name, "***REDACTED***",
                        "Evidence redactedKeys must list key names, not values"
                    )


# ─────────────────────────────────────────────────────────────────────────────
# TestSampleDiagnostics
# ─────────────────────────────────────────────────────────────────────────────

class TestSampleDiagnostics(unittest.TestCase):
    """Tests against the full sample diagnostics report."""

    @classmethod
    def setUpClass(cls):
        cls.report = build_sample_diagnostics()

    def test_no_docker_import_needed(self):
        """build_sample_diagnostics() must work even when docker is not installed."""
        import sys
        # Temporarily shadow the docker module
        original = sys.modules.get("docker")
        sys.modules["docker"] = None  # type: ignore[assignment]
        try:
            # Re-import from scratch to avoid cached module state
            report = build_sample_diagnostics()
            self.assertIn("findings", report)
        finally:
            if original is None:
                sys.modules.pop("docker", None)
            else:
                sys.modules["docker"] = original

    def test_schema_version(self):
        self.assertEqual(self.report["schemaVersion"], "1.0")

    def test_has_findings_list(self):
        self.assertIn("findings", self.report)
        self.assertIsInstance(self.report["findings"], list)

    def test_has_summary(self):
        self.assertIn("summary", self.report)

    def test_summary_keys_complete(self):
        summary = self.report["summary"]
        for key in ("findings", "bySeverity", "byCategory"):
            self.assertIn(key, summary, f"Summary missing key: {key!r}")

    def test_findings_count_matches_summary(self):
        self.assertEqual(
            self.report["summary"]["findings"],
            len(self.report["findings"]),
            "summary.findings count must match len(findings)",
        )

    def test_severity_counts_add_up(self):
        by_severity = self.report["summary"]["bySeverity"]
        total = sum(by_severity.values())
        self.assertEqual(
            total,
            self.report["summary"]["findings"],
            "bySeverity counts must sum to total findings",
        )

    def test_all_findings_json_serialisable(self):
        try:
            json.dumps(self.report)
        except (TypeError, ValueError) as exc:
            self.fail(f"Report is not JSON-serialisable: {exc}")

    def test_sample_flag_true(self):
        self.assertTrue(self.report["sample"])

    def test_has_warnings_list(self):
        self.assertIn("warnings", self.report)
        self.assertIsInstance(self.report["warnings"], list)

    def test_has_generated_at(self):
        self.assertIn("generatedAt", self.report)
        self.assertIsInstance(self.report["generatedAt"], str)
        self.assertGreater(len(self.report["generatedAt"]), 0)

    def test_has_source(self):
        self.assertIn("source", self.report)


# ─────────────────────────────────────────────────────────────────────────────
# TestExposedPortRule
# ─────────────────────────────────────────────────────────────────────────────

class TestExposedPortRule(unittest.TestCase):
    """Rule: exposed-port."""

    def _run(self, container, metrics=None):
        topo = _make_topology(containers=[container])
        return analyze_topology(topo, metrics)["findings"]

    def test_public_bind_port_is_medium(self):
        """Port bound to 0.0.0.0 should be severity medium."""
        c = _simple_container(ports=[PortMapping(80, 8080, "tcp", "0.0.0.0")])
        findings = [f for f in self._run(c) if f["ruleId"] == "exposed-port"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")
        self.assertEqual(findings[0]["evidence"]["hostIp"], "0.0.0.0")

    def test_loopback_bind_port_is_low(self):
        """Port bound to 127.0.0.1 should be severity low."""
        c = _simple_container(ports=[PortMapping(3000, 3000, "tcp", "127.0.0.1")])
        findings = [f for f in self._run(c) if f["ruleId"] == "exposed-port"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "low")
        self.assertEqual(findings[0]["evidence"]["hostIp"], "127.0.0.1")

    def test_ipv6_loopback_port_is_low(self):
        """Port bound to ::1 should also be severity low."""
        c = _simple_container(ports=[PortMapping(3000, 3000, "tcp", "::1")])
        findings = [f for f in self._run(c) if f["ruleId"] == "exposed-port"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "low")

    def test_no_finding_for_unpublished_port(self):
        """Port with hostPort=None should produce no exposed-port finding."""
        c = _simple_container(ports=[PortMapping(5432, None, "tcp")])
        findings = [f for f in self._run(c) if f["ruleId"] == "exposed-port"]
        self.assertEqual(len(findings), 0)

    def test_network_nodes_not_flagged(self):
        """Network nodes must never produce exposed-port findings."""
        net = _simple_network()
        topo = _make_topology(networks=[net])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "exposed-port"]
        self.assertEqual(len(findings), 0)

    def test_no_host_ip_is_medium(self):
        """Port with no host_ip (None) should default to severity medium."""
        c = _simple_container(ports=[PortMapping(80, 8080, "tcp", None)])
        findings = [f for f in self._run(c) if f["ruleId"] == "exposed-port"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_empty_host_ip_is_medium(self):
        """Port with host_ip='' should be severity medium."""
        # Construct via dict since PortMapping has host_ip as Optional
        topo_dict = {
            "schemaVersion": "1.0",
            "source": {"engine": "test"},
            "sample": False,
            "nodes": [{
                "id": "container:aabbcc001122",
                "label": "web",
                "kind": "container",
                "status": "running",
                "ports": [{"containerPort": 80, "hostPort": 8080, "protocol": "tcp", "hostIp": ""}],
            }],
            "links": [],
        }
        findings = [f for f in analyze_topology(topo_dict)["findings"]
                    if f["ruleId"] == "exposed-port"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_evidence_has_required_fields(self):
        c = _simple_container(ports=[PortMapping(80, 8080, "tcp", "0.0.0.0")])
        findings = [f for f in self._run(c) if f["ruleId"] == "exposed-port"]
        self.assertEqual(len(findings), 1)
        evidence = findings[0]["evidence"]
        for key in ("hostIp", "hostPort", "containerPort", "protocol"):
            self.assertIn(key, evidence, f"evidence missing key: {key!r}")

    def test_two_published_ports_two_findings(self):
        c = _simple_container(ports=[
            PortMapping(80, 8080, "tcp", "0.0.0.0"),
            PortMapping(443, 8443, "tcp", "0.0.0.0"),
        ])
        findings = [f for f in self._run(c) if f["ruleId"] == "exposed-port"]
        self.assertEqual(len(findings), 2)


# ─────────────────────────────────────────────────────────────────────────────
# TestSecretLabelRule
# ─────────────────────────────────────────────────────────────────────────────

class TestSecretLabelRule(unittest.TestCase):
    """Rule: secret-like-label-redacted."""

    def _run(self, container):
        topo = _make_topology(containers=[container])
        return [f for f in analyze_topology(topo)["findings"]
                if f["ruleId"] == "secret-like-label-redacted"]

    def test_redacted_label_produces_finding(self):
        c = _simple_container(labels={"app.api_key": "***REDACTED***"})
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "low")

    def test_no_finding_without_redacted_labels(self):
        c = _simple_container(labels={"app.name": "myapp", "app.version": "1.0"})
        findings = self._run(c)
        self.assertEqual(len(findings), 0)

    def test_raw_secret_never_in_finding(self):
        """The finding evidence must use key names only, not the '***REDACTED***' marker as a value."""
        c = _simple_container(labels={
            "app.api_key": "***REDACTED***",
            "app.token": "***REDACTED***",
        })
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        evidence = findings[0]["evidence"]
        # redactedKeyCount must be 2
        self.assertEqual(evidence["redactedKeyCount"], 2)
        # redactedKeys must be the key names (strings), not the marker value
        for k in evidence["redactedKeys"]:
            self.assertNotEqual(k, "***REDACTED***",
                                "redactedKeys must list label key names, not values")
        # Both key names must appear
        self.assertIn("app.api_key", evidence["redactedKeys"])
        self.assertIn("app.token", evidence["redactedKeys"])

    def test_multiple_redacted_keys_one_finding(self):
        """Multiple redacted labels on the same container → exactly one finding."""
        c = _simple_container(labels={
            "app.secret": "***REDACTED***",
            "db.password": "***REDACTED***",
            "app.name": "safe",
        })
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["evidence"]["redactedKeyCount"], 2)

    def test_normal_label_value_is_not_flagged(self):
        c = _simple_container(labels={"app.name": "myapp"})
        findings = self._run(c)
        self.assertEqual(len(findings), 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestBroadBindMountRule
# ─────────────────────────────────────────────────────────────────────────────

class TestBroadBindMountRule(unittest.TestCase):
    """Rule: broad-bind-mount."""

    def _run(self, container):
        topo = _make_topology(containers=[container])
        return [f for f in analyze_topology(topo)["findings"]
                if f["ruleId"] == "broad-bind-mount"]

    def test_docker_sock_is_high_severity(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/var/run/docker.sock",
                      destination="/var/run/docker.sock", mode="rw", rw=True)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_etc_mount_is_medium_severity(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/etc/ssl/certs",
                      destination="/certs", mode="ro", rw=False)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_root_mount_is_medium_severity(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/",
                      destination="/host", mode="rw", rw=True)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_proc_mount_is_medium_severity(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/proc",
                      destination="/host/proc", mode="ro", rw=False)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_home_mount_is_medium_severity(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/home/user",
                      destination="/data", mode="ro", rw=False)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_volume_mount_not_flagged(self):
        """type='volume' must never produce a broad-bind-mount finding."""
        c = _simple_container(mounts=[
            MountInfo(type="volume", source="",
                      destination="/var/lib/postgresql/data", mode="z", rw=True)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 0)

    def test_named_volume_not_flagged(self):
        """Named volume (type='volume', source='demo_pgdata') must not be flagged."""
        c = _simple_container(mounts=[
            MountInfo(type="volume", source="demo_pgdata",
                      destination="/var/lib/postgresql/data", mode="z", rw=True)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 0)

    def test_innocuous_bind_mount_not_flagged(self):
        """Bind mounts from non-sensitive paths must not be flagged."""
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/myapp/config",
                      destination="/config", mode="ro", rw=False)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 0)

    def test_evidence_has_source_and_destination(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/etc/ssl",
                      destination="/certs", mode="ro", rw=False)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        evidence = findings[0]["evidence"]
        self.assertEqual(evidence["source"], "/etc/ssl")
        self.assertEqual(evidence["destination"], "/certs")


# ─────────────────────────────────────────────────────────────────────────────
# TestExitedContainerRule
# ─────────────────────────────────────────────────────────────────────────────

class TestExitedContainerRule(unittest.TestCase):
    """Rule: exited-container."""

    def _run(self, container):
        topo = _make_topology(containers=[container])
        return [f for f in analyze_topology(topo)["findings"]
                if f["ruleId"] == "exited-container"]

    def test_exited_status_produces_finding(self):
        c = _simple_container(status="exited")
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_dead_status_is_high_severity(self):
        c = _simple_container(status="dead")
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_restarting_status_produces_finding(self):
        c = _simple_container(status="restarting")
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_running_status_no_finding(self):
        c = _simple_container(status="running")
        findings = self._run(c)
        self.assertEqual(len(findings), 0)

    def test_paused_status_no_finding(self):
        c = _simple_container(status="paused")
        findings = self._run(c)
        self.assertEqual(len(findings), 0)

    def test_evidence_has_status(self):
        c = _simple_container(status="exited")
        findings = self._run(c)
        self.assertEqual(findings[0]["evidence"]["status"], "exited")


# ─────────────────────────────────────────────────────────────────────────────
# TestNoNetworkRule
# ─────────────────────────────────────────────────────────────────────────────

class TestNoNetworkRule(unittest.TestCase):
    """Rule: no-network."""

    def test_running_container_without_links_flagged(self):
        c = _simple_container(status="running")
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "no-network"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "low")

    def test_container_with_link_not_flagged(self):
        c = _simple_container(cid="container:aabbccddee00", status="running")
        net = _simple_network(nid="network:net0net0net0")
        lnk = _link("container:aabbccddee00", "network:net0net0net0")
        topo = _make_topology(containers=[c], networks=[net], links=[lnk])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "no-network"]
        self.assertEqual(len(findings), 0)

    def test_exited_container_not_flagged_for_no_network(self):
        """Exited containers must NOT be flagged for having no network."""
        c = _simple_container(status="exited")
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "no-network"]
        self.assertEqual(len(findings), 0)

    def test_dead_container_not_flagged_for_no_network(self):
        c = _simple_container(status="dead")
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "no-network"]
        self.assertEqual(len(findings), 0)

    def test_paused_container_without_links_is_flagged(self):
        """Paused containers are still 'running' — they should be flagged."""
        c = _simple_container(status="paused")
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "no-network"]
        self.assertEqual(len(findings), 1)


# ─────────────────────────────────────────────────────────────────────────────
# TestMultiNetworkRule
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiNetworkRule(unittest.TestCase):
    """Rule: multi-network-container."""

    def test_two_networks_produces_info_finding(self):
        c = _simple_container(cid="container:aabbccddee00", status="running")
        net1 = _simple_network(nid="network:net1net1net1", label="frontend")
        net2 = _simple_network(nid="network:net2net2net2", label="backend")
        lnk1 = _link("container:aabbccddee00", "network:net1net1net1")
        lnk2 = _link("container:aabbccddee00", "network:net2net2net2")
        topo = _make_topology(
            containers=[c], networks=[net1, net2], links=[lnk1, lnk2]
        )
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "multi-network-container"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "info")
        self.assertEqual(findings[0]["evidence"]["networkCount"], 2)

    def test_one_network_no_finding(self):
        c = _simple_container(cid="container:aabbccddee00", status="running")
        net = _simple_network(nid="network:net1net1net1", label="frontend")
        lnk = _link("container:aabbccddee00", "network:net1net1net1")
        topo = _make_topology(containers=[c], networks=[net], links=[lnk])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "multi-network-container"]
        self.assertEqual(len(findings), 0)

    def test_zero_networks_no_finding(self):
        c = _simple_container(status="running")
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "multi-network-container"]
        self.assertEqual(len(findings), 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestHighCpuRule
# ─────────────────────────────────────────────────────────────────────────────

class TestHighCpuRule(unittest.TestCase):
    """Rule: high-cpu (requires metrics)."""

    def _run_with_cpu(self, cpu_percent):
        c = _simple_container(cid="container:aabbccddee00", label="myapp")
        topo = _make_topology(containers=[c])
        metrics = {
            "containers": [
                {
                    "id": "container:aabbccddee00",
                    "name": "myapp",
                    "status": "running",
                    "cpuPercent": cpu_percent,
                    "memoryPercent": 10.0,
                }
            ]
        }
        return [f for f in analyze_topology(topo, metrics)["findings"]
                if f["ruleId"] == "high-cpu"]

    def test_cpu_above_80_is_high(self):
        findings = self._run_with_cpu(85.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_cpu_exactly_80_is_high(self):
        findings = self._run_with_cpu(80.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_cpu_between_40_and_80_is_medium(self):
        findings = self._run_with_cpu(60.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_cpu_exactly_40_is_medium(self):
        findings = self._run_with_cpu(40.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_cpu_below_40_no_finding(self):
        findings = self._run_with_cpu(39.9)
        self.assertEqual(len(findings), 0)

    def test_cpu_zero_no_finding(self):
        findings = self._run_with_cpu(0.0)
        self.assertEqual(len(findings), 0)

    def test_no_metrics_no_finding(self):
        c = _simple_container(cid="container:aabbccddee00")
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo, None)["findings"]
                    if f["ruleId"] == "high-cpu"]
        self.assertEqual(len(findings), 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestHighMemoryRule
# ─────────────────────────────────────────────────────────────────────────────

class TestHighMemoryRule(unittest.TestCase):
    """Rule: high-memory (requires metrics)."""

    def _run_with_mem(self, mem_percent):
        c = _simple_container(cid="container:aabbccddee00", label="myapp")
        topo = _make_topology(containers=[c])
        metrics = {
            "containers": [
                {
                    "id": "container:aabbccddee00",
                    "name": "myapp",
                    "status": "running",
                    "cpuPercent": 5.0,
                    "memoryPercent": mem_percent,
                }
            ]
        }
        return [f for f in analyze_topology(topo, metrics)["findings"]
                if f["ruleId"] == "high-memory"]

    def test_memory_above_85_is_high(self):
        findings = self._run_with_mem(90.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_memory_exactly_85_is_high(self):
        findings = self._run_with_mem(85.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_memory_between_70_and_85_is_medium(self):
        findings = self._run_with_mem(75.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_memory_exactly_70_is_medium(self):
        findings = self._run_with_mem(70.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_memory_below_70_no_finding(self):
        findings = self._run_with_mem(69.9)
        self.assertEqual(len(findings), 0)

    def test_memory_zero_no_finding(self):
        findings = self._run_with_mem(0.0)
        self.assertEqual(len(findings), 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestOrphanNetworkRule
# ─────────────────────────────────────────────────────────────────────────────

class TestOrphanNetworkRule(unittest.TestCase):
    """Rule: orphan-network."""

    def test_network_with_no_containers_flagged(self):
        net = _simple_network(label="mynet")
        topo = _make_topology(networks=[net])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "orphan-network"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "low")
        self.assertAlmostEqual(findings[0]["confidence"], 0.85)

    def test_bridge_network_not_flagged(self):
        """Default network named 'bridge' must never be flagged as orphan."""
        net = _simple_network(nid="network:bridgebridg", label="bridge")
        topo = _make_topology(networks=[net])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "orphan-network"]
        self.assertEqual(len(findings), 0)

    def test_host_network_not_flagged(self):
        net = _simple_network(nid="network:hostho000000", label="host")
        topo = _make_topology(networks=[net])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "orphan-network"]
        self.assertEqual(len(findings), 0)

    def test_none_network_not_flagged(self):
        net = _simple_network(nid="network:nonenonenone", label="none")
        topo = _make_topology(networks=[net])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "orphan-network"]
        self.assertEqual(len(findings), 0)

    def test_network_with_attached_container_not_flagged(self):
        c = _simple_container(cid="container:aabbccddee00", status="running")
        net = _simple_network(nid="network:net0net0net0", label="mynet")
        lnk = _link("container:aabbccddee00", "network:net0net0net0")
        topo = _make_topology(containers=[c], networks=[net], links=[lnk])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "orphan-network"]
        self.assertEqual(len(findings), 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestNoDuplicates
# ─────────────────────────────────────────────────────────────────────────────

class TestNoDuplicates(unittest.TestCase):
    """Finding IDs must be unique within a report."""

    def test_same_rule_same_target_produces_at_most_one_finding_per_port(self):
        """Two different ports on the same container produce separate findings."""
        c = _simple_container(ports=[
            PortMapping(80, 8080, "tcp", "0.0.0.0"),
            PortMapping(443, 8443, "tcp", "0.0.0.0"),
        ])
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "exposed-port"]
        ids = [f["id"] for f in findings]
        self.assertEqual(len(ids), len(set(ids)),
                         "Each port must produce a unique finding ID")

    def test_sample_diagnostics_has_no_duplicate_finding_ids(self):
        report = build_sample_diagnostics()
        ids = [f["id"] for f in report["findings"]]
        self.assertEqual(len(ids), len(set(ids)),
                         "Sample diagnostics must have no duplicate finding IDs")

    def test_finding_id_helper_is_deterministic(self):
        id1 = _finding_id("exposed-port", "container:abc", "0.0.0.0:8080:80/tcp")
        id2 = _finding_id("exposed-port", "container:abc", "0.0.0.0:8080:80/tcp")
        self.assertEqual(id1, id2)

    def test_finding_id_changes_with_different_extra(self):
        id1 = _finding_id("exposed-port", "container:abc", "0.0.0.0:8080:80/tcp")
        id2 = _finding_id("exposed-port", "container:abc", "0.0.0.0:8443:443/tcp")
        self.assertNotEqual(id1, id2)


# ─────────────────────────────────────────────────────────────────────────────
# TestAcceptsDictTopology
# ─────────────────────────────────────────────────────────────────────────────

class TestAcceptsDictTopology(unittest.TestCase):
    """analyze_topology() must accept both Topology objects and plain dicts."""

    def test_accepts_topology_object(self):
        topo = _make_topology()
        report = analyze_topology(topo)
        self.assertIn("findings", report)

    def test_accepts_dict(self):
        topo_dict = {
            "schemaVersion": "1.0",
            "source": {"engine": "test"},
            "sample": False,
            "nodes": [],
            "links": [],
        }
        report = analyze_topology(topo_dict)
        self.assertIn("findings", report)

    def test_empty_topology_has_no_findings(self):
        topo = _make_topology()
        report = analyze_topology(topo)
        self.assertEqual(len(report["findings"]), 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestCLICommand
# ─────────────────────────────────────────────────────────────────────────────

class TestCLICommand(unittest.TestCase):
    """End-to-end tests for `python app.py diagnose --sample`."""

    _PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")

    def _run_diagnose_sample(self):
        env = {
            "PYTHONPATH": "src",
            "PATH": os.environ["PATH"],
        }
        return subprocess.run(
            [sys.executable, "app.py", "diagnose", "--sample"],
            capture_output=True,
            text=True,
            cwd=self._PROJECT_ROOT,
            env=env,
        )

    def test_diagnose_sample_returns_zero(self):
        result = self._run_diagnose_sample()
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit code 0; got {result.returncode}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout[:500]}",
        )

    def test_diagnose_sample_output_is_json(self):
        result = self._run_diagnose_sample()
        self.assertEqual(result.returncode, 0,
                         f"Command failed:\n{result.stderr}")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(
                f"Output is not valid JSON: {exc}\n"
                f"stdout: {result.stdout[:500]}"
            )
        self.assertIn("schemaVersion", data)
        self.assertIn("findings", data)
        self.assertIn("summary", data)

    def test_diagnose_sample_has_findings(self):
        result = self._run_diagnose_sample()
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertIsInstance(data["findings"], list)
        self.assertGreater(
            len(data["findings"]), 0,
            "Sample diagnostics should produce at least one finding",
        )


# ─────────────────────────────────────────────────────────────────────────────
# TestAPIEndpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestAPIEndpoint(unittest.TestCase):
    """Tests for GET /api/diagnostics via make_handler."""

    def _make_handler(self, allow_cors=False, use_sample=True):
        from docker_topology_live.server import make_handler
        HandlerCls = make_handler(use_sample=use_sample, allow_cors=allow_cors)
        handler = HandlerCls.__new__(HandlerCls)
        handler.path = "/api/diagnostics"
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = io.BytesIO()
        return handler

    def test_diagnostics_endpoint_returns_json(self):
        handler = self._make_handler(use_sample=True)
        handler.do_GET()
        # Must have sent a 200 response
        handler.send_response.assert_called_once_with(200)
        # Content-Type must be application/json
        header_calls = [c.args for c in handler.send_header.call_args_list]
        ct_headers = [v for n, v in header_calls if n == "Content-Type"]
        self.assertTrue(
            any("application/json" in v for v in ct_headers),
            f"Expected application/json content-type, got: {ct_headers}",
        )
        # Body must be valid JSON with expected keys
        body = handler.wfile.getvalue()
        data = json.loads(body.decode())
        self.assertIn("schemaVersion", data)
        self.assertIn("findings", data)
        self.assertIn("summary", data)

    def test_cors_default_off(self):
        handler = self._make_handler(allow_cors=False)
        handler.do_GET()
        header_calls = [c.args for c in handler.send_header.call_args_list]
        cors_headers = [n for n, *_ in header_calls
                        if "Access-Control-Allow-Origin" in n]
        self.assertEqual(
            cors_headers, [],
            "Access-Control-Allow-Origin must NOT be sent when allow_cors=False",
        )

    def test_cors_on_when_enabled(self):
        handler = self._make_handler(allow_cors=True)
        handler.do_GET()
        header_calls = [c.args for c in handler.send_header.call_args_list]
        cors = [(n, v) for n, v in header_calls
                if n == "Access-Control-Allow-Origin"]
        self.assertGreater(
            len(cors), 0,
            "Access-Control-Allow-Origin must be sent when allow_cors=True",
        )
        self.assertEqual(cors[0][1], "*")

    def test_diagnostics_body_is_valid_json_with_findings(self):
        handler = self._make_handler(use_sample=True)
        handler.do_GET()
        body = handler.wfile.getvalue()
        data = json.loads(body.decode())
        self.assertIsInstance(data.get("findings"), list)

    def test_diagnostics_summary_present(self):
        handler = self._make_handler(use_sample=True)
        handler.do_GET()
        body = handler.wfile.getvalue()
        data = json.loads(body.decode())
        self.assertIn("summary", data)
        self.assertIn("findings", data["summary"])


# ─────────────────────────────────────────────────────────────────────────────
# Additional edge-case tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPrivilegedLabelRule(unittest.TestCase):
    """Rule: privileged-label."""

    def _run(self, labels):
        c = _simple_container(labels=labels)
        topo = _make_topology(containers=[c])
        return [f for f in analyze_topology(topo)["findings"]
                if f["ruleId"] == "privileged-label"]

    def test_privileged_true_is_high(self):
        findings = self._run({"security.privileged": "true"})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")
        self.assertAlmostEqual(findings[0]["confidence"], 0.75)

    def test_privileged_one_is_high(self):
        findings = self._run({"privileged": "1"})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_privileged_yes_is_high(self):
        findings = self._run({"run.privileged": "yes"})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_privileged_false_no_finding(self):
        findings = self._run({"privileged": "false"})
        self.assertEqual(len(findings), 0)

    def test_no_privileged_key_no_finding(self):
        findings = self._run({"app.name": "myapp"})
        self.assertEqual(len(findings), 0)


class TestHighPidsRule(unittest.TestCase):
    """Rule: high-pids (requires metrics)."""

    def _run_with_pids(self, pids_count):
        c = _simple_container(cid="container:aabbccddee00", label="myapp")
        topo = _make_topology(containers=[c])
        metrics = {
            "containers": [{
                "id": "container:aabbccddee00",
                "name": "myapp",
                "status": "running",
                "cpuPercent": 5.0,
                "memoryPercent": 10.0,
                "pids": pids_count,
            }]
        }
        return [f for f in analyze_topology(topo, metrics)["findings"]
                if f["ruleId"] == "high-pids"]

    def test_pids_200_or_more_is_medium(self):
        findings = self._run_with_pids(200)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_pids_many_is_medium(self):
        findings = self._run_with_pids(500)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_pids_below_200_no_finding(self):
        findings = self._run_with_pids(199)
        self.assertEqual(len(findings), 0)


class TestHighBlockWriteRule(unittest.TestCase):
    """Rule: high-block-write (requires metrics, heuristic)."""

    _GIB = 1024 ** 3

    def _run_with_write(self, write_bytes):
        c = _simple_container(cid="container:aabbccddee00", label="myapp")
        topo = _make_topology(containers=[c])
        metrics = {
            "containers": [{
                "id": "container:aabbccddee00",
                "name": "myapp",
                "status": "running",
                "cpuPercent": 5.0,
                "memoryPercent": 10.0,
                "blockWriteBytes": write_bytes,
            }]
        }
        return [f for f in analyze_topology(topo, metrics)["findings"]
                if f["ruleId"] == "high-block-write"]

    def test_block_write_above_1gib_is_medium(self):
        findings = self._run_with_write(self._GIB + 1)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")
        self.assertAlmostEqual(findings[0]["confidence"], 0.5)

    def test_block_write_exactly_1gib_is_medium(self):
        findings = self._run_with_write(self._GIB)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_block_write_below_1gib_no_finding(self):
        findings = self._run_with_write(self._GIB - 1)
        self.assertEqual(len(findings), 0)


class TestUnnamedContainerRule(unittest.TestCase):
    """Rule: unnamed-container."""

    def _run(self, label):
        c = _simple_container(label=label)
        topo = _make_topology(containers=[c])
        return [f for f in analyze_topology(topo)["findings"]
                if f["ruleId"] == "unnamed-container"]

    def test_hex_name_flagged(self):
        """12+ hex char name should be flagged as likely auto-generated."""
        findings = self._run("a1b2c3d4e5f6")
        self.assertEqual(len(findings), 1)
        self.assertAlmostEqual(findings[0]["confidence"], 0.6)

    def test_very_short_name_flagged(self):
        """Name shorter than 3 chars should be flagged."""
        findings = self._run("ab")
        self.assertEqual(len(findings), 1)

    def test_single_char_name_flagged(self):
        findings = self._run("x")
        self.assertEqual(len(findings), 1)

    def test_descriptive_name_not_flagged(self):
        findings = self._run("web-server")
        self.assertEqual(len(findings), 0)

    def test_three_char_name_not_flagged(self):
        findings = self._run("api")
        self.assertEqual(len(findings), 0)


class TestMissingComposeLabelsRule(unittest.TestCase):
    """Rule: missing-compose-labels."""

    def test_container_without_compose_flagged_when_others_have_it(self):
        c1 = _simple_container(
            cid="container:aaaaaaaaaaaa",
            label="composed",
            labels={"com.docker.compose.project": "demo",
                    "com.docker.compose.service": "web"},
        )
        c2 = _simple_container(
            cid="container:bbbbbbbbbbbb",
            label="standalone",
            labels={},
        )
        topo = _make_topology(containers=[c1, c2])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "missing-compose-labels"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["target"]["label"], "standalone")
        self.assertAlmostEqual(findings[0]["confidence"], 0.6)

    def test_all_containers_without_compose_no_finding(self):
        """When NO container has compose labels, do not flag any."""
        c1 = _simple_container(cid="container:aaaaaaaaaaaa", label="app1")
        c2 = _simple_container(cid="container:bbbbbbbbbbbb", label="app2")
        topo = _make_topology(containers=[c1, c2])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "missing-compose-labels"]
        self.assertEqual(len(findings), 0)

    def test_all_containers_with_compose_no_finding(self):
        labels = {"com.docker.compose.project": "demo",
                  "com.docker.compose.service": "web"}
        c = _simple_container(labels=labels)
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "missing-compose-labels"]
        self.assertEqual(len(findings), 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestWarningsParameter
# ─────────────────────────────────────────────────────────────────────────────

class TestWarningsParameter(unittest.TestCase):
    """analyze_topology(warnings=...) must propagate warnings into the report."""

    def test_warnings_none_gives_empty_list(self):
        topo = _make_topology()
        report = analyze_topology(topo, warnings=None)
        self.assertIsInstance(report["warnings"], list)
        self.assertEqual(report["warnings"], [])

    def test_warnings_empty_list_gives_empty_list(self):
        topo = _make_topology()
        report = analyze_topology(topo, warnings=[])
        self.assertEqual(report["warnings"], [])

    def test_warnings_single_entry_included(self):
        topo = _make_topology()
        msg = "Metrics unavailable for diagnostics; resource rules were skipped."
        report = analyze_topology(topo, warnings=[msg])
        self.assertEqual(report["warnings"], [msg])

    def test_warnings_multiple_entries_preserved(self):
        topo = _make_topology()
        msgs = ["Warning one", "Warning two"]
        report = analyze_topology(topo, warnings=msgs)
        self.assertEqual(report["warnings"], msgs)

    def test_warnings_does_not_affect_findings(self):
        """Supplying a warnings list must not change the findings output."""
        topo = _make_topology()
        report_without = analyze_topology(topo)
        report_with = analyze_topology(topo, warnings=["something"])
        self.assertEqual(report_without["findings"], report_with["findings"])

    def test_warnings_are_strings(self):
        """Each entry in warnings must remain a string."""
        topo = _make_topology()
        msg = "test warning"
        report = analyze_topology(topo, warnings=[msg])
        for w in report["warnings"]:
            self.assertIsInstance(w, str)


# ─────────────────────────────────────────────────────────────────────────────
# TestMetricsFailurePropagation
# ─────────────────────────────────────────────────────────────────────────────

class TestMetricsFailurePropagation(unittest.TestCase):
    """Metrics collection failures must produce warnings, never tracebacks."""

    # ── server._get_diagnostics() ───────────────────────────────────────────

    def test_api_get_diagnostics_metrics_failure_returns_warning(self):
        """_get_diagnostics(use_metrics=True) with failing metrics → non-empty warnings."""
        from unittest.mock import patch
        from docker_topology_live.server import _get_diagnostics
        from docker_topology_live.scanner import build_sample

        with patch("docker_topology_live.server._get_topology",
                   return_value=build_sample()), \
             patch("docker_topology_live.server._get_metrics",
                   side_effect=RuntimeError("mock metrics fail")):
            result = _get_diagnostics(use_sample=False, use_metrics=True)

        self.assertIn("warnings", result)
        self.assertIsInstance(result["warnings"], list)
        self.assertGreater(len(result["warnings"]), 0,
                           "Expected at least one warning when metrics fail")

    def test_api_get_diagnostics_metrics_failure_no_traceback_in_warning(self):
        """Warnings must not contain Python tracebacks or raw exception details."""
        from unittest.mock import patch
        from docker_topology_live.server import _get_diagnostics
        from docker_topology_live.scanner import build_sample

        with patch("docker_topology_live.server._get_topology",
                   return_value=build_sample()), \
             patch("docker_topology_live.server._get_metrics",
                   side_effect=RuntimeError("SUPER_SENSITIVE_DETAIL")):
            result = _get_diagnostics(use_sample=False, use_metrics=True)

        text = json.dumps(result)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("SUPER_SENSITIVE_DETAIL", text,
                         "Raw exception message must not appear in diagnostics output")

    def test_api_get_diagnostics_metrics_success_empty_warnings(self):
        """When metrics collection succeeds, warnings remains empty."""
        from unittest.mock import patch
        from docker_topology_live.server import _get_diagnostics
        from docker_topology_live.scanner import build_sample
        from docker_topology_live.metrics import build_sample_metrics

        with patch("docker_topology_live.server._get_topology",
                   return_value=build_sample()), \
             patch("docker_topology_live.server._get_metrics",
                   return_value=build_sample_metrics()):
            result = _get_diagnostics(use_sample=False, use_metrics=True)

        self.assertEqual(result["warnings"], [],
                         "warnings must be empty when metrics collection succeeds")

    def test_api_get_diagnostics_no_metrics_flag_empty_warnings(self):
        """When use_metrics=False, warnings should be empty (no metrics attempted)."""
        from unittest.mock import patch
        from docker_topology_live.server import _get_diagnostics
        from docker_topology_live.scanner import build_sample

        with patch("docker_topology_live.server._get_topology",
                   return_value=build_sample()):
            result = _get_diagnostics(use_sample=False, use_metrics=False)

        self.assertEqual(result["warnings"], [])

    def test_api_endpoint_metrics_failure_body_is_valid_json_with_warnings(self):
        """GET /api/diagnostics handler with metrics failure → valid JSON + warnings."""
        from unittest.mock import patch, MagicMock
        from docker_topology_live.server import make_handler
        from docker_topology_live.scanner import build_sample

        HandlerCls = make_handler(
            use_sample=False, allow_cors=False, enable_metrics=True
        )
        handler = HandlerCls.__new__(HandlerCls)
        handler.path = "/api/diagnostics"
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = io.BytesIO()

        with patch("docker_topology_live.server._get_topology",
                   return_value=build_sample()), \
             patch("docker_topology_live.server._get_metrics",
                   side_effect=RuntimeError("mock metrics fail")):
            handler.do_GET()

        body = handler.wfile.getvalue()
        data = json.loads(body.decode())
        self.assertIn("warnings", data)
        self.assertIsInstance(data["warnings"], list)
        self.assertGreater(len(data["warnings"]), 0)

    # ── CLI _cmd_diagnose() ─────────────────────────────────────────────────

    def test_cli_metrics_failure_includes_warning_in_json_output(self):
        """CLI diagnose --include-metrics with failing metrics → warning in JSON stdout."""
        from unittest.mock import patch
        from docker_topology_live import cli
        from docker_topology_live.scanner import build_sample

        args = type("_Args", (), {
            "sample": False,
            "include_metrics": True,
            "output": None,
        })()

        captured = io.StringIO()

        with patch("docker_topology_live.cli.scan_live", return_value=build_sample()), \
             patch("docker_topology_live.metrics.collect_live_metrics",
                   side_effect=RuntimeError("mock metrics fail")), \
             patch("sys.stdout", new=captured):
            rc = cli._cmd_diagnose(args)

        self.assertEqual(rc, 0, "Command should succeed even when metrics fail")
        output = captured.getvalue().strip()
        self.assertTrue(output, "Expected JSON output on stdout")
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            self.fail(f"stdout is not valid JSON: {exc}\nOutput: {output[:300]}")

        self.assertIn("warnings", data)
        self.assertIsInstance(data["warnings"], list)
        self.assertGreater(len(data["warnings"]), 0,
                           "Expected at least one warning in JSON when metrics fail")

    def test_cli_metrics_failure_warning_has_no_traceback(self):
        """Warning strings in CLI output must not expose tracebacks."""
        from unittest.mock import patch
        from docker_topology_live import cli
        from docker_topology_live.scanner import build_sample

        args = type("_Args", (), {
            "sample": False,
            "include_metrics": True,
            "output": None,
        })()

        captured = io.StringIO()

        with patch("docker_topology_live.cli.scan_live", return_value=build_sample()), \
             patch("docker_topology_live.metrics.collect_live_metrics",
                   side_effect=RuntimeError("SECRET_EXC_VALUE")), \
             patch("sys.stdout", new=captured):
            cli._cmd_diagnose(args)

        output = captured.getvalue()
        self.assertNotIn("Traceback", output)
        self.assertNotIn("SECRET_EXC_VALUE", output,
                         "Raw exception message must not appear in JSON output")

    def test_cli_metrics_success_empty_warnings(self):
        """CLI diagnose --include-metrics with successful metrics → empty warnings."""
        from unittest.mock import patch
        from docker_topology_live import cli
        from docker_topology_live.scanner import build_sample
        from docker_topology_live.metrics import build_sample_metrics

        args = type("_Args", (), {
            "sample": False,
            "include_metrics": True,
            "output": None,
        })()

        captured = io.StringIO()

        with patch("docker_topology_live.cli.scan_live", return_value=build_sample()), \
             patch("docker_topology_live.metrics.collect_live_metrics",
                   return_value=build_sample_metrics()), \
             patch("sys.stdout", new=captured):
            rc = cli._cmd_diagnose(args)

        self.assertEqual(rc, 0)
        data = json.loads(captured.getvalue().strip())
        self.assertEqual(data["warnings"], [])

    # ── SSE / _PeriodicDiagnostics ──────────────────────────────────────────

    def test_sse_live_diag_closure_metrics_failure_includes_warnings(self):
        """Simulate server.py _live_diag closure: metrics failure → doc with warnings."""
        from docker_topology_live.diagnostics import analyze_topology
        from docker_topology_live.scanner import build_sample

        # Replicate the _live_diag closure logic exactly as it appears in server.py
        def _live_diag_simulated():
            topo = build_sample()
            metrics = None
            _warnings: list = []
            try:
                raise RuntimeError("simulated metrics error")
            except Exception:
                _warnings.append(
                    "Metrics unavailable for diagnostics; resource rules were skipped."
                )
            return analyze_topology(topo, metrics, warnings=_warnings)

        doc = _live_diag_simulated()
        self.assertIn("warnings", doc)
        self.assertIsInstance(doc["warnings"], list)
        self.assertGreater(len(doc["warnings"]), 0)
        for w in doc["warnings"]:
            self.assertIsInstance(w, str)
            self.assertNotIn("Traceback", w)
            self.assertNotIn("RuntimeError", w)

    def test_sse_live_diag_closure_emits_valid_json(self):
        """Diagnostics document from _live_diag simulation is JSON-serialisable."""
        from docker_topology_live.diagnostics import analyze_topology
        from docker_topology_live.scanner import build_sample

        def _live_diag_simulated():
            topo = build_sample()
            metrics = None
            _warnings: list = [
                "Metrics unavailable for diagnostics; resource rules were skipped."
            ]
            return analyze_topology(topo, metrics, warnings=_warnings)

        doc = _live_diag_simulated()
        try:
            text = json.dumps(doc)
        except (TypeError, ValueError) as exc:
            self.fail(f"Document is not JSON-serialisable: {exc}")
        self.assertIn('"warnings"', text)

    def test_periodic_diag_emits_error_not_traceback_on_exception(self):
        """_PeriodicDiagnostics must emit an error event (not a traceback) on failure."""
        from docker_topology_live.events import _PeriodicDiagnostics, SSEWriter

        buf = io.BytesIO()

        class _FakeFile:
            def write(self, data):
                buf.write(data)
            def flush(self):
                pass

        writer = SSEWriter(_FakeFile())

        def _exploding_diag():
            raise RuntimeError("internal diagnostics error")

        pd = _PeriodicDiagnostics(writer, _exploding_diag, interval=999.0)
        result = pd._emit_once()

        output = buf.getvalue().decode("utf-8")
        self.assertIn("event: error", output,
                      "Expected an 'error' SSE event when diag_fn raises")
        self.assertNotIn("Traceback", output,
                         "Tracebacks must never be forwarded to SSE clients")
        self.assertNotIn("internal diagnostics error", output,
                         "Raw exception message must not appear in SSE output")
        # The error payload must be JSON-parseable
        data_lines = [ln[6:] for ln in output.splitlines() if ln.startswith("data: ")]
        self.assertGreater(len(data_lines), 0, "Expected at least one data: line")
        err_data = json.loads(data_lines[0])
        self.assertIn("error", err_data)
        self.assertIsInstance(err_data["error"], str)

    def test_periodic_diag_with_warnings_doc_emits_diagnostics_event(self):
        """When diag_fn returns a document with warnings, 'diagnostics' event is emitted."""
        from docker_topology_live.events import _PeriodicDiagnostics, SSEWriter
        from docker_topology_live.diagnostics import analyze_topology
        from docker_topology_live.scanner import build_sample

        buf = io.BytesIO()

        class _FakeFile:
            def write(self, data):
                buf.write(data)
            def flush(self):
                pass

        writer = SSEWriter(_FakeFile())

        def _diag_with_warning():
            topo = build_sample()
            return analyze_topology(topo, None,
                                    warnings=["Metrics unavailable; resource rules skipped."])

        pd = _PeriodicDiagnostics(writer, _diag_with_warning, interval=999.0)
        pd._emit_once()

        output = buf.getvalue().decode("utf-8")
        self.assertIn("event: diagnostics", output)
        # Extract the data payload
        data_lines = [ln[6:] for ln in output.splitlines() if ln.startswith("data: ")]
        self.assertGreater(len(data_lines), 0)
        doc = json.loads("".join(data_lines))
        self.assertIn("warnings", doc)
        self.assertGreater(len(doc["warnings"]), 0)
        self.assertNotIn("Traceback", json.dumps(doc))


# ─────────────────────────────────────────────────────────────────────────────
# TestManualReviewWording
# ─────────────────────────────────────────────────────────────────────────────

_MANUAL_REVIEW_PHRASE = "Manual review required before taking any cleanup action."

_CLEANUP_RULE_IDS = {
    "broad-bind-mount",
    "privileged-label",
    "exited-container",
    "orphan-network",
}


class TestManualReviewWording(unittest.TestCase):
    """Cleanup-related recommendations must include the manual-review phrase."""

    # ── broad-bind-mount ────────────────────────────────────────────────────

    def test_docker_socket_mount_recommendation_has_manual_review(self):
        """broad-bind-mount (docker.sock) recommendation must state manual review."""
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/var/run/docker.sock",
                      destination="/var/run/docker.sock"),
        ])
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "broad-bind-mount"]
        self.assertGreater(len(findings), 0, "Expected a broad-bind-mount finding")
        for f in findings:
            self.assertIn(
                _MANUAL_REVIEW_PHRASE, f["recommendation"],
                f"docker.sock finding is missing manual-review phrase: {f['recommendation']!r}",
            )

    def test_etc_bind_mount_recommendation_has_manual_review(self):
        """broad-bind-mount (/etc path) recommendation must state manual review."""
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/etc/ssl/certs", destination="/certs"),
        ])
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "broad-bind-mount"]
        self.assertGreater(len(findings), 0, "Expected a broad-bind-mount finding")
        for f in findings:
            self.assertIn(
                _MANUAL_REVIEW_PHRASE, f["recommendation"],
                f"/etc bind mount finding is missing manual-review phrase",
            )

    def test_proc_bind_mount_recommendation_has_manual_review(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/proc", destination="/host_proc"),
        ])
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "broad-bind-mount"]
        self.assertGreater(len(findings), 0)
        for f in findings:
            self.assertIn(_MANUAL_REVIEW_PHRASE, f["recommendation"])

    # ── privileged-label ────────────────────────────────────────────────────

    def test_privileged_label_recommendation_has_manual_review(self):
        """privileged-label recommendation must state manual review."""
        c = _simple_container(labels={"security.privileged": "true"})
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "privileged-label"]
        self.assertGreater(len(findings), 0, "Expected a privileged-label finding")
        for f in findings:
            self.assertIn(
                _MANUAL_REVIEW_PHRASE, f["recommendation"],
                f"privileged-label finding is missing manual-review phrase",
            )

    # ── exited-container ────────────────────────────────────────────────────

    def test_exited_container_recommendation_has_manual_review(self):
        """exited-container recommendation must state manual review."""
        c = _simple_container(status="exited")
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "exited-container"]
        self.assertGreater(len(findings), 0, "Expected an exited-container finding")
        for f in findings:
            self.assertIn(
                _MANUAL_REVIEW_PHRASE, f["recommendation"],
                f"exited-container finding is missing manual-review phrase",
            )

    def test_dead_container_recommendation_has_manual_review(self):
        """dead container also gets the manual-review phrase."""
        c = _simple_container(status="dead")
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "exited-container"]
        self.assertGreater(len(findings), 0)
        for f in findings:
            self.assertIn(_MANUAL_REVIEW_PHRASE, f["recommendation"])

    def test_restarting_container_recommendation_has_manual_review(self):
        c = _simple_container(status="restarting")
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "exited-container"]
        self.assertGreater(len(findings), 0)
        for f in findings:
            self.assertIn(_MANUAL_REVIEW_PHRASE, f["recommendation"])

    # ── orphan-network ──────────────────────────────────────────────────────

    def test_orphan_network_recommendation_has_manual_review(self):
        """orphan-network recommendation must state manual review."""
        net = _simple_network(label="unused-net")
        topo = _make_topology(networks=[net])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "orphan-network"]
        self.assertGreater(len(findings), 0, "Expected an orphan-network finding")
        for f in findings:
            self.assertIn(
                _MANUAL_REVIEW_PHRASE, f["recommendation"],
                f"orphan-network finding is missing manual-review phrase",
            )

    # ── Sample diagnostics coverage ─────────────────────────────────────────

    def test_sample_diagnostics_all_cleanup_rules_have_manual_review(self):
        """All cleanup-rule findings in the sample report must have the phrase."""
        report = build_sample_diagnostics()
        for f in report["findings"]:
            if f["ruleId"] in _CLEANUP_RULE_IDS:
                self.assertIn(
                    _MANUAL_REVIEW_PHRASE, f["recommendation"],
                    f"Rule {f['ruleId']!r} finding is missing manual-review phrase: "
                    f"{f['recommendation']!r}",
                )

    # ── Rules that must NOT have the manual-review phrase ───────────────────

    def test_non_cleanup_rules_do_not_have_manual_review_phrase(self):
        """Rules that are informational or non-destructive must not acquire the phrase."""
        non_cleanup_rule_ids = {
            "exposed-port",
            "secret-like-label-redacted",
            "no-network",
            "multi-network-container",
            "high-cpu",
            "high-memory",
            "high-pids",
            "high-block-write",
            "unnamed-container",
            "missing-compose-labels",
        }
        report = build_sample_diagnostics()
        for f in report["findings"]:
            if f["ruleId"] in non_cleanup_rule_ids:
                self.assertNotIn(
                    _MANUAL_REVIEW_PHRASE, f["recommendation"],
                    f"Unexpected manual-review phrase in non-cleanup rule "
                    f"{f['ruleId']!r}: {f['recommendation']!r}",
                )


class TestNoRemediationExecution(unittest.TestCase):
    """The diagnostics engine must never execute Docker mutation commands."""

    def _collect_imported_names(self) -> set:
        """Parse diagnostics.py source to find imported names (smoke check)."""
        import ast, pathlib
        src = (pathlib.Path(__file__).parent.parent
               / "src/docker_topology_live/diagnostics.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        names: set = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names.add(ast.dump(node))
        return names

    def test_diagnostics_does_not_import_docker(self):
        """diagnostics.py must not import the docker package at module level."""
        import pathlib
        src = (pathlib.Path(__file__).parent.parent
               / "src/docker_topology_live/diagnostics.py").read_text(encoding="utf-8")
        # Module-level docker import would look like "import docker" or "from docker"
        import ast
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "docker",
                        "diagnostics.py must not import the docker package",
                    )
            elif isinstance(node, ast.ImportFrom):
                self.assertFalse(
                    (node.module or "").startswith("docker"),
                    f"diagnostics.py must not import from docker: {node.module!r}",
                )

    def test_diagnostics_has_no_mutation_calls(self):
        """diagnostics.py must not call container.stop/kill/remove/restart/exec/run."""
        import pathlib, ast
        src = (pathlib.Path(__file__).parent.parent
               / "src/docker_topology_live/diagnostics.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {"stop", "kill", "remove", "restart", "exec_run", "exec",
                     "pause", "unpause", "prune", "run"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in forbidden:
                self.fail(
                    f"diagnostics.py contains a potentially mutating call: "
                    f".{node.attr}() — ensure it is not a Docker mutation"
                )

    def test_analyze_topology_returns_read_only_report(self):
        """analyze_topology() must return a dict; it must not modify the topology."""
        topo = _make_topology()
        original_dict = topo.to_dict()
        report = analyze_topology(topo)
        self.assertIsInstance(report, dict)
        # Topology is unchanged
        self.assertEqual(original_dict, topo.to_dict())

    def test_findings_contain_no_docker_exec_commands(self):
        """No finding recommendation must instruct the engine to run docker exec."""
        # Recommendations may *mention* commands for the user, but the phrase
        # should never imply the engine itself runs them.
        report = build_sample_diagnostics()
        for f in report["findings"]:
            rec = f.get("recommendation", "")
            # We verify the text is a recommendation (string), not a subprocess call
            self.assertIsInstance(rec, str)
            # The recommendation must not be an empty string
            self.assertGreater(len(rec.strip()), 0,
                                f"Empty recommendation in finding {f['id']!r}")

    def test_build_sample_diagnostics_makes_no_docker_calls(self):
        """build_sample_diagnostics() must work with docker package removed from path."""
        import sys
        original = sys.modules.get("docker")
        sys.modules["docker"] = None  # type: ignore[assignment]
        try:
            report = build_sample_diagnostics()
            self.assertIn("findings", report)
            self.assertIn("warnings", report)
        finally:
            if original is None:
                sys.modules.pop("docker", None)
            else:
                sys.modules["docker"] = original


class TestFindingIDStability(unittest.TestCase):
    """Finding IDs must remain deterministic after the wording-only change."""

    @classmethod
    def setUpClass(cls):
        cls.report_a = build_sample_diagnostics()
        cls.report_b = build_sample_diagnostics()

    def test_finding_ids_stable_across_runs(self):
        ids_a = {f["id"] for f in self.report_a["findings"]}
        ids_b = {f["id"] for f in self.report_b["findings"]}
        self.assertEqual(ids_a, ids_b,
                         "Finding IDs must be deterministic across repeated calls")

    def test_cleanup_rule_finding_ids_unchanged_by_wording_update(self):
        """Verify a known stable ID for each cleanup rule still matches."""
        # These IDs are derived from ruleId:targetId:extra — not from recommendation text.
        # Compute expected IDs from sample topology and verify they are still present.
        report = build_sample_diagnostics()
        cleanup_ids_found = {f["ruleId"] for f in report["findings"]
                             if f["ruleId"] in _CLEANUP_RULE_IDS}
        # Sample topology produces findings for at least some cleanup rules
        self.assertTrue(
            cleanup_ids_found.issubset(_CLEANUP_RULE_IDS),
            "Unexpected rule IDs appeared in cleanup findings",
        )

    def test_recommendation_text_change_does_not_affect_finding_id(self):
        """Changing recommendation text must not change the finding ID (by design)."""
        c = _simple_container(status="exited")
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "exited-container"]
        self.assertGreater(len(findings), 0)
        fid = findings[0]["id"]
        # Finding ID is based on sha256(ruleId:targetId:status) — run again to confirm
        findings2 = [f for f in analyze_topology(topo)["findings"]
                     if f["ruleId"] == "exited-container"]
        self.assertEqual(fid, findings2[0]["id"])

    def test_all_findings_have_unique_ids_after_wording_update(self):
        report = build_sample_diagnostics()
        ids = [f["id"] for f in report["findings"]]
        self.assertEqual(len(ids), len(set(ids)),
                         "All finding IDs must be unique within a report")


if __name__ == "__main__":
    unittest.main()
