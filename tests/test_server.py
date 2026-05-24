"""Tests for docker_topology_live.server — CORS, handler configuration, and SSE endpoint."""
import inspect
import io
import json
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock, patch

from docker_topology_live.server import make_handler, serve


class TestCORSConfig(unittest.TestCase):
    """CORS must be off by default; opt-in only via allow_cors=True."""

    def test_cors_disabled_by_default(self):
        Handler = make_handler(use_sample=True)
        self.assertFalse(
            Handler.allow_cors,
            "allow_cors must default to False — wildcard CORS is a security risk "
            "for a local server that exposes Docker topology data.",
        )

    def test_cors_enabled_when_opt_in(self):
        Handler = make_handler(use_sample=True, allow_cors=True)
        self.assertTrue(Handler.allow_cors)

    def test_cors_false_independent_of_use_sample(self):
        for use_sample in (True, False):
            with self.subTest(use_sample=use_sample):
                Handler = make_handler(use_sample=use_sample)
                self.assertFalse(Handler.allow_cors)

    def test_serve_signature_accepts_allow_cors(self):
        params = inspect.signature(serve).parameters
        self.assertIn(
            "allow_cors", params,
            "serve() must accept allow_cors parameter",
        )
        self.assertFalse(
            params["allow_cors"].default,
            "allow_cors must default to False in serve()",
        )


class TestSendBytesHeaders(unittest.TestCase):
    """Verify that _send_bytes() emits (or omits) the CORS header correctly."""

    def _collect_headers(self, allow_cors: bool) -> list:
        """Instantiate a handler, call _send_bytes, and return header call args."""
        HandlerCls = make_handler(use_sample=True, allow_cors=allow_cors)

        handler = HandlerCls.__new__(HandlerCls)
        handler.wfile = io.BytesIO()
        handler.send_response = MagicMock()
        handler.send_header   = MagicMock()
        handler.end_headers   = MagicMock()

        handler._send_bytes(b"hello", "text/plain")

        # Return the list of (header_name, header_value) pairs sent
        return [c.args for c in handler.send_header.call_args_list]

    def test_cors_header_absent_by_default(self):
        headers = self._collect_headers(allow_cors=False)
        cors_headers = [
            name for name, *_ in headers
            if "Access-Control-Allow-Origin" in name
        ]
        self.assertEqual(
            cors_headers, [],
            "Access-Control-Allow-Origin must NOT be sent when allow_cors=False",
        )

    def test_cors_header_present_when_enabled(self):
        headers = self._collect_headers(allow_cors=True)
        cors_headers = [
            (name, value) for name, value in headers
            if name == "Access-Control-Allow-Origin"
        ]
        self.assertGreater(
            len(cors_headers), 0,
            "Access-Control-Allow-Origin: * must be sent when allow_cors=True",
        )
        self.assertEqual(cors_headers[0][1], "*")

    def test_cache_control_always_present(self):
        """Cache-Control: no-store must always be sent regardless of CORS setting."""
        for allow_cors in (True, False):
            with self.subTest(allow_cors=allow_cors):
                headers = self._collect_headers(allow_cors=allow_cors)
                cc_headers = [n for n, *_ in headers if n == "Cache-Control"]
                self.assertGreater(
                    len(cc_headers), 0,
                    f"Cache-Control must be sent when allow_cors={allow_cors}",
                )

    def test_content_type_always_present(self):
        for allow_cors in (True, False):
            with self.subTest(allow_cors=allow_cors):
                headers = self._collect_headers(allow_cors=allow_cors)
                ct_headers = [n for n, *_ in headers if n == "Content-Type"]
                self.assertGreater(len(ct_headers), 0)


class TestMakeHandler(unittest.TestCase):
    """make_handler() should return distinct classes with correct attributes."""

    def test_returns_class(self):
        cls = make_handler()
        self.assertTrue(isinstance(cls, type))

    def test_use_sample_attribute(self):
        self.assertFalse(make_handler(use_sample=False).use_sample)
        self.assertTrue(make_handler(use_sample=True).use_sample)

    def test_two_calls_return_distinct_classes(self):
        cls1 = make_handler(use_sample=True, allow_cors=False)
        cls2 = make_handler(use_sample=False, allow_cors=True)
        self.assertIsNot(cls1, cls2)
        # Changing one should not affect the other
        self.assertTrue(cls1.use_sample)
        self.assertFalse(cls2.use_sample)
        self.assertFalse(cls1.allow_cors)
        self.assertTrue(cls2.allow_cors)

    def test_enable_metrics_attribute_defaults_false(self):
        cls = make_handler()
        self.assertFalse(cls.enable_metrics)

    def test_enable_metrics_attribute_can_be_set(self):
        cls = make_handler(enable_metrics=True)
        self.assertTrue(cls.enable_metrics)

    def test_metrics_interval_attribute_defaults_two(self):
        cls = make_handler()
        self.assertEqual(cls.metrics_interval, 2.0)

    def test_metrics_interval_attribute_can_be_set(self):
        cls = make_handler(metrics_interval=5.0)
        self.assertEqual(cls.metrics_interval, 5.0)


# ── /api/metrics endpoint ─────────────────────────────────────────────────────

def _make_metrics_handler(allow_cors=False, use_sample=True):
    """Return a _TopologyHandler instance wired for /api/metrics tests."""
    HandlerCls = make_handler(use_sample=use_sample, allow_cors=allow_cors)
    handler = HandlerCls.__new__(HandlerCls)
    handler.path          = "/api/metrics"
    handler.send_response = MagicMock()
    handler.send_header   = MagicMock()
    handler.end_headers   = MagicMock()
    handler.wfile         = io.BytesIO()
    return handler


class TestMetricsEndpoint(unittest.TestCase):
    """GET /api/metrics returns JSON; CORS default off."""

    def test_returns_200_with_json(self):
        handler = _make_metrics_handler(use_sample=True)
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        ct_headers = [
            v for n, v in (c.args for c in handler.send_header.call_args_list)
            if n == "Content-Type"
        ]
        self.assertTrue(
            any("application/json" in v for v in ct_headers),
            f"Expected JSON content-type, got: {ct_headers}",
        )

    def test_response_body_is_valid_json(self):
        handler = _make_metrics_handler(use_sample=True)
        handler.do_GET()
        body = handler.wfile.getvalue()
        data = json.loads(body.decode())
        self.assertIn("schemaVersion", data)

    def test_cors_absent_by_default(self):
        handler = _make_metrics_handler(allow_cors=False)
        handler.do_GET()
        headers = [c.args for c in handler.send_header.call_args_list]
        cors = [n for n, *_ in headers if "Access-Control-Allow-Origin" in n]
        self.assertEqual(cors, [],
                         "CORS header must NOT be sent for /api/metrics by default")

    def test_cors_present_when_enabled(self):
        handler = _make_metrics_handler(allow_cors=True)
        handler.do_GET()
        headers = [c.args for c in handler.send_header.call_args_list]
        cors = [(n, v) for n, v in headers if n == "Access-Control-Allow-Origin"]
        self.assertGreater(len(cors), 0)
        self.assertEqual(cors[0][1], "*")

    def test_serve_signature_accepts_enable_metrics(self):
        params = inspect.signature(serve).parameters
        self.assertIn("enable_metrics", params)
        self.assertFalse(params["enable_metrics"].default)

    def test_serve_signature_accepts_metrics_interval(self):
        params = inspect.signature(serve).parameters
        self.assertIn("metrics_interval", params)
        self.assertEqual(params["metrics_interval"].default, 2.0)


# ── /api/events endpoint ──────────────────────────────────────────────────────

class _ClosingFile:
    """Wfile stub that raises BrokenPipeError on the first write.

    This causes SSEWriter to set closed=True immediately, so streaming
    functions return after the first (or only) write attempt.
    """
    def write(self, _):
        raise BrokenPipeError("test disconnect")
    def flush(self):
        pass


def _make_events_handler(allow_cors=False, use_sample=True):
    """Return a _TopologyHandler instance wired for /api/events tests."""
    HandlerCls = make_handler(use_sample=use_sample, allow_cors=allow_cors)
    handler = HandlerCls.__new__(HandlerCls)
    handler.path = "/api/events"
    handler.send_response = MagicMock()
    handler.send_header   = MagicMock()
    handler.end_headers   = MagicMock()
    handler.wfile         = _ClosingFile()
    return handler


class TestEventsEndpointHeaders(unittest.TestCase):
    """GET /api/events must set correct SSE headers."""

    def _sent_headers(self, handler) -> list:
        handler.do_GET()
        return [c.args for c in handler.send_header.call_args_list]

    def test_content_type_is_event_stream(self):
        handler = _make_events_handler()
        headers = self._sent_headers(handler)
        ct = [(n, v) for n, v in headers if n == "Content-Type"]
        self.assertGreater(len(ct), 0, "Content-Type header not sent for /api/events")
        self.assertIn("text/event-stream", ct[0][1])

    def test_cache_control_no_store(self):
        handler = _make_events_handler()
        headers = self._sent_headers(handler)
        cc = [v for n, v in headers if n == "Cache-Control"]
        self.assertGreater(len(cc), 0)
        self.assertIn("no-store", cc[0])

    def test_cors_absent_by_default(self):
        handler = _make_events_handler(allow_cors=False)
        headers = self._sent_headers(handler)
        cors = [n for n, *_ in headers if "Access-Control-Allow-Origin" in n]
        self.assertEqual(
            cors, [],
            "Access-Control-Allow-Origin must NOT be sent for /api/events by default",
        )

    def test_cors_present_when_enabled(self):
        handler = _make_events_handler(allow_cors=True)
        headers = self._sent_headers(handler)
        cors = [(n, v) for n, v in headers if n == "Access-Control-Allow-Origin"]
        self.assertGreater(
            len(cors), 0,
            "Access-Control-Allow-Origin must be sent when allow_cors=True",
        )
        self.assertEqual(cors[0][1], "*")

    def test_status_200_sent(self):
        handler = _make_events_handler()
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)

    def test_connection_keep_alive_sent(self):
        handler = _make_events_handler()
        headers = self._sent_headers(handler)
        conn = [v for n, v in headers if n == "Connection"]
        self.assertGreater(len(conn), 0)
        self.assertIn("keep-alive", conn[0].lower())


class TestThreadingServer(unittest.TestCase):
    """serve() must use ThreadingHTTPServer."""

    def test_serve_uses_threading_http_server(self):
        """Verify that serve() constructs a ThreadingHTTPServer."""
        created = []

        class _FakeServer(ThreadingHTTPServer):
            def __init__(self, addr, handler):
                created.append(("init", addr, handler))
            def serve_forever(self):
                raise KeyboardInterrupt  # stop immediately
            def server_close(self):
                pass

        with patch("docker_topology_live.server.ThreadingHTTPServer", _FakeServer):
            serve(use_sample=True)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0][0], "init")
