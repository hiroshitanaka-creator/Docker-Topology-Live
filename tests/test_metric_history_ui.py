"""Static source tests for browser-local metric history and sparkline UI (Goal 11).

All tests inspect the source text of app.js and related web assets.
No browser runtime is required.

Coverage:
- METRIC_HISTORY_LIMIT constant is present
- metricsHistory Map is declared
- recordMetricsHistory function is present
- getMetricHistory function is present
- makeSparkline function is present
- renderMetricHistorySection function is present
- selected detail panel metric-history refresh path is present
- createElementNS used for SVG construction in makeSparkline
- No innerHTML in app.js (regression guard)
- No innerHTML in index.html (regression guard)
- metrics SSE event listener still present
- Existing applyMetrics function still present
- History does not reference localStorage or sessionStorage
- CSS sparkline classes present in styles.css
- Sparkline section rendered only for container nodes
- applyMetrics calls recordMetricsHistory
- applyMetrics refreshes only the selected metric history section
"""
import os
import re
import unittest

# ── Paths ──────────────────────────────────────────────────────────────────────

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_JS = os.path.join(
    _SRC, "src", "docker_topology_live", "web", "assets", "app.js"
)
_INDEX_HTML = os.path.join(
    _SRC, "src", "docker_topology_live", "web", "index.html"
)
_STYLES_CSS = os.path.join(
    _SRC, "src", "docker_topology_live", "web", "assets", "styles.css"
)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _function_body(src, name, window=2500):
    """Return a JavaScript function body slice for an exact function name.

    Static tests use this helper to avoid false matches such as
    ``applyMetrics`` accidentally matching ``applyMetricsGlow``.  It performs
    a simple brace-balance scan starting at ``function <name>(`` and returns
    the complete function block when possible.
    """
    marker = "function " + name + "("
    idx = src.find(marker)
    if idx == -1:
        return ""

    brace_start = src.find("{", idx)
    if brace_start == -1:
        return src[idx:idx + window]

    depth = 0
    for pos in range(brace_start, len(src)):
        ch = src[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[idx:pos + 1]

    return src[idx:idx + window]


class TestMetricHistoryConstants(unittest.TestCase):
    """METRIC_HISTORY_LIMIT and metricsHistory must be declared."""

    def setUp(self):
        self.src = _read(_APP_JS)

    def test_metric_history_limit_constant_present(self):
        """METRIC_HISTORY_LIMIT constant must be defined."""
        self.assertIn(
            "METRIC_HISTORY_LIMIT",
            self.src,
            "app.js must define METRIC_HISTORY_LIMIT",
        )

    def test_metric_history_limit_is_positive_integer(self):
        """METRIC_HISTORY_LIMIT must be assigned a positive integer value."""
        m = re.search(r"METRIC_HISTORY_LIMIT\s*=\s*(\d+)", self.src)
        self.assertIsNotNone(m, "METRIC_HISTORY_LIMIT must be assigned an integer")
        self.assertGreater(int(m.group(1)), 0, "METRIC_HISTORY_LIMIT must be > 0")

    def test_metrics_history_map_declared(self):
        """metricsHistory Map must be declared."""
        self.assertIn(
            "metricsHistory",
            self.src,
            "app.js must declare metricsHistory",
        )

    def test_metrics_history_is_a_map(self):
        """metricsHistory must be instantiated as a Map."""
        self.assertIn(
            "new Map()",
            self.src,
            "app.js must use new Map() for metricsHistory",
        )


class TestMetricHistoryFunctions(unittest.TestCase):
    """recordMetricsHistory and getMetricHistory must be present."""

    def setUp(self):
        self.src = _read(_APP_JS)

    def test_record_metrics_history_function_present(self):
        """recordMetricsHistory function must be defined."""
        self.assertIn(
            "recordMetricsHistory",
            self.src,
            "app.js must define recordMetricsHistory",
        )

    def test_get_metric_history_function_present(self):
        """getMetricHistory function must be defined."""
        self.assertIn(
            "getMetricHistory",
            self.src,
            "app.js must define getMetricHistory",
        )

    def test_record_metrics_history_accepts_containers(self):
        """recordMetricsHistory must iterate over containers array."""
        self.assertIn(
            "containers",
            self.src,
            "recordMetricsHistory must reference .containers from the metrics doc",
        )

    def test_history_rolling_window_enforced(self):
        """History must be trimmed to METRIC_HISTORY_LIMIT via splice."""
        self.assertIn(
            "splice",
            self.src,
            "metricsHistory rolling window must use splice() to trim old samples",
        )

    def test_history_uses_history_limit(self):
        """History pruning must reference METRIC_HISTORY_LIMIT."""
        idx = self.src.find("recordMetricsHistory")
        self.assertGreater(idx, -1)
        section = self.src[idx:idx + 2000]
        self.assertIn(
            "METRIC_HISTORY_LIMIT",
            section,
            "recordMetricsHistory must reference METRIC_HISTORY_LIMIT for the rolling window",
        )


class TestSparklineFunctions(unittest.TestCase):
    """makeSparkline and renderMetricHistorySection must be present and correct."""

    def setUp(self):
        self.src = _read(_APP_JS)

    def test_make_sparkline_function_present(self):
        """makeSparkline function must be defined."""
        self.assertIn(
            "makeSparkline",
            self.src,
            "app.js must define makeSparkline",
        )

    def test_render_metric_history_section_function_present(self):
        """renderMetricHistorySection function must be defined."""
        self.assertIn(
            "renderMetricHistorySection",
            self.src,
            "app.js must define renderMetricHistorySection",
        )

    def test_sparkline_uses_create_element_ns(self):
        """makeSparkline must use createElementNS for SVG construction."""
        self.assertIn(
            "createElementNS",
            self.src,
            "makeSparkline must use createElementNS — no innerHTML for SVG",
        )

    def test_sparkline_uses_svg_namespace(self):
        """makeSparkline must reference the SVG namespace URI."""
        self.assertIn(
            "http://www.w3.org/2000/svg",
            self.src,
            "makeSparkline must use SVG namespace 'http://www.w3.org/2000/svg'",
        )

    def test_sparkline_creates_polyline(self):
        """makeSparkline must create a polyline element for the sparkline stroke."""
        self.assertIn(
            "polyline",
            self.src,
            "makeSparkline must create a polyline SVG element",
        )

    def test_sparkline_creates_circle_dot(self):
        """makeSparkline must create a circle dot on the latest value."""
        section = _function_body(self.src, "makeSparkline")
        self.assertIn(
            "'circle'",
            section,
            "makeSparkline must create a circle element for the latest-value dot",
        )

    def test_sparkline_handles_fewer_than_2_samples(self):
        """makeSparkline must return early when samples.length < 2."""
        section = _function_body(self.src, "makeSparkline")
        self.assertIn(
            "length < 2",
            section,
            "makeSparkline must guard against fewer than 2 samples",
        )

    def test_render_history_container_only(self):
        """renderMetricHistorySection must guard for container kind."""
        section = _function_body(self.src, "renderMetricHistorySection")
        self.assertIn(
            "container",
            section,
            "renderMetricHistorySection must check d.kind === 'container'",
        )

    def test_render_history_not_enough_message(self):
        """renderMetricHistorySection must show a message when history is insufficient."""
        self.assertIn(
            "Not enough history yet",
            self.src,
            "renderMetricHistorySection must show 'Not enough history yet.' for < 2 samples",
        )

    def test_cpu_sparkline_spec_present(self):
        """CPU% sparkline spec must be present in renderMetricHistorySection."""
        self.assertIn(
            "cpuPercent",
            self.src,
            "renderMetricHistorySection must include a CPU% sparkline",
        )

    def test_memory_sparkline_spec_present(self):
        """Memory% sparkline spec must be present in renderMetricHistorySection."""
        self.assertIn(
            "memoryPercent",
            self.src,
            "renderMetricHistorySection must include a Memory% sparkline",
        )


class TestApplyMetricsIntegration(unittest.TestCase):
    """applyMetrics must call recordMetricsHistory."""

    def setUp(self):
        self.src = _read(_APP_JS)

    def test_apply_metrics_calls_record_history(self):
        """applyMetrics must call recordMetricsHistory to accumulate history."""
        section = _function_body(self.src, "applyMetrics")
        self.assertIn(
            "recordMetricsHistory",
            section,
            "applyMetrics must call recordMetricsHistory",
        )

    def test_apply_metrics_function_still_present(self):
        """applyMetrics function must still exist."""
        self.assertIn(
            "function applyMetrics(",
            self.src,
            "applyMetrics must still be defined",
        )

    def test_metrics_sse_listener_still_present(self):
        """SSE 'metrics' event listener must still be wired."""
        self.assertIn(
            "addEventListener('metrics'",
            self.src,
            "app.js must still listen for 'metrics' SSE events",
        )

    def test_on_node_click_calls_render_history_section(self):
        """onNodeClick must call renderMetricHistorySection."""
        section = _function_body(self.src, "onNodeClick")
        self.assertIn(
            "renderMetricHistorySection",
            section,
            "onNodeClick must call renderMetricHistorySection for the detail panel",
        )


class TestSelectedSparklineRefresh(unittest.TestCase):
    """Open detail panel should refresh only the selected node's metric history section."""

    def setUp(self):
        self.src = _read(_APP_JS)

    def test_selected_detail_node_state_declared(self):
        self.assertIn(
            "selectedDetailNode",
            self.src,
            "app.js must track the currently selected detail-panel node",
        )

    def test_on_node_click_sets_selected_detail_node(self):
        section = _function_body(self.src, "onNodeClick")
        self.assertIn(
            "selectedDetailNode = d",
            section,
            "onNodeClick must remember the selected node for later sparkline refresh",
        )

    def test_close_detail_panel_clears_selected_node(self):
        section = _function_body(self.src, "closeDetailPanel")
        self.assertIn(
            "selectedDetailNode = null",
            section,
            "closeDetailPanel must clear selectedDetailNode",
        )

    def test_apply_metrics_refreshes_selected_metric_history(self):
        section = _function_body(self.src, "applyMetrics")
        self.assertIn(
            "recordMetricsHistory(data)",
            section,
            "applyMetrics must still record history first",
        )
        self.assertIn(
            "refreshSelectedMetricHistory()",
            section,
            "applyMetrics must refresh the open selected node's sparkline section",
        )

    def test_refresh_selected_metric_history_function_present(self):
        self.assertIn(
            "function refreshSelectedMetricHistory(",
            self.src,
            "app.js must define refreshSelectedMetricHistory",
        )

    def test_refresh_selected_metric_history_checks_container(self):
        section = _function_body(self.src, "refreshSelectedMetricHistory")
        self.assertIn(
            "selectedDetailNode.kind !== 'container'",
            section,
            "refreshSelectedMetricHistory must skip non-container nodes",
        )

    def test_refresh_selected_metric_history_checks_panel_visible(self):
        section = _function_body(self.src, "refreshSelectedMetricHistory")
        self.assertIn(
            "classList.contains('hidden')",
            section,
            "refreshSelectedMetricHistory must not update a hidden detail panel",
        )

    def test_refresh_selected_metric_history_replaces_only_section(self):
        section = _function_body(self.src, "refreshSelectedMetricHistory")
        self.assertIn(
            "replaceWith(buildMetricHistorySection(selectedDetailNode))",
            section,
            "refreshSelectedMetricHistory must replace only the existing metric history section",
        )
        self.assertNotIn(
            "render(",
            section,
            "refreshSelectedMetricHistory must not re-render the whole graph",
        )
        self.assertNotIn(
            "loadTopology",
            section,
            "refreshSelectedMetricHistory must not refetch topology",
        )

    def test_metric_history_section_has_stable_sanitized_id(self):
        self.assertIn(
            "function metricHistorySectionId(",
            self.src,
            "app.js must define a stable id helper for the metric history section",
        )
        section = _function_body(self.src, "metricHistorySectionId")
        self.assertIn(
            "replace(/[^a-zA-Z0-9_-]/g, '-')",
            section,
            "metricHistorySectionId must sanitize node ids before using them as DOM ids",
        )

    def test_render_metric_history_section_uses_build_helper(self):
        section = _function_body(self.src, "renderMetricHistorySection")
        self.assertIn(
            "buildMetricHistorySection(d)",
            section,
            "renderMetricHistorySection must use the reusable build helper",
        )

    def test_document_click_does_not_close_when_clicking_detail_panel(self):
        self.assertIn(
            "#detail-panel",
            self.src,
            "document click handler should avoid closing the panel when clicking inside it",
        )


class TestNoInnerHTMLRegression(unittest.TestCase):
    """No innerHTML assignments in app.js or index.html (regression guard)."""

    def setUp(self):
        self.app_js_src = _read(_APP_JS)
        self.index_html_src = _read(_INDEX_HTML)

    def test_no_innerHTML_assignment_in_app_js(self):
        """app.js must not assign to innerHTML."""
        matches = re.findall(r'\.innerHTML\s*=', self.app_js_src)
        self.assertEqual(
            matches, [],
            "app.js must not assign to innerHTML; found: " + str(matches),
        )

    def test_no_innerHTML_assignment_in_index_html(self):
        """index.html must not assign to innerHTML."""
        matches = re.findall(r'\.innerHTML\s*=', self.index_html_src)
        self.assertEqual(
            matches, [],
            "index.html must not assign to innerHTML; found: " + str(matches),
        )


class TestNoLocalStoragePersistence(unittest.TestCase):
    """Metric history must not be persisted to localStorage or sessionStorage."""

    def setUp(self):
        self.src = _read(_APP_JS)

    def test_no_local_storage(self):
        """app.js must not use localStorage for metric history."""
        self.assertNotIn(
            "localStorage",
            self.src,
            "Metric history must not be persisted to localStorage",
        )

    def test_no_session_storage(self):
        """app.js must not use sessionStorage for metric history."""
        self.assertNotIn(
            "sessionStorage",
            self.src,
            "Metric history must not be persisted to sessionStorage",
        )


class TestSparklineCSS(unittest.TestCase):
    """Sparkline CSS classes must be present in styles.css."""

    def setUp(self):
        self.css = _read(_STYLES_CSS)

    def test_sparkline_section_class_present(self):
        """styles.css must define .sparkline-section."""
        self.assertIn(
            ".sparkline-section",
            self.css,
            "styles.css must define .sparkline-section",
        )

    def test_sparkline_label_class_present(self):
        """styles.css must define .sparkline-label."""
        self.assertIn(
            ".sparkline-label",
            self.css,
            "styles.css must define .sparkline-label",
        )

    def test_sparkline_empty_class_present(self):
        """styles.css must define .sparkline-empty."""
        self.assertIn(
            ".sparkline-empty",
            self.css,
            "styles.css must define .sparkline-empty",
        )


if __name__ == "__main__":
    unittest.main()
