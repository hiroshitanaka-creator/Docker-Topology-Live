"""Tests for docker_topology_live.metrics — parsers, collection, sample data.

All tests run without a real Docker daemon.  The docker package is mocked
wherever live collection is tested.
"""
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

from docker_topology_live.metrics import (
    build_sample_metrics,
    parse_blkio,
    parse_container_stats,
    parse_cpu_percent,
    parse_memory,
    parse_network,
    parse_pids,
)


# ── parse_cpu_percent ─────────────────────────────────────────────────────────

def _cpu_payload(cpu_total=200_000_000, pre_total=100_000_000,
                 sys_cpu=10_000_000_000, pre_sys=9_000_000_000,
                 online_cpus=2):
    """Return a minimal stats dict for cpu percent calculation."""
    return {
        "cpu_stats": {
            "cpu_usage": {"total_usage": cpu_total},
            "system_cpu_usage": sys_cpu,
            "online_cpus": online_cpus,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": pre_total},
            "system_cpu_usage": pre_sys,
        },
    }


class TestParseCpuPercent(unittest.TestCase):

    def test_normal_calculation(self):
        # cpu_delta = 100_000_000, system_delta = 1_000_000_000
        # percent = (100_000_000 / 1_000_000_000) * 2 * 100 = 20.0
        payload = _cpu_payload(
            cpu_total=200_000_000, pre_total=100_000_000,
            sys_cpu=10_000_000_000, pre_sys=9_000_000_000,
            online_cpus=2,
        )
        result = parse_cpu_percent(payload)
        self.assertAlmostEqual(result, 20.0, places=1)

    def test_zero_cpu_delta_returns_zero(self):
        payload = _cpu_payload(cpu_total=100_000_000, pre_total=100_000_000)
        self.assertEqual(parse_cpu_percent(payload), 0.0)

    def test_zero_system_delta_returns_zero(self):
        payload = _cpu_payload(sys_cpu=9_000_000_000, pre_sys=9_000_000_000)
        self.assertEqual(parse_cpu_percent(payload), 0.0)

    def test_negative_system_delta_returns_zero(self):
        payload = _cpu_payload(sys_cpu=8_000_000_000, pre_sys=9_000_000_000)
        self.assertEqual(parse_cpu_percent(payload), 0.0)

    def test_missing_cpu_stats_returns_zero(self):
        self.assertEqual(parse_cpu_percent({}), 0.0)

    def test_none_stats_returns_zero(self):
        self.assertEqual(parse_cpu_percent({"cpu_stats": None, "precpu_stats": None}), 0.0)

    def test_uses_percpu_count_when_online_cpus_missing(self):
        stats = {
            "cpu_stats": {
                "cpu_usage": {
                    "total_usage": 200_000_000,
                    "percpu_usage": [0, 0, 0, 0],   # 4 CPUs
                },
                "system_cpu_usage": 10_000_000_000,
                # no "online_cpus"
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100_000_000},
                "system_cpu_usage": 9_000_000_000,
            },
        }
        # percent = (100_000_000 / 1_000_000_000) * 4 * 100 = 40.0
        result = parse_cpu_percent(stats)
        self.assertAlmostEqual(result, 40.0, places=1)

    def test_returns_float(self):
        self.assertIsInstance(parse_cpu_percent(_cpu_payload()), float)

    def test_never_raises_on_garbage_input(self):
        for bad in [None, "string", 42, [], {"cpu_stats": "bad"}]:
            try:
                result = parse_cpu_percent(bad)
                self.assertEqual(result, 0.0)
            except Exception as exc:
                self.fail(f"parse_cpu_percent({bad!r}) raised {exc}")


# ── parse_memory ──────────────────────────────────────────────────────────────

class TestParseMemory(unittest.TestCase):

    def test_normal_calculation(self):
        stats = {"memory_stats": {"usage": 104_857_600, "limit": 1_073_741_824}}
        result = parse_memory(stats)
        self.assertEqual(result["memoryUsageBytes"], 104_857_600)
        self.assertEqual(result["memoryLimitBytes"], 1_073_741_824)
        self.assertAlmostEqual(result["memoryPercent"], 9.77, places=1)

    def test_zero_limit_returns_zero_percent(self):
        stats = {"memory_stats": {"usage": 1024, "limit": 0}}
        result = parse_memory(stats)
        self.assertEqual(result["memoryPercent"], 0.0)

    def test_missing_memory_stats_returns_zeros(self):
        result = parse_memory({})
        self.assertEqual(result["memoryUsageBytes"], 0)
        self.assertEqual(result["memoryLimitBytes"], 0)
        self.assertEqual(result["memoryPercent"], 0.0)

    def test_all_keys_present(self):
        result = parse_memory({"memory_stats": {"usage": 0, "limit": 0}})
        for key in ("memoryUsageBytes", "memoryLimitBytes", "memoryPercent"):
            self.assertIn(key, result)

    def test_never_raises_on_garbage(self):
        for bad in [None, "string", 42, {"memory_stats": "bad"}]:
            try:
                parse_memory(bad)
            except Exception as exc:
                self.fail(f"parse_memory({bad!r}) raised {exc}")


# ── parse_network ─────────────────────────────────────────────────────────────

class TestParseNetwork(unittest.TestCase):

    def test_single_interface(self):
        stats = {"networks": {"eth0": {"rx_bytes": 1024, "tx_bytes": 2048}}}
        result = parse_network(stats)
        self.assertEqual(result["networkRxBytes"], 1024)
        self.assertEqual(result["networkTxBytes"], 2048)

    def test_aggregates_multiple_interfaces(self):
        stats = {"networks": {
            "eth0": {"rx_bytes": 1000, "tx_bytes": 2000},
            "eth1": {"rx_bytes": 500,  "tx_bytes": 1000},
        }}
        result = parse_network(stats)
        self.assertEqual(result["networkRxBytes"], 1500)
        self.assertEqual(result["networkTxBytes"], 3000)

    def test_empty_networks_returns_zeros(self):
        result = parse_network({"networks": {}})
        self.assertEqual(result["networkRxBytes"], 0)
        self.assertEqual(result["networkTxBytes"], 0)

    def test_missing_networks_key_returns_zeros(self):
        result = parse_network({})
        self.assertEqual(result["networkRxBytes"], 0)
        self.assertEqual(result["networkTxBytes"], 0)

    def test_all_keys_present(self):
        result = parse_network({})
        self.assertIn("networkRxBytes", result)
        self.assertIn("networkTxBytes", result)

    def test_never_raises_on_garbage(self):
        for bad in [None, "string", 42]:
            try:
                parse_network(bad)
            except Exception as exc:
                self.fail(f"parse_network({bad!r}) raised {exc}")


# ── parse_blkio ───────────────────────────────────────────────────────────────

class TestParseBlkio(unittest.TestCase):

    def test_normal_read_write(self):
        stats = {"blkio_stats": {"io_service_bytes_recursive": [
            {"op": "Read",  "value": 4096},
            {"op": "Write", "value": 8192},
            {"op": "Total", "value": 12288},
        ]}}
        result = parse_blkio(stats)
        self.assertEqual(result["blockReadBytes"],  4096)
        self.assertEqual(result["blockWriteBytes"], 8192)

    def test_case_insensitive_op(self):
        stats = {"blkio_stats": {"io_service_bytes_recursive": [
            {"op": "read",  "value": 1024},
            {"op": "WRITE", "value": 2048},
        ]}}
        result = parse_blkio(stats)
        self.assertEqual(result["blockReadBytes"],  1024)
        self.assertEqual(result["blockWriteBytes"], 2048)

    def test_missing_blkio_returns_zeros(self):
        result = parse_blkio({})
        self.assertEqual(result["blockReadBytes"],  0)
        self.assertEqual(result["blockWriteBytes"], 0)

    def test_empty_io_entries_returns_zeros(self):
        result = parse_blkio({"blkio_stats": {"io_service_bytes_recursive": []}})
        self.assertEqual(result["blockReadBytes"],  0)
        self.assertEqual(result["blockWriteBytes"], 0)

    def test_all_keys_present(self):
        result = parse_blkio({})
        self.assertIn("blockReadBytes",  result)
        self.assertIn("blockWriteBytes", result)

    def test_never_raises_on_garbage(self):
        for bad in [None, "string", 42]:
            try:
                parse_blkio(bad)
            except Exception as exc:
                self.fail(f"parse_blkio({bad!r}) raised {exc}")


# ── parse_pids ────────────────────────────────────────────────────────────────

class TestParsePids(unittest.TestCase):

    def test_returns_pid_count(self):
        stats = {"pids_stats": {"current": 15}}
        self.assertEqual(parse_pids(stats), 15)

    def test_missing_pids_stats_returns_none(self):
        self.assertIsNone(parse_pids({}))

    def test_none_current_returns_none(self):
        self.assertIsNone(parse_pids({"pids_stats": {"current": None}}))

    def test_returns_int(self):
        stats = {"pids_stats": {"current": "8"}}
        result = parse_pids(stats)
        self.assertIsInstance(result, int)
        self.assertEqual(result, 8)

    def test_never_raises(self):
        for bad in [None, "string", 42, {"pids_stats": "bad"}]:
            try:
                parse_pids(bad)
            except Exception as exc:
                self.fail(f"parse_pids({bad!r}) raised {exc}")


# ── parse_container_stats ─────────────────────────────────────────────────────

class TestParseContainerStats(unittest.TestCase):

    def _payload(self):
        return {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200_000_000},
                "system_cpu_usage": 10_000_000_000,
                "online_cpus": 2,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100_000_000},
                "system_cpu_usage": 9_000_000_000,
            },
            "memory_stats": {"usage": 104_857_600, "limit": 1_073_741_824},
            "networks": {"eth0": {"rx_bytes": 1024, "tx_bytes": 2048}},
            "blkio_stats": {"io_service_bytes_recursive": []},
            "pids_stats": {"current": 7},
        }

    def test_all_required_fields_present(self):
        result = parse_container_stats(
            "container:abc123abc123", "mycontainer", "running", self._payload()
        )
        for field in (
            "id", "name", "status", "cpuPercent",
            "memoryUsageBytes", "memoryLimitBytes", "memoryPercent",
            "networkRxBytes", "networkTxBytes",
            "blockReadBytes", "blockWriteBytes",
        ):
            self.assertIn(field, result, f"Missing field: {field}")

    def test_id_and_name_preserved(self):
        result = parse_container_stats(
            "container:abc123abc123", "mycontainer", "running", self._payload()
        )
        self.assertEqual(result["id"],     "container:abc123abc123")
        self.assertEqual(result["name"],   "mycontainer")
        self.assertEqual(result["status"], "running")

    def test_pids_present_when_available(self):
        result = parse_container_stats("container:aaa", "x", "running", self._payload())
        self.assertIn("pids", result)
        self.assertEqual(result["pids"], 7)

    def test_pids_absent_when_not_available(self):
        payload = self._payload()
        del payload["pids_stats"]
        result = parse_container_stats("container:aaa", "x", "running", payload)
        self.assertNotIn("pids", result)

    def test_cpu_percent_positive(self):
        result = parse_container_stats("container:aaa", "x", "running", self._payload())
        self.assertGreater(result["cpuPercent"], 0)

    def test_json_serialisable(self):
        result = parse_container_stats("container:abc123abc123", "web", "running", self._payload())
        json.dumps(result)  # must not raise


# ── build_sample_metrics ──────────────────────────────────────────────────────

class TestBuildSampleMetrics(unittest.TestCase):

    def setUp(self):
        self.doc = build_sample_metrics()

    def test_no_docker_import_needed(self):
        """build_sample_metrics must not require the docker package."""
        with patch.dict(sys.modules, {"docker": None}):
            try:
                from docker_topology_live.metrics import build_sample_metrics as bsm
                bsm()
            except ImportError:
                self.fail("build_sample_metrics tried to import docker")

    def test_schema_version(self):
        self.assertEqual(self.doc["schemaVersion"], "1.0")

    def test_sample_flag_is_true(self):
        self.assertTrue(self.doc["sample"])

    def test_has_containers_list(self):
        self.assertIsInstance(self.doc["containers"], list)
        self.assertGreater(len(self.doc["containers"]), 0)

    def test_has_summary(self):
        summary = self.doc["summary"]
        for key in (
            "containers", "runningContainers",
            "avgCpuPercent", "maxCpuPercent",
            "totalMemoryUsageBytes",
            "totalNetworkRxBytes", "totalNetworkTxBytes",
        ):
            self.assertIn(key, summary, f"Summary missing key: {key}")

    def test_container_ids_use_correct_prefix(self):
        for c in self.doc["containers"]:
            self.assertTrue(
                c["id"].startswith("container:"),
                f"Container id {c['id']!r} must start with 'container:'",
            )

    def test_critical_glow_container_exists(self):
        """Sample must include a container with CPU >= 80 % (triggers glow-critical)."""
        cpu_vals = [c["cpuPercent"] for c in self.doc["containers"]]
        self.assertTrue(
            any(v >= 80 for v in cpu_vals),
            f"No critical-glow container in sample: {cpu_vals}",
        )

    def test_all_containers_json_serialisable(self):
        json.dumps(self.doc)  # must not raise

    def test_warnings_is_list(self):
        self.assertIsInstance(self.doc["warnings"], list)

    def test_summary_running_count_correct(self):
        running = sum(1 for c in self.doc["containers"] if c["status"] == "running")
        self.assertEqual(self.doc["summary"]["runningContainers"], running)

    def test_summary_max_cpu_is_max(self):
        running = [c for c in self.doc["containers"] if c["status"] == "running"]
        expected = max(c["cpuPercent"] for c in running)
        self.assertAlmostEqual(self.doc["summary"]["maxCpuPercent"], expected, places=1)


# ── collect_live_metrics (mocked) ─────────────────────────────────────────────

def _make_mock_container(short_id="abc123abc123", name="web", status="running",
                         stats_payload=None, stats_raises=None):
    """Return a mock container object."""
    container = MagicMock()
    container.id     = short_id + "0" * (64 - len(short_id))  # full 64-char id
    container.name   = name
    container.status = status
    if stats_raises is not None:
        container.stats.side_effect = stats_raises
    else:
        payload = stats_payload or {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200_000_000},
                "system_cpu_usage": 10_000_000_000,
                "online_cpus": 2,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100_000_000},
                "system_cpu_usage": 9_000_000_000,
            },
            "memory_stats": {"usage": 52_428_800, "limit": 1_073_741_824},
            "networks": {"eth0": {"rx_bytes": 1024, "tx_bytes": 2048}},
            "blkio_stats": {"io_service_bytes_recursive": []},
            "pids_stats": {"current": 5},
        }
        container.stats.return_value = payload
    return container


class TestCollectLiveMetrics(unittest.TestCase):

    def _run(self, containers):
        mock_docker = MagicMock()
        mock_docker.from_env.return_value.containers.list.return_value = containers
        with patch.dict(sys.modules, {"docker": mock_docker}):
            from docker_topology_live.metrics import collect_live_metrics
            return collect_live_metrics()

    def test_returns_valid_document(self):
        doc = self._run([_make_mock_container()])
        self.assertEqual(doc["schemaVersion"], "1.0")
        self.assertFalse(doc["sample"])
        self.assertIn("containers", doc)
        self.assertIn("summary",    doc)

    def test_container_id_uses_short_id(self):
        doc = self._run([_make_mock_container(short_id="abc123abc123")])
        ids = [c["id"] for c in doc["containers"]]
        self.assertEqual(ids, ["container:abc123abc123"])

    def test_stats_called_stream_false(self):
        """stats(stream=False) must be used — never stream=True."""
        container = _make_mock_container()
        self._run([container])
        container.stats.assert_called_once_with(stream=False)

    def test_individual_failure_is_skipped_with_warning(self):
        good = _make_mock_container(short_id="aaa111aaa111", name="good")
        bad  = _make_mock_container(
            short_id="bbb222bbb222", name="bad",
            stats_raises=RuntimeError("stats unavailable"),
        )
        doc = self._run([good, bad])
        # Only the good container should appear
        names = [c["name"] for c in doc["containers"]]
        self.assertIn("good", names)
        self.assertNotIn("bad", names)
        # A warning must be recorded
        self.assertTrue(any("bad" in w for w in doc["warnings"]),
                        f"Expected warning for 'bad' container, got: {doc['warnings']}")

    def test_no_docker_package_raises_runtime_error(self):
        with patch.dict(sys.modules, {"docker": None}):
            from docker_topology_live.metrics import collect_live_metrics
            with self.assertRaises(RuntimeError):
                collect_live_metrics()

    def test_no_containers_returns_empty_list(self):
        doc = self._run([])
        self.assertEqual(doc["containers"], [])
        self.assertEqual(doc["summary"]["runningContainers"], 0)

    def test_json_serialisable(self):
        doc = self._run([_make_mock_container()])
        json.dumps(doc)

    def test_no_traceback_in_document_on_container_failure(self):
        """Tracebacks must never appear in the metrics document."""
        bad = _make_mock_container(
            short_id="bbb222bbb222", name="bad",
            stats_raises=RuntimeError("intentional failure"),
        )
        doc = self._run([bad])
        doc_str = json.dumps(doc)
        self.assertNotIn("Traceback",  doc_str)
        self.assertNotIn('File "',     doc_str)
        self.assertNotIn("RuntimeError", doc_str)


if __name__ == "__main__":
    unittest.main()
