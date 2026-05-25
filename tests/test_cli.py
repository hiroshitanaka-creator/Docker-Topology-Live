"""Tests for docker_topology_live.cli."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docker_topology_live.cli import build_parser, main


class TestBuildParser(unittest.TestCase):
    def test_sample_command_parsed(self):
        args = build_parser().parse_args(["sample"])
        self.assertEqual(args.command, "sample")

    def test_sample_with_output(self):
        args = build_parser().parse_args(["sample", "-o", "out.json"])
        self.assertEqual(args.output, "out.json")

    def test_scan_command_parsed(self):
        args = build_parser().parse_args(["scan"])
        self.assertEqual(args.command, "scan")

    def test_scan_sample_on_error_flag(self):
        args = build_parser().parse_args(["scan", "--sample-on-error"])
        self.assertTrue(args.sample_on_error)

    def test_serve_defaults(self):
        args = build_parser().parse_args(["serve"])
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8080)
        self.assertFalse(args.sample)

    def test_serve_sample_flag(self):
        args = build_parser().parse_args(["serve", "--sample"])
        self.assertTrue(args.sample)

    def test_serve_custom_port(self):
        args = build_parser().parse_args(["serve", "--port", "9090"])
        self.assertEqual(args.port, 9090)

    def test_doctor_command_parsed(self):
        args = build_parser().parse_args(["doctor"])
        self.assertEqual(args.command, "doctor")


class TestMainSample(unittest.TestCase):
    def test_sample_to_stdout(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            rc = main(["sample"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertIn("nodes", data)
        self.assertTrue(data.get("sample"))

    def test_sample_to_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = str(Path(td) / "topo.json")
            rc = main(["sample", "-o", out])
            self.assertEqual(rc, 0)
            data = json.loads(Path(out).read_text())
            self.assertIn("nodes", data)
            self.assertTrue(data.get("sample"))

    def test_sample_output_has_schema_version(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            main(["sample"])
        data = json.loads(buf.getvalue())
        self.assertEqual(data.get("schemaVersion"), "1.0")

    def test_sample_output_has_summary(self):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            main(["sample"])
        data = json.loads(buf.getvalue())
        self.assertIn("summary", data)
        self.assertGreater(data["summary"].get("containers", 0), 0)


class TestMainScanFallback(unittest.TestCase):
    def test_scan_sample_on_error_fallback(self):
        """--sample-on-error must produce sample data when Docker is unavailable."""
        buf = io.StringIO()
        with patch("sys.stdout", buf), \
             patch("docker_topology_live.cli.scan_live",
                   side_effect=RuntimeError("Docker not available")):
            rc = main(["scan", "--sample-on-error"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertTrue(data.get("sample"))

    def test_scan_without_fallback_returns_nonzero(self):
        """Without --sample-on-error, a Docker error must return non-zero exit code."""
        with patch("docker_topology_live.cli.scan_live",
                   side_effect=RuntimeError("Docker not available")):
            rc = main(["scan"])
        self.assertNotEqual(rc, 0)


class TestServePrometheusFlag(unittest.TestCase):
    """--prometheus flag must parse and default to False."""

    def test_prometheus_flag_parses(self):
        args = build_parser().parse_args(["serve", "--prometheus"])
        self.assertTrue(args.prometheus)

    def test_prometheus_defaults_false(self):
        args = build_parser().parse_args(["serve"])
        self.assertFalse(
            args.prometheus,
            "--prometheus must default to False",
        )

    def test_prometheus_combined_with_metrics(self):
        args = build_parser().parse_args(["serve", "--metrics", "--prometheus"])
        self.assertTrue(args.metrics)
        self.assertTrue(args.prometheus)

    def test_prometheus_combined_with_sample(self):
        args = build_parser().parse_args(["serve", "--sample", "--prometheus"])
        self.assertTrue(args.sample)
        self.assertTrue(args.prometheus)

    def test_prometheus_not_set_without_flag(self):
        args = build_parser().parse_args(["serve", "--metrics", "--diagnostics"])
        self.assertFalse(args.prometheus)
