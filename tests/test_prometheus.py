"""Tests for docker_topology_live.prometheus — Prometheus text exposition formatter.

All tests run without a real Docker daemon.

Coverage:
- escape_label_value: backslash, double-quote, newline, combined, empty, no-op
- format_prometheus_metrics:
  - output ends with newline
  - HELP and TYPE lines present for every declared metric
  - per-container gauges emitted
  - summary (containers_total, running_containers) emitted
  - metrics_warnings_total emitted
  - deterministic / stable ordering
  - empty metrics doc produces valid output
  - warnings count reflected in metrics_warnings_total
  - no raw traceback / Python exception text in output
  - no Docker labels, env vars, or mount paths in output
  - label values are escaped in the output
- PROMETHEUS_CONTENT_TYPE constant
"""
import re
import unittest

from docker_topology_live.prometheus import (
    PROMETHEUS_CONTENT_TYPE,
    escape_label_value,
    format_prometheus_metrics,
)

# ── Minimal sample metrics document ──────────────────────────────────────────

_SAMPLE_DOC = {
    "schemaVersion": "1.0",
    "generatedAt": "2024-01-15T12:00:00Z",
    "source": {"engine": "sample", "host": "demo"},
    "sample": True,
    "containers": [
        {
            "id": "container:abc123",
            "name": "web",
            "status": "running",
            "cpuPercent": 1.5,
            "memoryUsageBytes": 52428800,
            "memoryLimitBytes": 1073741824,
            "memoryPercent": 4.88,
            "networkRxBytes": 102400,
            "networkTxBytes": 204800,
            "blockReadBytes": 0,
            "blockWriteBytes": 4096,
            "pids": 5,
        },
        {
            "id": "container:def456",
            "name": "db",
            "status": "running",
            "cpuPercent": 32.1,
            "memoryUsageBytes": 209715200,
            "memoryLimitBytes": 1073741824,
            "memoryPercent": 19.53,
            "networkRxBytes": 512000,
            "networkTxBytes": 1024000,
            "blockReadBytes": 8192,
            "blockWriteBytes": 16384,
            "pids": 8,
        },
    ],
    "summary": {
        "containers": 2,
        "runningContainers": 2,
        "withMetrics": 2,
    },
    "warnings": [],
}

_EMPTY_DOC: dict = {
    "containers": [],
    "summary":    {},
    "warnings":   [],
}


# ── escape_label_value ────────────────────────────────────────────────────────

class TestEscapeLabelValue(unittest.TestCase):
    """escape_label_value must escape backslash, double-quote, and newline."""

    def test_no_op_for_plain_string(self):
        """Plain alphanumeric strings must pass through unchanged."""
        self.assertEqual(escape_label_value("hello"), "hello")

    def test_empty_string(self):
        self.assertEqual(escape_label_value(""), "")

    def test_backslash_escaped(self):
        result = escape_label_value("a\\b")
        self.assertEqual(result, "a\\\\b",
                         "backslash must be doubled: \\ → \\\\")

    def test_double_quote_escaped(self):
        result = escape_label_value('a"b')
        self.assertEqual(result, 'a\\"b',
                         'double-quote must become \\": " → \\"')

    def test_newline_escaped(self):
        result = escape_label_value("a\nb")
        self.assertEqual(result, "a\\nb",
                         r"newline must become literal \n: \n → \\n")

    def test_combined_escaping(self):
        """All three special characters in one string."""
        raw = 'back\\slash "quoted"\nnewline'
        result = escape_label_value(raw)
        # backslash first, then quote, then newline
        self.assertIn("\\\\", result, "backslash must be doubled")
        self.assertIn('\\"', result, "double-quote must be escaped")
        self.assertIn("\\n", result, r"newline must become \n")
        self.assertNotIn("\n", result, "no raw newlines must remain")

    def test_backslash_escaped_before_quote(self):
        """Ensure backslash is escaped before quote to avoid double-escaping."""
        raw = '\\"'  # backslash followed by double-quote
        result = escape_label_value(raw)
        # After correct escaping: \\ then \"  →  \\\\"
        self.assertTrue(
            result.startswith("\\\\"),
            "backslash must be doubled first; result: " + repr(result),
        )

    def test_unicode_passthrough(self):
        """Unicode characters not in the escape set must pass through."""
        self.assertEqual(escape_label_value("héllo"), "héllo")
        self.assertEqual(escape_label_value("🐳"), "🐳")


# ── format_prometheus_metrics — output structure ──────────────────────────────

class TestFormatPrometheusOutputStructure(unittest.TestCase):
    """Basic structural requirements of the Prometheus output."""

    def setUp(self):
        self.out = format_prometheus_metrics(_SAMPLE_DOC)

    def test_output_ends_with_newline(self):
        """Prometheus text format requires trailing newline."""
        self.assertTrue(
            self.out.endswith("\n"),
            "Output must end with a newline character",
        )

    def test_output_is_str(self):
        self.assertIsInstance(self.out, str)

    def test_output_not_empty(self):
        self.assertGreater(len(self.out), 0)

    def test_has_help_lines(self):
        """Output must contain HELP comment lines."""
        self.assertIn("# HELP", self.out, "HELP lines must be present")

    def test_has_type_lines(self):
        """Output must contain TYPE comment lines."""
        self.assertIn("# TYPE", self.out, "TYPE lines must be present")

    def test_all_type_lines_are_gauge(self):
        """All metrics are point-in-time gauges."""
        type_lines = [l for l in self.out.splitlines() if l.startswith("# TYPE")]
        self.assertGreater(len(type_lines), 0, "Must have at least one TYPE line")
        for line in type_lines:
            self.assertTrue(
                line.endswith(" gauge"),
                f"TYPE line must declare 'gauge': {line!r}",
            )


# ── format_prometheus_metrics — summary metrics ───────────────────────────────

class TestFormatPrometheusSummaryMetrics(unittest.TestCase):
    """Summary (containers_total, running_containers) must be emitted."""

    def setUp(self):
        self.out = format_prometheus_metrics(_SAMPLE_DOC)
        self.lines = self.out.splitlines()

    def _metric_lines(self, metric_suffix: str):
        full = "docker_topology_live_" + metric_suffix
        return [l for l in self.lines if l.startswith(full) and not l.startswith("#")]

    def test_containers_total_help_present(self):
        self.assertIn("docker_topology_live_containers_total", self.out)

    def test_containers_total_value(self):
        sample_lines = self._metric_lines("containers_total")
        self.assertEqual(len(sample_lines), 1)
        _, val = sample_lines[0].rsplit(" ", 1)
        self.assertEqual(val, "2")

    def test_running_containers_help_present(self):
        self.assertIn("docker_topology_live_running_containers", self.out)

    def test_running_containers_value(self):
        sample_lines = self._metric_lines("running_containers")
        self.assertEqual(len(sample_lines), 1)
        _, val = sample_lines[0].rsplit(" ", 1)
        self.assertEqual(val, "2")


# ── format_prometheus_metrics — per-container metrics ─────────────────────────

class TestFormatPrometheusPerContainerMetrics(unittest.TestCase):
    """Per-container metric lines must be emitted for each container."""

    def setUp(self):
        self.out = format_prometheus_metrics(_SAMPLE_DOC)

    def _sample_lines_for(self, metric_suffix: str) -> list:
        full = "docker_topology_live_" + metric_suffix
        return [
            l for l in self.out.splitlines()
            if l.startswith(full) and not l.startswith("#")
        ]

    def test_cpu_percent_lines_count(self):
        lines = self._sample_lines_for("container_cpu_percent")
        self.assertEqual(
            len(lines), 2,
            "cpu_percent must emit one line per container",
        )

    def test_memory_usage_bytes_emitted(self):
        self.assertIn("container_memory_usage_bytes", self.out)

    def test_memory_limit_bytes_emitted(self):
        self.assertIn("container_memory_limit_bytes", self.out)

    def test_memory_percent_emitted(self):
        self.assertIn("container_memory_percent", self.out)

    def test_network_rx_emitted(self):
        self.assertIn("container_network_rx_bytes", self.out)

    def test_network_tx_emitted(self):
        self.assertIn("container_network_tx_bytes", self.out)

    def test_block_read_emitted(self):
        self.assertIn("container_block_read_bytes", self.out)

    def test_block_write_emitted(self):
        self.assertIn("container_block_write_bytes", self.out)

    def test_pids_emitted(self):
        self.assertIn("container_pids", self.out)

    def test_container_id_in_labels(self):
        """container_id label must appear in per-container lines."""
        self.assertIn('container_id="container:abc123"', self.out)

    def test_container_name_in_labels(self):
        """container_name label must appear in per-container lines."""
        self.assertIn('container_name="web"', self.out)

    def test_status_in_labels(self):
        """status label must appear in per-container lines."""
        self.assertIn('status="running"', self.out)

    def test_cpu_value_correct(self):
        """CPU percent value must match the input."""
        lines = self._sample_lines_for("container_cpu_percent")
        web_line = next((l for l in lines if "web" in l), None)
        self.assertIsNotNone(web_line, "Must have a cpu_percent line for 'web'")
        # Value is the last space-separated token
        val = web_line.rsplit(" ", 1)[-1]
        self.assertEqual(float(val), 1.5)


# ── format_prometheus_metrics — warnings metric ───────────────────────────────

class TestFormatPrometheusWarnings(unittest.TestCase):
    """metrics_warnings_total must always be present."""

    def test_warnings_metric_always_present(self):
        out = format_prometheus_metrics(_SAMPLE_DOC)
        self.assertIn("metrics_warnings_total", out)

    def test_warnings_zero_when_no_warnings(self):
        out = format_prometheus_metrics(_SAMPLE_DOC)
        lines = [l for l in out.splitlines()
                 if l.startswith("docker_topology_live_metrics_warnings_total")
                 and not l.startswith("#")]
        self.assertEqual(len(lines), 1)
        val = lines[0].rsplit(" ", 1)[-1]
        self.assertEqual(val, "0")

    def test_warnings_count_reflects_warnings_list(self):
        """warnings count must equal len(doc['warnings'])."""
        doc = dict(_SAMPLE_DOC)
        doc["warnings"] = ["one warning", "two warnings"]
        out = format_prometheus_metrics(doc)
        lines = [l for l in out.splitlines()
                 if l.startswith("docker_topology_live_metrics_warnings_total")
                 and not l.startswith("#")]
        val = lines[0].rsplit(" ", 1)[-1]
        self.assertEqual(val, "2")


# ── format_prometheus_metrics — empty / minimal docs ─────────────────────────

class TestFormatPrometheusEmptyDoc(unittest.TestCase):
    """Empty and minimal metrics documents must produce valid output."""

    def test_empty_doc_ends_with_newline(self):
        out = format_prometheus_metrics(_EMPTY_DOC)
        self.assertTrue(out.endswith("\n"))

    def test_empty_doc_has_help_lines(self):
        out = format_prometheus_metrics(_EMPTY_DOC)
        self.assertIn("# HELP", out)

    def test_empty_doc_has_type_lines(self):
        out = format_prometheus_metrics(_EMPTY_DOC)
        self.assertIn("# TYPE", out)

    def test_empty_doc_has_warnings_metric(self):
        """metrics_warnings_total must appear even for empty input."""
        out = format_prometheus_metrics(_EMPTY_DOC)
        self.assertIn("metrics_warnings_total", out)

    def test_empty_doc_no_container_sample_lines(self):
        """No per-container sample lines when containers list is empty."""
        out = format_prometheus_metrics(_EMPTY_DOC)
        sample_lines = [
            l for l in out.splitlines()
            if l.startswith("docker_topology_live_container_cpu_percent{")
        ]
        self.assertEqual(sample_lines, [])

    def test_minimal_doc_no_crash(self):
        """An entirely empty dict must not raise."""
        try:
            out = format_prometheus_metrics({})
            self.assertIsInstance(out, str)
        except Exception as exc:
            self.fail(f"format_prometheus_metrics({{}}) raised {exc!r}")


# ── format_prometheus_metrics — deterministic ordering ───────────────────────

class TestFormatPrometheusDeterministicOrdering(unittest.TestCase):
    """Output ordering must be stable across repeated calls."""

    def test_two_calls_produce_identical_output(self):
        out1 = format_prometheus_metrics(_SAMPLE_DOC)
        out2 = format_prometheus_metrics(_SAMPLE_DOC)
        self.assertEqual(out1, out2, "Two calls with the same input must produce identical output")

    def test_containers_sorted_by_id(self):
        """Containers must appear sorted by container id."""
        out = format_prometheus_metrics(_SAMPLE_DOC)
        # abc123 < def456 alphabetically
        idx_abc = out.find("container:abc123")
        idx_def = out.find("container:def456")
        self.assertGreater(idx_abc, -1)
        self.assertGreater(idx_def, -1)
        self.assertLess(idx_abc, idx_def,
                        "container:abc123 must appear before container:def456 (sorted by id)")

    def test_reversed_input_order_same_output(self):
        """Container order in input dict must not affect output order."""
        doc_a = dict(_SAMPLE_DOC)
        doc_a["containers"] = list(_SAMPLE_DOC["containers"])           # abc, def

        doc_b = dict(_SAMPLE_DOC)
        doc_b["containers"] = list(reversed(_SAMPLE_DOC["containers"])) # def, abc

        self.assertEqual(
            format_prometheus_metrics(doc_a),
            format_prometheus_metrics(doc_b),
            "Output must be identical regardless of input container list order",
        )


# ── format_prometheus_metrics — label escaping ────────────────────────────────

class TestFormatPrometheusLabelEscaping(unittest.TestCase):
    """Special characters in label values must be escaped in output."""

    def _format_with_name(self, name: str) -> str:
        doc = {
            "containers": [{
                "id": "container:test",
                "name": name,
                "status": "running",
                "cpuPercent": 1.0,
                "memoryUsageBytes": 0,
                "memoryLimitBytes": 0,
                "memoryPercent": 0.0,
                "networkRxBytes": 0,
                "networkTxBytes": 0,
                "blockReadBytes": 0,
                "blockWriteBytes": 0,
            }],
            "summary": {"containers": 1, "runningContainers": 1},
            "warnings": [],
        }
        return format_prometheus_metrics(doc)

    def test_double_quote_in_name_escaped(self):
        out = self._format_with_name('say "hello"')
        self.assertNotIn('name="say "hello"', out,
                         "Unescaped double-quote must not appear in label")
        self.assertIn('\\"', out, "Double-quote must be escaped as \\\"")

    def test_backslash_in_name_escaped(self):
        out = self._format_with_name("path\\to\\file")
        self.assertIn("\\\\", out, "Backslash must be doubled in label value")

    def test_newline_in_name_escaped(self):
        out = self._format_with_name("line1\nline2")
        # Check each individual sample line (not the joined string) has no raw newline
        for line in out.splitlines():
            if line.startswith("#") or not line:
                continue
            self.assertNotIn(
                "\n", line,
                "Raw newline must not appear within a single Prometheus sample line",
            )
        # The escaped form \\n must appear somewhere in the output
        self.assertIn("\\n", out,
                      r"Newline must be escaped as literal \n in label value")

    def test_plain_name_unchanged(self):
        out = self._format_with_name("mycontainer")
        self.assertIn('container_name="mycontainer"', out)


def _extract_sample_lines(prometheus_text: str) -> str:
    """Return only non-comment lines from Prometheus output."""
    return "\n".join(
        l for l in prometheus_text.splitlines()
        if l and not l.startswith("#")
    )


# ── format_prometheus_metrics — safety constraints ───────────────────────────

class TestFormatPrometheusPrivacySafety(unittest.TestCase):
    """Sensitive Docker metadata must not appear in Prometheus output."""

    def test_no_raw_docker_labels_in_output(self):
        """Raw Docker container labels must not appear in the Prometheus output."""
        doc = dict(_SAMPLE_DOC)
        # Simulate a container with Docker labels (labels are NOT in the
        # metrics doc schema and must not appear in output even if present)
        containers = [dict(_SAMPLE_DOC["containers"][0])]
        containers[0]["Labels"] = {"com.example.secret": "hunter2"}
        doc["containers"] = containers
        out = format_prometheus_metrics(doc)
        self.assertNotIn("hunter2", out,
                         "Raw Docker label values must not leak into Prometheus output")
        self.assertNotIn("com.example.secret", out)

    def test_no_env_vars_in_output(self):
        """Environment variables must not appear in the output."""
        doc = dict(_SAMPLE_DOC)
        containers = [dict(_SAMPLE_DOC["containers"][0])]
        containers[0]["Env"] = ["SECRET=password123"]
        doc["containers"] = containers
        out = format_prometheus_metrics(doc)
        self.assertNotIn("password123", out,
                         "Environment variables must not appear in Prometheus output")

    def test_no_mount_paths_in_output(self):
        """Mount/bind paths must not appear in the output."""
        doc = dict(_SAMPLE_DOC)
        containers = [dict(_SAMPLE_DOC["containers"][0])]
        containers[0]["Mounts"] = [{"Source": "/etc/secrets", "Destination": "/run/secrets"}]
        doc["containers"] = containers
        out = format_prometheus_metrics(doc)
        self.assertNotIn("/etc/secrets", out,
                         "Mount paths must not appear in Prometheus output")

    def test_no_python_traceback_in_output(self):
        """The formatter must never produce Python traceback text."""
        out = format_prometheus_metrics(_EMPTY_DOC)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("File \"", out)

    def test_output_contains_only_metric_names_and_labels(self):
        """Every non-comment line must match Prometheus sample format."""
        out = format_prometheus_metrics(_SAMPLE_DOC)
        # Pattern: metric_name{labels} value   OR   metric_name value
        prom_sample = re.compile(
            r'^docker_topology_live_\w+(\{[^}]*\})? [-+]?[\d.eE+-]+$'
        )
        for line in out.splitlines():
            if not line or line.startswith("#"):
                continue
            self.assertTrue(
                prom_sample.match(line),
                f"Non-comment line does not match Prometheus sample format: {line!r}",
            )


# ── Optional fields (pids absent) ─────────────────────────────────────────────

class TestFormatPrometheusOptionalFields(unittest.TestCase):
    """Fields absent from a container entry must not appear in output."""

    def test_pids_absent_when_not_in_doc(self):
        """If pids is missing from all containers, container_pids must be omitted."""
        doc = {
            "containers": [{
                "id": "container:nopid",
                "name": "nopidcontainer",
                "status": "running",
                "cpuPercent": 0.0,
                "memoryUsageBytes": 0,
                "memoryLimitBytes": 0,
                "memoryPercent": 0.0,
                "networkRxBytes": 0,
                "networkTxBytes": 0,
                "blockReadBytes": 0,
                "blockWriteBytes": 0,
                # no pids key
            }],
            "summary": {"containers": 1, "runningContainers": 1},
            "warnings": [],
        }
        out = format_prometheus_metrics(doc)
        self.assertNotIn("container_pids", out,
                         "container_pids must be omitted when pids field is absent")

    def test_pids_present_when_in_doc(self):
        """If pids is present, container_pids must appear."""
        out = format_prometheus_metrics(_SAMPLE_DOC)
        self.assertIn("container_pids", out)


# ── PROMETHEUS_CONTENT_TYPE ───────────────────────────────────────────────────

class TestPrometheusContentType(unittest.TestCase):
    """PROMETHEUS_CONTENT_TYPE must match the Prometheus spec."""

    def test_content_type_value(self):
        self.assertEqual(
            PROMETHEUS_CONTENT_TYPE,
            "text/plain; version=0.0.4; charset=utf-8",
        )

    def test_content_type_starts_with_text_plain(self):
        self.assertTrue(
            PROMETHEUS_CONTENT_TYPE.startswith("text/plain"),
            "Prometheus content type must start with 'text/plain'",
        )


if __name__ == "__main__":
    unittest.main()
