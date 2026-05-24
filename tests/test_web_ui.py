"""Tests for the browser UI static assets (index.html and app.js).

These are text-parsing checks that run without a browser or build step.
They guard against accidental omission of required DOM elements and
against security regressions (innerHTML, wildcard CORS in JS, etc.).
"""
import io
import json
import pathlib
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

_ROOT = pathlib.Path(__file__).parent.parent
_HTML = (_ROOT / "src/docker_topology_live/web/index.html").read_text(encoding="utf-8")
_JS   = (_ROOT / "src/docker_topology_live/web/assets/app.js").read_text(encoding="utf-8")
_VENDOR_DIR = _ROOT / "src/docker_topology_live/web/vendor"


class TestIndexHTMLStructure(unittest.TestCase):
    """index.html must contain the expected DOM skeleton."""

    def test_metrics_status_element_present(self):
        """id="metrics-status" must exist so app.js can set glow-state classes."""
        self.assertIn(
            'id="metrics-status"', _HTML,
            'index.html is missing <span id="metrics-status"> in the stats bar.',
        )

    def test_metrics_status_inside_stats_bar(self):
        """metrics-status must be a descendant of #stats-bar."""
        stats_bar_start = _HTML.find('id="stats-bar"')
        self.assertGreater(stats_bar_start, -1, "#stats-bar not found in index.html")
        # The closing </div> after stats-bar ends the section; metrics-status must come before it.
        stats_bar_block = _HTML[stats_bar_start:]
        close_div = stats_bar_block.find("</div>")
        self.assertGreater(close_div, -1)
        inner = stats_bar_block[:close_div]
        self.assertIn('id="metrics-status"', inner,
                      "metrics-status must be inside #stats-bar")

    def test_diag_bar_element_present(self):
        """id="diag-bar" must exist so app.js can show diagnostics severity counts."""
        self.assertIn('id="diag-bar"', _HTML)

    def test_status_msg_element_present(self):
        self.assertIn('id="status-msg"', _HTML)

    def test_stats_bar_present(self):
        self.assertIn('id="stats-bar"', _HTML)

    def test_topbar_present(self):
        self.assertIn('id="topbar"', _HTML)

    def test_graph_svg_present(self):
        self.assertIn('id="graph"', _HTML)

    def test_detail_panel_present(self):
        self.assertIn('id="detail-panel"', _HTML)

    def test_tooltip_present(self):
        self.assertIn('id="tooltip"', _HTML)

    def test_app_js_loaded(self):
        self.assertIn('src="/assets/app.js"', _HTML)

    def test_styles_css_loaded(self):
        self.assertIn('href="/assets/styles.css"', _HTML)

    def test_no_inline_scripts_with_eval(self):
        """No eval() in inline <script> blocks."""
        inline = re.findall(r'<script[^>]*>(.*?)</script>', _HTML, re.DOTALL)
        for block in inline:
            self.assertNotIn("eval(", block)

    def test_charset_utf8(self):
        self.assertIn('charset="utf-8"', _HTML.lower())


class TestAppJSMetricsReferences(unittest.TestCase):
    """app.js must wire up the metrics-status element and related logic."""

    def test_references_metrics_status_id(self):
        """app.js must look up the metrics-status DOM element by id."""
        self.assertIn(
            "metrics-status", _JS,
            "app.js does not reference 'metrics-status' — "
            "glow-state display will be broken.",
        )

    def test_update_metrics_status_function_present(self):
        self.assertIn("updateMetricsStatus", _JS)

    def test_apply_metrics_fn_present(self):
        self.assertIn("applyMetrics", _JS)

    def test_metrics_sse_listener_present(self):
        self.assertIn("'metrics'", _JS)

    def test_no_innerHTML_assignment(self):
        matches = re.findall(r'\.innerHTML\s*=', _JS)
        self.assertEqual(matches, [],
                         f"innerHTML assignment(s) found in app.js: {matches}")


class TestOfflineD3VendoredFiles(unittest.TestCase):
    """Vendored D3 bundle and licence notice must exist on disk."""

    def test_d3_min_js_exists(self):
        """web/vendor/d3.min.js must be present in the package."""
        p = _VENDOR_DIR / "d3.min.js"
        self.assertTrue(p.is_file(), f"Vendored D3 bundle not found: {p}")

    def test_d3_min_js_nonempty(self):
        """d3.min.js must not be an empty file."""
        p = _VENDOR_DIR / "d3.min.js"
        self.assertGreater(p.stat().st_size, 10_000,
                           "d3.min.js is unexpectedly small — may be truncated or missing")

    def test_d3_license_txt_exists(self):
        """web/vendor/D3_LICENSE.txt must be present."""
        p = _VENDOR_DIR / "D3_LICENSE.txt"
        self.assertTrue(p.is_file(), f"D3 licence file not found: {p}")

    def test_d3_license_contains_version(self):
        """D3_LICENSE.txt must mention the D3 version."""
        text = (_VENDOR_DIR / "D3_LICENSE.txt").read_text(encoding="utf-8")
        self.assertRegex(text, r"7\.\d+\.\d+",
                         "D3_LICENSE.txt must state the D3 version (7.x.y)")

    def test_d3_license_contains_copyright(self):
        """D3_LICENSE.txt must reproduce the upstream copyright notice."""
        text = (_VENDOR_DIR / "D3_LICENSE.txt").read_text(encoding="utf-8")
        self.assertIn("Mike Bostock", text,
                      "D3_LICENSE.txt must include the copyright holder name")

    def test_d3_license_contains_source_url(self):
        """D3_LICENSE.txt must include the upstream source URL."""
        text = (_VENDOR_DIR / "D3_LICENSE.txt").read_text(encoding="utf-8")
        self.assertIn("github.com/d3/d3", text,
                      "D3_LICENSE.txt must include the upstream source URL")

    def test_d3_license_contains_license_name(self):
        """D3_LICENSE.txt must state the licence name (ISC)."""
        text = (_VENDOR_DIR / "D3_LICENSE.txt").read_text(encoding="utf-8")
        self.assertIn("ISC", text,
                      "D3_LICENSE.txt must state the licence name (ISC)")


class TestOfflineD3IndexHTML(unittest.TestCase):
    """index.html must reference the local vendor D3 bundle, not the CDN."""

    def test_index_references_vendor_d3(self):
        """index.html must load D3 from /vendor/d3.min.js."""
        self.assertIn("/vendor/d3.min.js", _HTML,
                      "index.html must reference /vendor/d3.min.js")

    def test_index_has_no_cdn_jsdelivr_d3(self):
        """index.html must NOT contain a cdn.jsdelivr.net D3 script tag."""
        self.assertNotIn("cdn.jsdelivr.net", _HTML,
                         "index.html must not load D3 from the CDN — "
                         "use the vendored /vendor/d3.min.js instead")

    def test_vendor_d3_script_tag_is_first(self):
        """The /vendor/d3.min.js <script> tag must appear before /assets/app.js."""
        vendor_pos = _HTML.find("/vendor/d3.min.js")
        app_pos    = _HTML.find("/assets/app.js")
        self.assertGreater(vendor_pos, -1, "/vendor/d3.min.js not in index.html")
        self.assertGreater(app_pos, -1, "/assets/app.js not in index.html")
        self.assertLess(vendor_pos, app_pos,
                        "/vendor/d3.min.js must be loaded before /assets/app.js")

    def test_d3_load_failure_shows_visible_error(self):
        """The D3 <script> tag must have an onerror attribute for a visible error message."""
        # Find the vendor d3 script tag
        match = re.search(r'<script[^>]*vendor/d3\.min\.js[^>]*>', _HTML)
        self.assertIsNotNone(match, "Could not find <script> tag for vendor/d3.min.js")
        tag = match.group(0)
        self.assertIn("onerror", tag,
                      "The vendor D3 <script> tag must have an onerror handler "
                      "that shows a visible error when D3 fails to load")


class TestOfflineD3ServerRoute(unittest.TestCase):
    """The server must serve GET /vendor/d3.min.js with the correct content type."""

    def _make_handler(self):
        sys.path.insert(0, str(_ROOT / "src"))
        from docker_topology_live.server import make_handler
        HandlerCls = make_handler(use_sample=True)
        handler = HandlerCls.__new__(HandlerCls)
        handler.wfile = io.BytesIO()
        handler.send_response = MagicMock()
        handler.send_header   = MagicMock()
        handler.end_headers   = MagicMock()
        handler.path          = "/vendor/d3.min.js"
        return handler

    def test_vendor_d3_route_returns_200(self):
        """/vendor/d3.min.js must be served with HTTP 200."""
        handler = self._make_handler()
        handler.do_GET()
        calls = [c.args[0] for c in handler.send_response.call_args_list]
        self.assertIn(200, calls,
                      "GET /vendor/d3.min.js must respond with HTTP 200")

    def test_vendor_d3_route_content_type(self):
        """/vendor/d3.min.js must be served as application/javascript."""
        handler = self._make_handler()
        handler.do_GET()
        header_pairs = [c.args for c in handler.send_header.call_args_list]
        content_types = [v for k, v in header_pairs if k == "Content-Type"]
        self.assertTrue(
            any("javascript" in ct for ct in content_types),
            f"GET /vendor/d3.min.js content type must be application/javascript, "
            f"got: {content_types}",
        )

    def test_vendor_d3_route_returns_nonempty_body(self):
        """/vendor/d3.min.js response body must not be empty."""
        handler = self._make_handler()
        handler.do_GET()
        body = handler.wfile.getvalue()
        self.assertGreater(len(body), 1000,
                           "/vendor/d3.min.js response body is unexpectedly short")

    def test_vendor_only_d3_is_served(self):
        """GET /vendor/ (directory listing) must return 404, not file contents."""
        sys.path.insert(0, str(_ROOT / "src"))
        from docker_topology_live.server import make_handler
        HandlerCls = make_handler(use_sample=True)
        handler = HandlerCls.__new__(HandlerCls)
        handler.wfile = io.BytesIO()
        handler.send_response = MagicMock()
        handler.send_header   = MagicMock()
        handler.end_headers   = MagicMock()
        handler.path          = "/vendor/"
        handler.do_GET()
        calls = [c.args[0] for c in handler.send_response.call_args_list]
        self.assertIn(404, calls,
                      "GET /vendor/ must return 404 — directory listing must not be exposed")


class TestOfflineD3PyprojectToml(unittest.TestCase):
    """pyproject.toml must include vendor assets in package-data."""

    def test_vendor_d3_in_package_data(self):
        """pyproject.toml package-data must include web/vendor/d3.min.js."""
        toml_text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("vendor/d3.min.js", toml_text,
                      "pyproject.toml must include web/vendor/d3.min.js in package-data")

    def test_vendor_license_in_package_data(self):
        """pyproject.toml package-data must include web/vendor/D3_LICENSE.txt."""
        toml_text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("D3_LICENSE.txt", toml_text,
                      "pyproject.toml must include web/vendor/D3_LICENSE.txt in package-data")


class TestOfflineD3SampleMode(unittest.TestCase):
    """Sample mode must work correctly with the vendored D3 (no Docker daemon needed)."""

    def test_sample_topology_returns_sample_true(self):
        """build_sample() must set sample=True without requiring Docker."""
        sys.path.insert(0, str(_ROOT / "src"))
        from docker_topology_live.scanner import build_sample
        topo = build_sample()
        self.assertTrue(topo.sample,
                        "build_sample() must return a topology with sample=True")

    def test_sample_topology_has_nodes(self):
        """build_sample() must return nodes without requiring Docker."""
        sys.path.insert(0, str(_ROOT / "src"))
        from docker_topology_live.scanner import build_sample
        topo = build_sample()
        self.assertGreater(len(topo.nodes), 0,
                           "build_sample() must return at least one node")

    def test_sample_topology_serialises(self):
        """build_sample().to_dict() must produce valid JSON-serialisable output."""
        sys.path.insert(0, str(_ROOT / "src"))
        from docker_topology_live.scanner import build_sample
        topo = build_sample()
        d = topo.to_dict()
        # Must not raise
        serialised = json.dumps(d)
        self.assertGreater(len(serialised), 10)


if __name__ == "__main__":
    unittest.main()
