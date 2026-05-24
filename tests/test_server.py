"""Tests for docker_topology_live.server — CORS and handler configuration."""
import inspect
import io
import unittest
from unittest.mock import MagicMock, call, patch

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
