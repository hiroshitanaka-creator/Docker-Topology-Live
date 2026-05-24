"""Tests for docker_topology_live.events — SSE encoding, event filtering, streaming.

All tests run without a real Docker daemon.
"""
import io
import json
import pathlib
import re
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from docker_topology_live.events import (
    SSEWriter,
    _DebounceRescan,
    _HEARTBEAT_STEP,
    format_sse,
    is_relevant_event,
    normalize_event,
    stream_live,
    stream_sample,
)


# ── format_sse ────────────────────────────────────────────────────────────────

class TestFormatSSE(unittest.TestCase):
    def test_returns_bytes(self):
        self.assertIsInstance(format_sse("topology", "data"), bytes)

    def test_event_line_present(self):
        text = format_sse("topology", '{"ok":true}').decode()
        self.assertIn("event: topology\n", text)

    def test_data_line_present(self):
        text = format_sse("heartbeat", '{"ok":true}').decode()
        self.assertIn('data: {"ok":true}\n', text)

    def test_ends_with_double_newline(self):
        result = format_sse("ping", "x")
        self.assertTrue(result.endswith(b"\n\n"))

    def test_multiline_data_split(self):
        text = format_sse("multi", "line1\nline2\nline3").decode()
        self.assertIn("data: line1\n", text)
        self.assertIn("data: line2\n", text)
        self.assertIn("data: line3\n", text)

    def test_unicode_data(self):
        text = format_sse("topology", '{"name":"café"}').decode("utf-8")
        self.assertIn("café", text)


# ── is_relevant_event ─────────────────────────────────────────────────────────

class TestIsRelevantEvent(unittest.TestCase):
    # Container lifecycle
    def test_container_start_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "start"}))

    def test_container_die_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "die"}))

    def test_container_create_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "create"}))

    def test_container_stop_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "stop"}))

    def test_container_destroy_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "destroy"}))

    def test_container_remove_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "remove"}))

    def test_container_pause_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "pause"}))

    def test_container_unpause_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "unpause"}))

    def test_container_restart_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "restart"}))

    def test_container_rename_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "rename"}))

    def test_container_health_status_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "container", "Action": "health_status"}))

    # Network membership
    def test_network_connect_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "network", "Action": "connect"}))

    def test_network_disconnect_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "network", "Action": "disconnect"}))

    def test_network_create_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "network", "Action": "create"}))

    def test_network_destroy_relevant(self):
        self.assertTrue(is_relevant_event({"Type": "network", "Action": "destroy"}))

    # Irrelevant types
    def test_image_pull_not_relevant(self):
        self.assertFalse(is_relevant_event({"Type": "image", "Action": "pull"}))

    def test_volume_create_not_relevant(self):
        self.assertFalse(is_relevant_event({"Type": "volume", "Action": "create"}))

    def test_plugin_event_not_relevant(self):
        self.assertFalse(is_relevant_event({"Type": "plugin", "Action": "install"}))

    def test_empty_event_not_relevant(self):
        self.assertFalse(is_relevant_event({}))

    # Irrelevant actions for container
    def test_container_exec_start_not_relevant(self):
        self.assertFalse(is_relevant_event({"Type": "container", "Action": "exec_start"}))

    def test_container_exec_create_not_relevant(self):
        self.assertFalse(is_relevant_event({"Type": "container", "Action": "exec_create"}))

    def test_container_attach_not_relevant(self):
        self.assertFalse(is_relevant_event({"Type": "container", "Action": "attach"}))

    def test_container_copy_not_relevant(self):
        self.assertFalse(is_relevant_event({"Type": "container", "Action": "copy"}))


# ── normalize_event ───────────────────────────────────────────────────────────

class TestNormalizeEvent(unittest.TestCase):
    def test_full_event(self):
        raw = {
            "Type": "container",
            "Action": "start",
            "Actor": {
                "ID": "abc123",
                "Attributes": {"name": "mycontainer", "image": "nginx"},
            },
            "time": 1700000000,
        }
        norm = normalize_event(raw)
        self.assertEqual(norm["type"],   "container")
        self.assertEqual(norm["action"], "start")
        self.assertEqual(norm["id"],     "abc123")
        self.assertEqual(norm["name"],   "mycontainer")
        self.assertEqual(norm["time"],   "1700000000")
        self.assertEqual(norm["scope"],  "docker")

    def test_minimal_event(self):
        norm = normalize_event({})
        self.assertEqual(norm["type"],   "")
        self.assertEqual(norm["action"], "")
        self.assertEqual(norm["id"],     "")
        self.assertEqual(norm["name"],   "")
        self.assertEqual(norm["scope"],  "docker")

    def test_all_keys_present(self):
        norm = normalize_event({"Type": "network", "Action": "connect"})
        for key in ("type", "action", "id", "name", "time", "scope"):
            self.assertIn(key, norm, f"Missing key: {key}")

    def test_no_traceback_in_values(self):
        norm = normalize_event({"Type": "container", "Action": "die"})
        for v in norm.values():
            self.assertNotIn("Traceback", str(v))
            self.assertNotIn("Error", str(v))

    def test_image_attribute_not_included(self):
        """Image tag/digest from actor attributes must NOT leak into output."""
        raw = {
            "Type": "container",
            "Action": "start",
            "Actor": {
                "ID": "abc",
                "Attributes": {"image": "nginx:latest", "name": "web"},
            },
        }
        norm = normalize_event(raw)
        # The normalized output has only the 6 documented keys
        self.assertEqual(set(norm.keys()), {"type", "action", "id", "name", "time", "scope"})

    def test_json_serialisable(self):
        norm = normalize_event({"Type": "container", "Action": "start",
                                "Actor": {"ID": "x", "Attributes": {"name": "y"}},
                                "time": 0})
        json.dumps(norm)  # must not raise


# ── SSEWriter ─────────────────────────────────────────────────────────────────

class TestSSEWriter(unittest.TestCase):

    @staticmethod
    def _make() -> tuple:
        buf = io.BytesIO()
        return SSEWriter(buf), buf

    def test_write_returns_true_on_success(self):
        writer, _ = self._make()
        self.assertTrue(writer.write("topology", "{}"))

    def test_write_encodes_correct_sse(self):
        writer, buf = self._make()
        writer.write("heartbeat", '{"ok":true}')
        text = buf.getvalue().decode()
        self.assertIn("event: heartbeat\n", text)
        self.assertIn('data: {"ok":true}\n', text)

    def test_write_returns_false_when_manually_closed(self):
        writer, _ = self._make()
        writer.close()
        self.assertFalse(writer.write("topology", "{}"))

    def test_write_returns_false_on_broken_pipe(self):
        class _BrokenFile:
            def write(self, _): raise BrokenPipeError("broken")
            def flush(self): pass

        writer = SSEWriter(_BrokenFile())
        self.assertFalse(writer.write("topology", "{}"))
        self.assertTrue(writer.closed)

    def test_write_returns_false_on_connection_reset(self):
        class _ResetFile:
            def write(self, _): raise ConnectionResetError("reset")
            def flush(self): pass

        writer = SSEWriter(_ResetFile())
        self.assertFalse(writer.write("x", "y"))
        self.assertTrue(writer.closed)

    def test_write_returns_false_on_os_error(self):
        class _OsErrFile:
            def write(self, _): raise OSError("eof")
            def flush(self): pass

        writer = SSEWriter(_OsErrFile())
        self.assertFalse(writer.write("x", "y"))

    def test_closed_starts_false(self):
        writer, _ = self._make()
        self.assertFalse(writer.closed)

    def test_close_sets_closed(self):
        writer, _ = self._make()
        writer.close()
        self.assertTrue(writer.closed)

    def test_thread_safe_concurrent_writes(self):
        """Concurrent writes from multiple threads must not corrupt the buffer."""
        buf = io.BytesIO()
        writer = SSEWriter(buf)
        errors = []

        def _spam(label):
            for _ in range(20):
                if not writer.write(label, f"data-{label}"):
                    errors.append(f"write-{label} failed")

        threads = [threading.Thread(target=_spam, args=(str(i),)) for i in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()

        self.assertEqual(errors, [], "Some writes unexpectedly failed")
        text = buf.getvalue().decode()
        # Every SSE block must end with \n\n
        blocks = [b for b in text.split("\n\n") if b.strip()]
        self.assertGreater(len(blocks), 0)
        for block in blocks:
            self.assertIn("event: ", block)
            self.assertIn("data: ", block)


# ── stream_sample ─────────────────────────────────────────────────────────────

class TestStreamSample(unittest.TestCase):

    def _run_until_first_write(self, heartbeat_interval=1000.0):
        """Run stream_sample, close writer after first event, return bytes."""
        buf = io.BytesIO()
        writer = SSEWriter(buf)

        orig_write = writer.write.__func__  # unbound method
        call_n = [0]

        def _close_after_first(self_inner, event_type, data):
            result = orig_write(self_inner, event_type, data)
            call_n[0] += 1
            if call_n[0] >= 1:
                self_inner.close()
            return result

        import types
        writer.write = types.MethodType(_close_after_first, writer)

        from docker_topology_live.scanner import build_sample
        stream_sample(writer, build_sample, heartbeat_interval=heartbeat_interval)
        return buf.getvalue()

    def test_initial_topology_event_sent(self):
        raw = self._run_until_first_write()
        text = raw.decode()
        self.assertIn("event: topology\n", text)

    def test_initial_topology_is_valid_json(self):
        raw = self._run_until_first_write()
        text = raw.decode()
        # SSE topology data is multi-line JSON; collect all data: lines for the
        # topology event block and join them before parsing.
        for block in text.split("\n\n"):
            lines = block.strip().splitlines()
            if any(l == "event: topology" for l in lines):
                data_lines = [l[6:] for l in lines if l.startswith("data: ")]
                combined = "\n".join(data_lines)
                data = json.loads(combined)
                self.assertIn("schemaVersion", data)
                return
        self.fail("No topology event block found in SSE output")

    def test_no_docker_import_needed(self):
        """stream_sample must NOT import the docker package."""
        buf = io.BytesIO()
        writer = SSEWriter(buf)
        writer.close()  # Stop immediately

        from docker_topology_live.scanner import build_sample

        # Ensure docker is absent; stream_sample must not even try to import it
        with patch.dict(sys.modules, {"docker": None}):
            try:
                stream_sample(writer, build_sample, heartbeat_interval=1000.0)
            except ImportError:
                self.fail("stream_sample attempted to import docker package")

    def test_heartbeat_sent_after_short_interval(self):
        buf = io.BytesIO()
        writer = SSEWriter(buf)
        events_seen = []

        orig_write = writer.write.__func__
        import types

        def _capture(self_inner, event_type, data):
            events_seen.append(event_type)
            result = orig_write(self_inner, event_type, data)
            if len(events_seen) >= 2:
                self_inner.close()
            return result

        writer.write = types.MethodType(_capture, writer)

        from docker_topology_live.scanner import build_sample
        # Use a very short heartbeat (slightly longer than _HEARTBEAT_STEP)
        stream_sample(writer, build_sample, heartbeat_interval=_HEARTBEAT_STEP + 0.05)

        self.assertIn("topology",  events_seen)
        self.assertIn("heartbeat", events_seen)

    def test_scan_exception_sends_error_event(self):
        buf = io.BytesIO()
        writer = SSEWriter(buf)

        def _failing_scan():
            raise RuntimeError("simulated scan failure")

        stream_sample(writer, _failing_scan, heartbeat_interval=1000.0)
        text = buf.getvalue().decode()
        self.assertIn("event: error\n", text)
        # No traceback in payload
        for line in text.splitlines():
            if line.startswith("data: "):
                self.assertNotIn("Traceback", line)


# ── stream_live (mocked Docker SDK) ──────────────────────────────────────────

def _mock_docker(events_iter, from_env_raises=None):
    """Return a mock docker module object."""
    mock_docker = MagicMock()
    if from_env_raises is not None:
        mock_docker.from_env.side_effect = from_env_raises
    else:
        client = MagicMock()
        client.events.return_value = iter(events_iter)
        mock_docker.from_env.return_value = client
    return mock_docker


class TestStreamLiveMocked(unittest.TestCase):

    def _run(self, events, from_env_raises=None, scan_fn=None):
        buf = io.BytesIO()
        writer = SSEWriter(buf)

        if scan_fn is None:
            from docker_topology_live.scanner import build_sample
            scan_fn = build_sample

        mock_docker = _mock_docker(events, from_env_raises=from_env_raises)
        with patch.dict(sys.modules, {"docker": mock_docker}):
            stream_live(writer, scan_fn)

        return buf.getvalue().decode()

    def test_initial_topology_always_sent(self):
        text = self._run([])
        self.assertIn("event: topology\n", text)

    def test_relevant_event_triggers_docker_event_sse(self):
        raw = {"Type": "container", "Action": "start",
               "Actor": {"ID": "abc", "Attributes": {"name": "web"}}, "time": 0}
        text = self._run([raw])
        self.assertIn("event: docker-event\n", text)

    def test_irrelevant_event_not_forwarded(self):
        raw = {"Type": "image", "Action": "pull", "Actor": {}, "time": 0}
        text = self._run([raw])
        self.assertNotIn("event: docker-event\n", text)

    def test_network_event_forwarded(self):
        raw = {"Type": "network", "Action": "connect",
               "Actor": {"ID": "net1", "Attributes": {"name": "mynet"}}, "time": 0}
        text = self._run([raw])
        self.assertIn("event: docker-event\n", text)

    def test_docker_connection_failure_sends_error_sse(self):
        text = self._run([], from_env_raises=Exception("daemon not running"))
        self.assertIn("event: error\n", text)

    def test_no_traceback_in_any_output(self):
        raw = {"Type": "container", "Action": "start",
               "Actor": {"ID": "abc", "Attributes": {}}, "time": 0}
        text = self._run([raw])
        self.assertNotIn("Traceback", text)
        self.assertNotIn("File \"", text)

    def test_scan_exception_sends_error_event(self):
        def _failing_scan():
            raise RuntimeError("Docker not reachable")

        # stream_live calls scan_fn() for the initial snapshot
        raw_events = []
        text = self._run(raw_events, scan_fn=_failing_scan)
        self.assertIn("event: error\n", text)
        # Verify error data is safe JSON with no traceback
        for line in text.splitlines():
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if "error" in data:
                        self.assertNotIn("Traceback", data["error"])
                        self.assertNotIn("File \"", data["error"])
                except json.JSONDecodeError:
                    pass

    def test_docker_event_data_is_valid_json(self):
        raw = {"Type": "container", "Action": "stop",
               "Actor": {"ID": "xyz", "Attributes": {"name": "db"}}, "time": 99}
        text = self._run([raw])
        # docker-event data is a single-line JSON dict; find the block
        docker_data = None
        for block in text.split("\n\n"):
            lines = block.strip().splitlines()
            if any(l == "event: docker-event" for l in lines):
                data_lines = [l[6:] for l in lines if l.startswith("data: ")]
                docker_data = json.loads("\n".join(data_lines))
                break
        self.assertIsNotNone(docker_data, "docker-event data block not found")
        self.assertEqual(docker_data["type"],   "container")
        self.assertEqual(docker_data["action"], "stop")
        self.assertEqual(docker_data["scope"],  "docker")

    def test_docker_import_error_sends_error_sse(self):
        buf = io.BytesIO()
        writer = SSEWriter(buf)
        from docker_topology_live.scanner import build_sample

        # None in sys.modules causes ImportError on `import docker`
        with patch.dict(sys.modules, {"docker": None}):
            stream_live(writer, build_sample)

        text = buf.getvalue().decode()
        self.assertIn("event: error\n", text)
        self.assertNotIn("Traceback", text)

    def test_multiple_relevant_events_produce_multiple_docker_events(self):
        events = [
            {"Type": "container", "Action": "start",
             "Actor": {"ID": "a", "Attributes": {}}, "time": 1},
            {"Type": "container", "Action": "stop",
             "Actor": {"ID": "b", "Attributes": {}}, "time": 2},
        ]
        text = self._run(events)
        count = text.count("event: docker-event")
        self.assertEqual(count, 2)


# ── _DebounceRescan ───────────────────────────────────────────────────────────

class TestDebounceRescan(unittest.TestCase):

    def test_triggers_scan_after_delay(self):
        buf = io.BytesIO()
        writer = SSEWriter(buf)
        scan_calls = []

        def _scan():
            scan_calls.append(True)
            from docker_topology_live.scanner import build_sample
            return build_sample()

        debouncer = _DebounceRescan(_scan, writer, delay=0.05)
        debouncer.trigger()
        time.sleep(0.15)

        self.assertEqual(len(scan_calls), 1, "Scan must be called exactly once")

    def test_debounce_collapses_rapid_triggers(self):
        buf = io.BytesIO()
        writer = SSEWriter(buf)
        scan_calls = []

        def _scan():
            scan_calls.append(True)
            from docker_topology_live.scanner import build_sample
            return build_sample()

        debouncer = _DebounceRescan(_scan, writer, delay=0.1)
        # Fire 5 times rapidly
        for _ in range(5):
            debouncer.trigger()
            time.sleep(0.01)
        time.sleep(0.3)

        self.assertEqual(len(scan_calls), 1, "Debounce must collapse rapid triggers into one scan")

    def test_cancel_prevents_scan(self):
        buf = io.BytesIO()
        writer = SSEWriter(buf)
        scan_calls = []

        def _scan():
            scan_calls.append(True)
            from docker_topology_live.scanner import build_sample
            return build_sample()

        debouncer = _DebounceRescan(_scan, writer, delay=0.1)
        debouncer.trigger()
        debouncer.cancel()
        time.sleep(0.2)

        self.assertEqual(len(scan_calls), 0, "Cancel must prevent the scan from running")

    def test_scan_exception_sends_error_event_not_raise(self):
        buf = io.BytesIO()
        writer = SSEWriter(buf)

        def _failing():
            raise RuntimeError("oops")

        debouncer = _DebounceRescan(_failing, writer, delay=0.05)
        debouncer.trigger()
        time.sleep(0.15)

        text = buf.getvalue().decode()
        self.assertIn("event: error\n", text)
        self.assertNotIn("Traceback", text)


# ── app.js security check ─────────────────────────────────────────────────────

class TestAppJSSecurity(unittest.TestCase):
    """Verify that no innerHTML assignment exists in the browser UI."""

    @classmethod
    def setUpClass(cls):
        app_js = (
            pathlib.Path(__file__).parent.parent
            / "src/docker_topology_live/web/assets/app.js"
        )
        cls.content = app_js.read_text(encoding="utf-8")

    def test_no_innerHTML_assignment(self):
        # Match `.innerHTML =` (assignment, not e.g. a comment mentioning innerHTML)
        matches = re.findall(r'\.innerHTML\s*=', self.content)
        self.assertEqual(
            matches, [],
            f"innerHTML assignment(s) found in app.js: {matches}",
        )

    def test_uses_textContent(self):
        """textContent should be present (we rely on it for safe rendering)."""
        self.assertIn("textContent", self.content)

    def test_uses_createElement(self):
        self.assertIn("createElement", self.content)

    def test_uses_createTextNode(self):
        self.assertIn("createTextNode", self.content)

    def test_event_source_present(self):
        """EventSource must be used for SSE support."""
        self.assertIn("EventSource", self.content)

    def test_polling_fallback_present(self):
        """startPolling / stopPolling must be implemented."""
        self.assertIn("startPolling", self.content)
        self.assertIn("stopPolling",  self.content)
