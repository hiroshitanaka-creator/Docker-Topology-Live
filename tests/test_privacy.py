"""Comprehensive tests for the privacy-redact-mount-sources feature.

Covers:
  - _categorize_mount_source() in scanner.py
  - MountInfo.source_redacted / source_category fields and to_dict() serialisation
  - _parse_mounts(redact_host_paths=...) updated signature
  - scan_live(redact_host_paths=...) new parameter
  - build_sample(redact_host_paths=...) new parameter
  - _rule_broad_bind_mount updated to work with redacted mounts
  - CLI --redact-host-paths flag on sample / diagnose subcommands
  - Server make_handler(redact_host_paths=...) and GET /api/topology
  - Named volumes never redacted
  - Web UI: no .innerHTML = assignment in app.js

All tests run without a live Docker daemon.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import MagicMock

# ── Ensure the package is importable regardless of install state ──────────────
_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from docker_topology_live.models import (
    MountInfo,
    PortMapping,
    Topology,
    TopologyLink,
    TopologyNode,
)

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")

# ── Topology builder helpers (mirrors test_diagnostics.py conventions) ────────

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


def _link(container_id, network_id) -> TopologyLink:
    return TopologyLink(source=container_id, target=network_id, kind="attached-to")


def _make_handler_and_call(path="/api/topology", use_sample=True, redact_host_paths=False,
                            allow_cors=False):
    """Create a handler via make_handler and simulate a GET request, returning the JSON body."""
    from docker_topology_live.server import make_handler
    HandlerCls = make_handler(
        use_sample=use_sample,
        allow_cors=allow_cors,
        redact_host_paths=redact_host_paths,
    )
    handler = HandlerCls.__new__(HandlerCls)
    handler.path = path
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = io.BytesIO()
    handler.do_GET()
    body = handler.wfile.getvalue()
    return json.loads(body.decode())


# =============================================================================
# TestSourceCategorization
# =============================================================================

class TestSourceCategorization(unittest.TestCase):
    """_categorize_mount_source() must return the correct category for every input."""

    def _cat(self, source: str) -> str:
        from docker_topology_live.scanner import _categorize_mount_source
        return _categorize_mount_source(source)

    # docker-socket ─────────────────────────────────────────────────────────

    def test_docker_sock_is_docker_socket(self):
        self.assertEqual(self._cat("/var/run/docker.sock"), "docker-socket")

    # root ──────────────────────────────────────────────────────────────────

    def test_root_slash_is_root(self):
        self.assertEqual(self._cat("/"), "root")

    # system ────────────────────────────────────────────────────────────────

    def test_etc_prefix_is_system(self):
        self.assertEqual(self._cat("/etc/ssl/certs"), "system")

    def test_etc_bare_is_system(self):
        self.assertEqual(self._cat("/etc"), "system")

    def test_proc_prefix_is_system(self):
        self.assertEqual(self._cat("/proc/net"), "system")

    def test_proc_bare_is_system(self):
        self.assertEqual(self._cat("/proc"), "system")

    def test_sys_prefix_is_system(self):
        self.assertEqual(self._cat("/sys/kernel"), "system")

    def test_sys_bare_is_system(self):
        self.assertEqual(self._cat("/sys"), "system")

    def test_var_run_prefix_is_system(self):
        # /var/run/* other than docker.sock is still system
        self.assertEqual(self._cat("/var/run/containerd"), "system")

    def test_var_run_bare_is_system(self):
        self.assertEqual(self._cat("/var/run"), "system")

    def test_root_home_is_system(self):
        self.assertEqual(self._cat("/root"), "system")

    def test_root_home_subdirectory_is_system(self):
        self.assertEqual(self._cat("/root/.ssh"), "system")

    # home ──────────────────────────────────────────────────────────────────

    def test_home_user_is_home(self):
        self.assertEqual(self._cat("/home/alice"), "home")

    def test_home_bare_is_home(self):
        self.assertEqual(self._cat("/home"), "home")

    def test_users_mac_is_home(self):
        self.assertEqual(self._cat("/Users/bob/projects"), "home")

    def test_users_bare_is_home(self):
        self.assertEqual(self._cat("/Users"), "home")

    # absolute-path ─────────────────────────────────────────────────────────

    def test_app_data_is_absolute_path(self):
        self.assertEqual(self._cat("/myapp/data"), "absolute-path")

    def test_tmp_is_absolute_path(self):
        self.assertEqual(self._cat("/tmp"), "absolute-path")

    def test_srv_is_absolute_path(self):
        self.assertEqual(self._cat("/srv/www"), "absolute-path")

    def test_opt_is_absolute_path(self):
        self.assertEqual(self._cat("/opt/myapp"), "absolute-path")

    # named-volume ──────────────────────────────────────────────────────────

    def test_named_volume_no_slash_is_named_volume(self):
        self.assertEqual(self._cat("demo_pgdata"), "named-volume")

    def test_named_volume_with_underscore_is_named_volume(self):
        self.assertEqual(self._cat("my_volume"), "named-volume")

    def test_named_volume_alphanumeric_is_named_volume(self):
        self.assertEqual(self._cat("myvolume123"), "named-volume")

    # unknown ───────────────────────────────────────────────────────────────

    def test_empty_string_is_unknown(self):
        self.assertEqual(self._cat(""), "unknown")


# =============================================================================
# TestMountInfoToDict
# =============================================================================

class TestMountInfoToDict(unittest.TestCase):
    """MountInfo.to_dict() serialisation of new privacy fields."""

    def test_source_redacted_true_present_in_dict(self):
        m = MountInfo(
            type="bind",
            destination="/app/certs",
            mode="ro",
            rw=False,
            source="[redacted]",
            source_redacted=True,
            source_category="system",
        )
        d = m.to_dict()
        self.assertTrue(d.get("sourceRedacted"), "sourceRedacted should be True")

    def test_source_redacted_false_not_in_dict(self):
        m = MountInfo(
            type="bind",
            destination="/app/certs",
            mode="ro",
            rw=False,
            source="/etc/ssl/certs",
            source_redacted=False,
        )
        d = m.to_dict()
        self.assertNotIn("sourceRedacted", d,
                         "sourceRedacted should not appear when False")

    def test_source_redacted_defaults_to_false(self):
        m = MountInfo(type="bind", destination="/data", mode="", rw=True, source="/data")
        d = m.to_dict()
        self.assertNotIn("sourceRedacted", d)

    def test_source_category_present_when_set(self):
        m = MountInfo(
            type="bind",
            destination="/app/certs",
            mode="ro",
            rw=False,
            source="[redacted]",
            source_redacted=True,
            source_category="system",
        )
        d = m.to_dict()
        self.assertEqual(d.get("sourceCategory"), "system")

    def test_source_category_absent_when_none(self):
        m = MountInfo(type="bind", destination="/data", mode="", rw=True, source="/data")
        d = m.to_dict()
        self.assertNotIn("sourceCategory", d,
                         "sourceCategory should not appear when None")

    def test_source_is_redacted_sentinel_when_redacted(self):
        m = MountInfo(
            type="bind",
            destination="/data",
            mode="",
            rw=True,
            source="[redacted]",
            source_redacted=True,
            source_category="absolute-path",
        )
        d = m.to_dict()
        self.assertEqual(d["source"], "[redacted]")

    def test_volume_mount_has_no_source_category_by_default(self):
        m = MountInfo(
            type="volume",
            destination="/var/lib/postgresql/data",
            mode="z",
            rw=True,
            source="demo_pgdata",
        )
        d = m.to_dict()
        self.assertNotIn("sourceCategory", d)
        self.assertNotIn("sourceRedacted", d)

    def test_source_category_docker_socket(self):
        m = MountInfo(
            type="bind",
            destination="/var/run/docker.sock",
            mode="rw",
            rw=True,
            source="[redacted]",
            source_redacted=True,
            source_category="docker-socket",
        )
        d = m.to_dict()
        self.assertEqual(d["sourceCategory"], "docker-socket")
        self.assertTrue(d["sourceRedacted"])


# =============================================================================
# TestNoRedactionByDefault
# =============================================================================

class TestNoRedactionByDefault(unittest.TestCase):
    """build_sample() and scan_live() must not redact mount sources by default."""

    def test_build_sample_default_has_raw_source(self):
        from docker_topology_live.scanner import build_sample
        topo = build_sample()
        api_node = next(
            (n for n in topo.nodes if n.label == "api" and n.kind == "container"),
            None,
        )
        self.assertIsNotNone(api_node, "Expected 'api' container in sample topology")
        bind_mounts = [m for m in api_node.mounts if m.type == "bind"]
        self.assertGreater(len(bind_mounts), 0, "api container should have bind mounts")
        for m in bind_mounts:
            self.assertNotEqual(m.source, "[redacted]",
                                "Default build_sample() must not redact sources")

    def test_build_sample_default_source_redacted_is_false(self):
        from docker_topology_live.scanner import build_sample
        topo = build_sample()
        for node in topo.nodes:
            if node.kind != "container":
                continue
            for m in node.mounts:
                self.assertFalse(
                    getattr(m, "source_redacted", False),
                    f"source_redacted should be False by default on {node.label}.{m.destination}",
                )

    def test_build_sample_volume_mounts_not_redacted_even_with_flag(self):
        from docker_topology_live.scanner import build_sample
        topo = build_sample(redact_host_paths=True)
        for node in topo.nodes:
            if node.kind != "container":
                continue
            for m in node.mounts:
                if m.type == "volume":
                    self.assertFalse(
                        getattr(m, "source_redacted", False),
                        f"Volume mount should never be redacted: {node.label}.{m.destination}",
                    )
                    self.assertNotEqual(m.source, "[redacted]",
                                        "Volume mount source must not be replaced with sentinel")


# =============================================================================
# TestBuildSampleRedaction
# =============================================================================

class TestBuildSampleRedaction(unittest.TestCase):
    """build_sample(redact_host_paths=True) must redact bind mount sources."""

    @classmethod
    def setUpClass(cls):
        from docker_topology_live.scanner import build_sample
        cls.topo = build_sample(redact_host_paths=True)

    def _api_bind_mounts(self):
        api_node = next(
            (n for n in self.topo.nodes if n.label == "api" and n.kind == "container"),
            None,
        )
        self.assertIsNotNone(api_node, "Expected 'api' container in sample topology")
        return [m for m in api_node.mounts if m.type == "bind"]

    def test_bind_mount_source_is_sentinel(self):
        for m in self._api_bind_mounts():
            self.assertEqual(m.source, "[redacted]",
                             "Bind mount source must be '[redacted]' when flag is True")

    def test_bind_mount_source_redacted_is_true(self):
        for m in self._api_bind_mounts():
            self.assertTrue(
                getattr(m, "source_redacted", False),
                "source_redacted must be True on redacted bind mount",
            )

    def test_bind_mount_source_category_is_system(self):
        for m in self._api_bind_mounts():
            self.assertEqual(
                getattr(m, "source_category", None),
                "system",
                "api bind mount from /etc/ssl/certs should be categorised as 'system'",
            )

    def test_volume_mount_intact(self):
        """Volume mounts must not be touched even with redact_host_paths=True."""
        for node in self.topo.nodes:
            if node.kind != "container":
                continue
            for m in node.mounts:
                if m.type == "volume":
                    self.assertNotEqual(m.source, "[redacted]",
                                        f"Volume mount on {node.label} must not be redacted")
                    self.assertFalse(
                        getattr(m, "source_redacted", False),
                        f"source_redacted must be False on volume mount {node.label}.{m.destination}",
                    )

    def test_to_dict_has_source_redacted_true(self):
        d = self.topo.to_dict()
        api_dict = next(
            (n for n in d["nodes"] if n.get("label") == "api" and n.get("kind") == "container"),
            None,
        )
        self.assertIsNotNone(api_dict)
        bind_mount_dicts = [m for m in api_dict.get("mounts", []) if m.get("type") == "bind"]
        self.assertGreater(len(bind_mount_dicts), 0)
        for md in bind_mount_dicts:
            self.assertTrue(md.get("sourceRedacted"),
                            "sourceRedacted must be True in to_dict() output")

    def test_to_dict_has_source_category(self):
        d = self.topo.to_dict()
        api_dict = next(
            (n for n in d["nodes"] if n.get("label") == "api" and n.get("kind") == "container"),
            None,
        )
        bind_mount_dicts = [m for m in api_dict.get("mounts", []) if m.get("type") == "bind"]
        for md in bind_mount_dicts:
            self.assertIn("sourceCategory", md,
                          "sourceCategory must appear in to_dict() when set")

    def test_to_dict_source_is_sentinel_string(self):
        d = self.topo.to_dict()
        api_dict = next(
            (n for n in d["nodes"] if n.get("label") == "api" and n.get("kind") == "container"),
            None,
        )
        bind_mount_dicts = [m for m in api_dict.get("mounts", []) if m.get("type") == "bind"]
        for md in bind_mount_dicts:
            self.assertEqual(md.get("source"), "[redacted]")


# =============================================================================
# TestBuildSampleNoRedaction
# =============================================================================

class TestBuildSampleNoRedaction(unittest.TestCase):
    """build_sample() without flag must have raw source but still compute category."""

    @classmethod
    def setUpClass(cls):
        from docker_topology_live.scanner import build_sample
        cls.topo = build_sample()

    def _api_bind_mounts(self):
        api_node = next(
            (n for n in self.topo.nodes if n.label == "api" and n.kind == "container"),
            None,
        )
        self.assertIsNotNone(api_node)
        return [m for m in api_node.mounts if m.type == "bind"]

    def test_source_is_real_path(self):
        for m in self._api_bind_mounts():
            self.assertEqual(m.source, "/etc/ssl/certs",
                             "Without redaction flag, source must remain real path")

    def test_source_redacted_is_false(self):
        for m in self._api_bind_mounts():
            self.assertFalse(
                getattr(m, "source_redacted", False),
                "source_redacted must be False when redact_host_paths is not set",
            )

    def test_source_category_is_system(self):
        """Category should be computed even without redaction."""
        for m in self._api_bind_mounts():
            self.assertEqual(
                getattr(m, "source_category", None),
                "system",
                "Category should be 'system' for /etc/ssl/certs even without redaction",
            )

    def test_to_dict_source_redacted_absent(self):
        d = self.topo.to_dict()
        api_dict = next(
            (n for n in d["nodes"] if n.get("label") == "api" and n.get("kind") == "container"),
            None,
        )
        bind_mount_dicts = [m for m in api_dict.get("mounts", []) if m.get("type") == "bind"]
        for md in bind_mount_dicts:
            self.assertNotIn(
                "sourceRedacted", md,
                "sourceRedacted must not appear in dict when False",
            )


# =============================================================================
# TestBroadBindMountDiagnosticsWithRedaction
# =============================================================================

class TestBroadBindMountDiagnosticsWithRedaction(unittest.TestCase):
    """_rule_broad_bind_mount adapted to handle redacted mounts correctly."""

    def _run(self, container):
        from docker_topology_live.diagnostics import analyze_topology
        topo = _make_topology(containers=[container])
        return [f for f in analyze_topology(topo)["findings"]
                if f["ruleId"] == "broad-bind-mount"]

    def _redacted_mount(self, destination, source_category):
        """Build a MountInfo that simulates a redacted bind mount."""
        return MountInfo(
            type="bind",
            destination=destination,
            mode="ro",
            rw=False,
            source="[redacted]",
            source_redacted=True,
            source_category=source_category,
        )

    def test_redacted_docker_socket_is_high(self):
        c = _simple_container(mounts=[
            self._redacted_mount("/var/run/docker.sock", "docker-socket")
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1, "Expected exactly one broad-bind-mount finding")
        self.assertEqual(findings[0]["severity"], "high")

    def test_redacted_system_is_medium(self):
        c = _simple_container(mounts=[
            self._redacted_mount("/app/certs", "system")
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_redacted_root_is_medium(self):
        c = _simple_container(mounts=[
            self._redacted_mount("/host", "root")
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_redacted_home_is_medium(self):
        c = _simple_container(mounts=[
            self._redacted_mount("/data", "home")
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_redacted_absolute_path_is_skipped(self):
        """absolute-path category with redacted source should be skipped (not sensitive enough)."""
        c = _simple_container(mounts=[
            self._redacted_mount("/config", "absolute-path")
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 0,
                         "absolute-path category should not produce a finding when redacted")

    def test_evidence_excludes_raw_source_when_redacted(self):
        c = _simple_container(mounts=[
            self._redacted_mount("/app/certs", "system")
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        evidence = findings[0]["evidence"]
        # Raw source path must not appear
        self.assertNotEqual(evidence.get("source"), "/etc/ssl/certs")
        self.assertNotEqual(evidence.get("source"), "/home/alice")
        # Must not contain any real path in the source field
        source_val = evidence.get("source", "")
        self.assertFalse(
            source_val.startswith("/") and source_val != "[redacted]",
            f"evidence.source must not be a raw path when redacted, got: {source_val!r}",
        )

    def test_evidence_includes_source_redacted_flag(self):
        c = _simple_container(mounts=[
            self._redacted_mount("/app/certs", "system")
        ])
        findings = self._run(c)
        evidence = findings[0]["evidence"]
        self.assertTrue(evidence.get("sourceRedacted"),
                        "evidence must include sourceRedacted: true when source is redacted")

    def test_evidence_includes_source_category(self):
        c = _simple_container(mounts=[
            self._redacted_mount("/app/certs", "system")
        ])
        findings = self._run(c)
        evidence = findings[0]["evidence"]
        self.assertEqual(evidence.get("sourceCategory"), "system",
                         "evidence must include sourceCategory when source is redacted")

    def test_finding_id_uses_destination_when_redacted(self):
        """Finding ID must be deterministic using destination when source is redacted."""
        c = _simple_container(mounts=[
            self._redacted_mount("/app/certs", "system")
        ])
        findings_a = self._run(c)
        findings_b = self._run(c)
        self.assertEqual(findings_a[0]["id"], findings_b[0]["id"],
                         "Finding ID must be deterministic when source is redacted")


# =============================================================================
# TestBroadBindMountDiagnosticsNoRedaction
# =============================================================================

class TestBroadBindMountDiagnosticsNoRedaction(unittest.TestCase):
    """Original broad-bind-mount behaviour preserved for non-redacted mounts."""

    def _run(self, container):
        from docker_topology_live.diagnostics import analyze_topology
        topo = _make_topology(containers=[container])
        return [f for f in analyze_topology(topo)["findings"]
                if f["ruleId"] == "broad-bind-mount"]

    def test_docker_sock_non_redacted_is_high(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/var/run/docker.sock",
                      destination="/var/run/docker.sock", mode="rw", rw=True)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_etc_path_non_redacted_is_medium(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/etc/ssl/certs",
                      destination="/certs", mode="ro", rw=False)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")

    def test_evidence_has_source_when_not_redacted(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/etc/ssl/certs",
                      destination="/certs", mode="ro", rw=False)
        ])
        findings = self._run(c)
        self.assertEqual(len(findings), 1)
        evidence = findings[0]["evidence"]
        self.assertEqual(evidence.get("source"), "/etc/ssl/certs",
                         "Raw source must appear in evidence when not redacted")

    def test_evidence_has_destination_when_not_redacted(self):
        c = _simple_container(mounts=[
            MountInfo(type="bind", source="/etc/ssl/certs",
                      destination="/certs", mode="ro", rw=False)
        ])
        findings = self._run(c)
        evidence = findings[0]["evidence"]
        self.assertEqual(evidence.get("destination"), "/certs")

    def test_finding_still_fires_non_redacted(self):
        """Verify findings are produced for all sensitive paths without redaction."""
        sensitive_paths = [
            "/var/run/docker.sock",
            "/etc/passwd",
            "/proc/net",
            "/sys/kernel",
            "/home/user",
            "/root/.ssh",
            "/",
        ]
        for src in sensitive_paths:
            with self.subTest(source=src):
                c = _simple_container(mounts=[
                    MountInfo(type="bind", source=src,
                              destination="/mount", mode="ro", rw=False)
                ])
                findings = self._run(c)
                self.assertGreater(
                    len(findings), 0,
                    f"Expected finding for sensitive path: {src!r}",
                )


# =============================================================================
# TestFindingIDUniquenessWhenRedacted
# =============================================================================

class TestFindingIDUniquenessWhenRedacted(unittest.TestCase):
    """Two different bind mounts on the same container (both redacted) must get different IDs."""

    def test_different_destinations_different_ids(self):
        from docker_topology_live.diagnostics import analyze_topology
        c = _simple_container(
            cid="container:aabbccddee00",
            mounts=[
                MountInfo(
                    type="bind",
                    destination="/app/certs",
                    mode="ro",
                    rw=False,
                    source="[redacted]",
                    source_redacted=True,
                    source_category="system",
                ),
                MountInfo(
                    type="bind",
                    destination="/var/run/docker.sock",
                    mode="rw",
                    rw=True,
                    source="[redacted]",
                    source_redacted=True,
                    source_category="docker-socket",
                ),
            ],
        )
        topo = _make_topology(containers=[c])
        findings = [f for f in analyze_topology(topo)["findings"]
                    if f["ruleId"] == "broad-bind-mount"]
        self.assertEqual(len(findings), 2, "Both redacted mounts should produce findings")
        ids = [f["id"] for f in findings]
        self.assertEqual(len(ids), len(set(ids)),
                         "Finding IDs must be unique even when both sources are redacted")

    def test_ids_are_deterministic_across_runs(self):
        from docker_topology_live.diagnostics import analyze_topology
        c = _simple_container(
            cid="container:aabbccddee00",
            mounts=[
                MountInfo(
                    type="bind",
                    destination="/app/certs",
                    mode="ro",
                    rw=False,
                    source="[redacted]",
                    source_redacted=True,
                    source_category="system",
                ),
            ],
        )
        topo = _make_topology(containers=[c])
        findings_a = [f for f in analyze_topology(topo)["findings"]
                      if f["ruleId"] == "broad-bind-mount"]
        findings_b = [f for f in analyze_topology(topo)["findings"]
                      if f["ruleId"] == "broad-bind-mount"]
        self.assertEqual(len(findings_a), 1)
        self.assertEqual(findings_a[0]["id"], findings_b[0]["id"])


# =============================================================================
# TestSampleDiagnosticsWithRedaction
# =============================================================================

class TestSampleDiagnosticsWithRedaction(unittest.TestCase):
    """build_sample(redact_host_paths=True) fed into analyze_topology produces correct output."""

    @classmethod
    def setUpClass(cls):
        from docker_topology_live.scanner import build_sample
        from docker_topology_live.diagnostics import analyze_topology
        topo = build_sample(redact_host_paths=True)
        cls.report = analyze_topology(topo)

    def test_broad_bind_mount_finding_present(self):
        ids = {f["ruleId"] for f in self.report["findings"]}
        self.assertIn("broad-bind-mount", ids,
                      "broad-bind-mount finding must still fire on redacted topology")

    def test_evidence_has_no_raw_path(self):
        for f in self.report["findings"]:
            if f["ruleId"] != "broad-bind-mount":
                continue
            evidence = f["evidence"]
            source_val = evidence.get("source", "")
            # source must be absent, "[redacted]", or not a raw path
            if source_val:
                self.assertFalse(
                    source_val.startswith("/") and source_val not in ("[redacted]",),
                    f"Raw host path appeared in evidence when redacted: {source_val!r}",
                )

    def test_evidence_has_source_redacted_true(self):
        for f in self.report["findings"]:
            if f["ruleId"] != "broad-bind-mount":
                continue
            evidence = f["evidence"]
            self.assertTrue(evidence.get("sourceRedacted"),
                            "evidence.sourceRedacted must be True")

    def test_report_is_json_serialisable(self):
        try:
            json.dumps(self.report)
        except (TypeError, ValueError) as exc:
            self.fail(f"Report is not JSON-serialisable: {exc}")

    def test_finding_ids_unique(self):
        ids = [f["id"] for f in self.report["findings"]]
        self.assertEqual(len(ids), len(set(ids)),
                         "Finding IDs must be unique in redacted diagnostics report")


# =============================================================================
# TestAPIEndpointRedaction
# =============================================================================

class TestAPIEndpointRedaction(unittest.TestCase):
    """GET /api/topology via make_handler reflects redact_host_paths setting."""

    def test_redact_true_produces_sentinel_source(self):
        data = _make_handler_and_call(
            path="/api/topology", use_sample=True, redact_host_paths=True
        )
        bind_mounts = []
        for node in data.get("nodes", []):
            if node.get("kind") == "container":
                for m in node.get("mounts", []):
                    if m.get("type") == "bind":
                        bind_mounts.append(m)
        self.assertGreater(len(bind_mounts), 0,
                           "Expected at least one bind mount in sample topology")
        for m in bind_mounts:
            self.assertEqual(m.get("source"), "[redacted]",
                             "Bind mount source must be '[redacted]' when redact_host_paths=True")

    def test_redact_true_has_source_redacted_flag(self):
        data = _make_handler_and_call(
            path="/api/topology", use_sample=True, redact_host_paths=True
        )
        for node in data.get("nodes", []):
            if node.get("kind") == "container":
                for m in node.get("mounts", []):
                    if m.get("type") == "bind":
                        self.assertTrue(m.get("sourceRedacted"),
                                        "sourceRedacted must be True in API response")

    def test_redact_false_produces_raw_source(self):
        data = _make_handler_and_call(
            path="/api/topology", use_sample=True, redact_host_paths=False
        )
        bind_mounts = []
        for node in data.get("nodes", []):
            if node.get("kind") == "container":
                for m in node.get("mounts", []):
                    if m.get("type") == "bind":
                        bind_mounts.append(m)
        self.assertGreater(len(bind_mounts), 0)
        for m in bind_mounts:
            source = m.get("source", "")
            self.assertNotEqual(source, "[redacted]",
                                "Source must not be sentinel when redact_host_paths=False")
            self.assertTrue(source.startswith("/"),
                            f"Source must be a real path, got: {source!r}")

    def test_redact_false_source_redacted_absent(self):
        data = _make_handler_and_call(
            path="/api/topology", use_sample=True, redact_host_paths=False
        )
        for node in data.get("nodes", []):
            if node.get("kind") == "container":
                for m in node.get("mounts", []):
                    if m.get("type") == "bind":
                        self.assertNotIn(
                            "sourceRedacted", m,
                            "sourceRedacted must not appear when redact_host_paths=False",
                        )

    def test_volume_mounts_never_redacted_in_api(self):
        data = _make_handler_and_call(
            path="/api/topology", use_sample=True, redact_host_paths=True
        )
        for node in data.get("nodes", []):
            if node.get("kind") == "container":
                for m in node.get("mounts", []):
                    if m.get("type") == "volume":
                        self.assertNotIn("sourceRedacted", m,
                                         "Volume mounts must not have sourceRedacted")
                        source = m.get("source", "")
                        self.assertNotEqual(source, "[redacted]",
                                            "Volume mount source must not be sentinel")


# =============================================================================
# TestCLISampleRedaction
# =============================================================================

class TestCLISampleRedaction(unittest.TestCase):
    """CLI `python app.py sample --redact-host-paths` must produce redacted JSON."""

    def _run_sample(self, *extra_args):
        env = {"PYTHONPATH": "src", "PATH": os.environ["PATH"]}
        return subprocess.run(
            [sys.executable, "app.py", "sample"] + list(extra_args),
            capture_output=True,
            text=True,
            cwd=_PROJECT_ROOT,
            env=env,
        )

    def test_sample_with_redact_flag_exits_zero(self):
        result = self._run_sample("--redact-host-paths")
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit code 0; got {result.returncode}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout[:500]}",
        )

    def test_sample_with_redact_flag_is_valid_json(self):
        result = self._run_sample("--redact-host-paths")
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"Output is not valid JSON: {exc}\nstdout: {result.stdout[:400]}")
        self.assertIn("nodes", data)

    def test_sample_with_redact_flag_has_source_redacted_true(self):
        result = self._run_sample("--redact-host-paths")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        bind_mounts = []
        for node in data.get("nodes", []):
            if node.get("kind") == "container":
                for m in node.get("mounts", []):
                    if m.get("type") == "bind":
                        bind_mounts.append(m)
        self.assertGreater(len(bind_mounts), 0)
        for m in bind_mounts:
            self.assertTrue(m.get("sourceRedacted"),
                            f"sourceRedacted must be True in CLI output: {m}")

    def test_sample_without_flag_has_raw_source(self):
        result = self._run_sample()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        bind_mounts = []
        for node in data.get("nodes", []):
            if node.get("kind") == "container":
                for m in node.get("mounts", []):
                    if m.get("type") == "bind":
                        bind_mounts.append(m)
        self.assertGreater(len(bind_mounts), 0)
        for m in bind_mounts:
            source = m.get("source", "")
            self.assertNotEqual(source, "[redacted]",
                                "Without flag, source must not be sentinel")

    def test_sample_with_redact_flag_source_is_sentinel(self):
        result = self._run_sample("--redact-host-paths")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        for node in data.get("nodes", []):
            if node.get("kind") == "container":
                for m in node.get("mounts", []):
                    if m.get("type") == "bind":
                        self.assertEqual(
                            m.get("source"), "[redacted]",
                            f"Expected '[redacted]' sentinel in CLI output, got: {m.get('source')!r}",
                        )


# =============================================================================
# TestCLIDiagnoseRedaction
# =============================================================================

class TestCLIDiagnoseRedaction(unittest.TestCase):
    """CLI `python app.py diagnose --sample --redact-host-paths` must produce valid redacted diagnostics."""

    def _run_diagnose(self, *extra_args):
        env = {"PYTHONPATH": "src", "PATH": os.environ["PATH"]}
        return subprocess.run(
            [sys.executable, "app.py", "diagnose", "--sample"] + list(extra_args),
            capture_output=True,
            text=True,
            cwd=_PROJECT_ROOT,
            env=env,
        )

    def test_diagnose_with_redact_flag_exits_zero(self):
        result = self._run_diagnose("--redact-host-paths")
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit code 0; got {result.returncode}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout[:500]}",
        )

    def test_diagnose_with_redact_flag_is_valid_json(self):
        result = self._run_diagnose("--redact-host-paths")
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"Output is not valid JSON: {exc}\nstdout: {result.stdout[:400]}")
        self.assertIn("findings", data)
        self.assertIn("summary", data)
        self.assertIn("schemaVersion", data)

    def test_diagnose_with_redact_flag_broad_bind_mount_fires(self):
        result = self._run_diagnose("--redact-host-paths")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        rule_ids = {f["ruleId"] for f in data.get("findings", [])}
        self.assertIn("broad-bind-mount", rule_ids,
                      "broad-bind-mount must fire even with redacted sources")

    def test_diagnose_with_redact_flag_no_raw_path_in_evidence(self):
        result = self._run_diagnose("--redact-host-paths")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        for f in data.get("findings", []):
            if f["ruleId"] != "broad-bind-mount":
                continue
            evidence = f.get("evidence", {})
            source_val = evidence.get("source", "")
            if source_val:
                self.assertFalse(
                    source_val.startswith("/") and source_val not in ("[redacted]",),
                    f"Raw host path in evidence when flag set: {source_val!r}",
                )

    def test_diagnose_without_redact_flag_has_raw_path(self):
        result = self._run_diagnose()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        bind_findings = [f for f in data.get("findings", [])
                         if f["ruleId"] == "broad-bind-mount"]
        self.assertGreater(len(bind_findings), 0)
        for f in bind_findings:
            source_val = f.get("evidence", {}).get("source", "")
            self.assertTrue(
                source_val.startswith("/"),
                f"Expected raw path in evidence without redaction flag, got: {source_val!r}",
            )


# =============================================================================
# TestNamedVolumesNotRedacted
# =============================================================================

class TestNamedVolumesNotRedacted(unittest.TestCase):
    """Named and anonymous volumes must never be redacted regardless of flag."""

    def test_named_volume_source_intact_with_flag(self):
        from docker_topology_live.scanner import build_sample
        topo = build_sample(redact_host_paths=True)
        db_node = next(
            (n for n in topo.nodes if n.label == "db" and n.kind == "container"),
            None,
        )
        self.assertIsNotNone(db_node, "Expected 'db' container in sample topology")
        volume_mounts = [m for m in db_node.mounts if m.type == "volume"]
        self.assertGreater(len(volume_mounts), 0, "Expected volume mount on db container")
        for m in volume_mounts:
            self.assertNotEqual(m.source, "[redacted]",
                                "Named volume source must not be replaced with sentinel")
            self.assertFalse(
                getattr(m, "source_redacted", False),
                "source_redacted must be False on named volume",
            )

    def test_volume_mount_no_source_redacted_in_dict(self):
        from docker_topology_live.scanner import build_sample
        topo = build_sample(redact_host_paths=True)
        d = topo.to_dict()
        for node in d.get("nodes", []):
            if node.get("kind") == "container":
                for m in node.get("mounts", []):
                    if m.get("type") == "volume":
                        self.assertNotIn(
                            "sourceRedacted", m,
                            f"sourceRedacted must not appear for volume mount: {m}",
                        )

    def test_parse_mounts_volume_not_redacted(self):
        from docker_topology_live.scanner import _parse_mounts
        attrs = {
            "Mounts": [
                {
                    "Type": "volume",
                    "Source": "demo_pgdata",
                    "Destination": "/var/lib/postgresql/data",
                    "Mode": "z",
                    "RW": True,
                }
            ]
        }
        mounts = _parse_mounts(attrs, redact_host_paths=True)
        self.assertEqual(len(mounts), 1)
        self.assertNotEqual(mounts[0].source, "[redacted]")
        self.assertFalse(getattr(mounts[0], "source_redacted", False))

    def test_parse_mounts_bind_redacted_volume_not(self):
        from docker_topology_live.scanner import _parse_mounts
        attrs = {
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/etc/ssl/certs",
                    "Destination": "/certs",
                    "Mode": "ro",
                    "RW": False,
                },
                {
                    "Type": "volume",
                    "Source": "demo_pgdata",
                    "Destination": "/data",
                    "Mode": "z",
                    "RW": True,
                },
            ]
        }
        mounts = _parse_mounts(attrs, redact_host_paths=True)
        self.assertEqual(len(mounts), 2)
        bind_m = next(m for m in mounts if m.type == "bind")
        vol_m = next(m for m in mounts if m.type == "volume")
        self.assertEqual(bind_m.source, "[redacted]")
        self.assertTrue(getattr(bind_m, "source_redacted", False))
        self.assertEqual(vol_m.source, "demo_pgdata")
        self.assertFalse(getattr(vol_m, "source_redacted", False))


# =============================================================================
# TestParseMountsSignature
# =============================================================================

class TestParseMountsSignature(unittest.TestCase):
    """_parse_mounts() must accept redact_host_paths kwarg."""

    def test_parse_mounts_accepts_redact_false(self):
        from docker_topology_live.scanner import _parse_mounts
        attrs = {
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/etc/ssl/certs",
                    "Destination": "/certs",
                    "Mode": "ro",
                    "RW": False,
                }
            ]
        }
        # Must not raise
        mounts = _parse_mounts(attrs, redact_host_paths=False)
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0].source, "/etc/ssl/certs")

    def test_parse_mounts_accepts_redact_true(self):
        from docker_topology_live.scanner import _parse_mounts
        attrs = {
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/etc/ssl/certs",
                    "Destination": "/certs",
                    "Mode": "ro",
                    "RW": False,
                }
            ]
        }
        mounts = _parse_mounts(attrs, redact_host_paths=True)
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0].source, "[redacted]")
        self.assertTrue(getattr(mounts[0], "source_redacted", False))

    def test_parse_mounts_default_no_redact(self):
        """Default behaviour (no flag) must not redact."""
        from docker_topology_live.scanner import _parse_mounts
        attrs = {
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/home/alice/data",
                    "Destination": "/data",
                    "Mode": "rw",
                    "RW": True,
                }
            ]
        }
        mounts = _parse_mounts(attrs)
        self.assertEqual(mounts[0].source, "/home/alice/data")

    def test_parse_mounts_category_computed_for_bind_when_not_redacted(self):
        from docker_topology_live.scanner import _parse_mounts
        attrs = {
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/etc/ssl/certs",
                    "Destination": "/certs",
                    "Mode": "ro",
                    "RW": False,
                }
            ]
        }
        mounts = _parse_mounts(attrs, redact_host_paths=False)
        self.assertEqual(getattr(mounts[0], "source_category", None), "system")

    def test_parse_mounts_category_computed_docker_sock(self):
        from docker_topology_live.scanner import _parse_mounts
        attrs = {
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/var/run/docker.sock",
                    "Destination": "/var/run/docker.sock",
                    "Mode": "rw",
                    "RW": True,
                }
            ]
        }
        mounts = _parse_mounts(attrs, redact_host_paths=False)
        self.assertEqual(getattr(mounts[0], "source_category", None), "docker-socket")


# =============================================================================
# TestWebUINoInnerHTML
# =============================================================================

class TestWebUINoInnerHTML(unittest.TestCase):
    """app.js must not use .innerHTML assignments (XSS risk)."""

    @classmethod
    def setUpClass(cls):
        js_path = (
            pathlib.Path(__file__).parent.parent
            / "src/docker_topology_live/web/assets/app.js"
        )
        cls._js = js_path.read_text(encoding="utf-8")

    def test_no_inner_html_assignment(self):
        import re
        matches = re.findall(r'\.innerHTML\s*=', self._js)
        self.assertEqual(
            matches, [],
            f"innerHTML assignment(s) found in app.js: {matches}. "
            "Use textContent or DOM methods instead to prevent XSS.",
        )


if __name__ == "__main__":
    unittest.main()
