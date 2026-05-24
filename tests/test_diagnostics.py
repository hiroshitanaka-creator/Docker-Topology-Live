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


if __name__ == "__main__":
    unittest.main()
