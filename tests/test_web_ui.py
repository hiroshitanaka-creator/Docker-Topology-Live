"""Tests for the browser UI static assets (index.html and app.js).

These are text-parsing checks that run without a browser or build step.
They guard against accidental omission of required DOM elements and
against security regressions (innerHTML, wildcard CORS in JS, etc.).
"""
import pathlib
import re
import unittest

_ROOT = pathlib.Path(__file__).parent.parent
_HTML = (_ROOT / "src/docker_topology_live/web/index.html").read_text(encoding="utf-8")
_JS   = (_ROOT / "src/docker_topology_live/web/assets/app.js").read_text(encoding="utf-8")


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


if __name__ == "__main__":
    unittest.main()
