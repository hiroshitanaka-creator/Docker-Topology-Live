"""Static/source tests for the browser smoke script and workflow.

These tests verify that:
- scripts/browser_smoke.py exists and is correctly structured
- The script references the correct server flags and safety checks
- .github/workflows/browser-smoke.yml exists and is workflow_dispatch only
- pyproject.toml defines the browser-test optional extra

These tests do NOT require Playwright to be installed.
The normal unit test suite (``python -m unittest discover -s tests -v``) passes
without the ``browser-test`` optional extra.
"""
import pathlib
import unittest

_ROOT = pathlib.Path(__file__).parent.parent
_SCRIPT = _ROOT / "scripts" / "browser_smoke.py"
_WORKFLOW = _ROOT / ".github" / "workflows" / "browser-smoke.yml"
_PYPROJECT = _ROOT / "pyproject.toml"


# ---------------------------------------------------------------------------
# scripts/browser_smoke.py — existence
# ---------------------------------------------------------------------------

class TestBrowserSmokeScriptExists(unittest.TestCase):
    """scripts/browser_smoke.py must exist and be non-empty."""

    def test_script_exists(self):
        self.assertTrue(
            _SCRIPT.is_file(),
            f"scripts/browser_smoke.py not found at {_SCRIPT}",
        )

    def test_script_is_nonempty(self):
        self.assertGreater(
            _SCRIPT.stat().st_size,
            0,
            "scripts/browser_smoke.py must not be empty",
        )


# ---------------------------------------------------------------------------
# scripts/browser_smoke.py — content / correctness
# ---------------------------------------------------------------------------

class TestBrowserSmokeScriptContent(unittest.TestCase):
    """scripts/browser_smoke.py must reference the correct flags and checks."""

    @classmethod
    def setUpClass(cls):
        cls.text = _SCRIPT.read_text(encoding="utf-8")

    # --- Server flags -------------------------------------------------------

    def test_references_sample_flag(self):
        """Script must start the server with --sample (no Docker daemon needed)."""
        self.assertIn(
            "--sample", self.text,
            "browser_smoke.py must pass --sample to the server command",
        )

    def test_references_metrics_flag(self):
        """Script must enable --metrics so sparklines can be validated."""
        self.assertIn(
            "--metrics", self.text,
            "browser_smoke.py must pass --metrics to the server command",
        )

    def test_references_diagnostics_flag(self):
        """Script must enable --diagnostics so the diag-bar can be checked."""
        self.assertIn(
            "--diagnostics", self.text,
            "browser_smoke.py must pass --diagnostics to the server command",
        )

    def test_references_redact_host_paths_flag(self):
        """Script must enable --redact-host-paths for privacy."""
        self.assertIn(
            "--redact-host-paths", self.text,
            "browser_smoke.py must pass --redact-host-paths to the server command",
        )

    # --- Safety constraints -------------------------------------------------

    def test_uses_loopback_address(self):
        """Script must bind to 127.0.0.1 (loopback-only)."""
        self.assertIn(
            "127.0.0.1", self.text,
            "browser_smoke.py must use 127.0.0.1 (loopback address only)",
        )

    def test_no_docker_api_import(self):
        """Script must not import the docker package or call Docker APIs."""
        self.assertNotIn(
            "import docker", self.text,
            "browser_smoke.py must not import the docker package",
        )

    # --- Offline-first D3 checks -------------------------------------------

    def test_checks_vendor_d3(self):
        """Script must verify that /vendor/d3.min.js is loaded from the local vendor."""
        self.assertIn(
            "/vendor/d3.min.js", self.text,
            "browser_smoke.py must check that /vendor/d3.min.js is requested",
        )

    def test_forbids_cdn(self):
        """Script must verify that cdn.jsdelivr.net is NOT contacted."""
        self.assertIn(
            "cdn.jsdelivr.net", self.text,
            "browser_smoke.py must check that no cdn.jsdelivr.net requests are made",
        )

    # --- DOM element checks -------------------------------------------------

    def test_checks_graph_element(self):
        """Script must check for the #graph DOM element."""
        self.assertIn(
            "#graph", self.text,
            "browser_smoke.py must check for the #graph element",
        )

    def test_checks_detail_panel_element(self):
        """Script must check for the #detail-panel DOM element."""
        self.assertIn(
            "#detail-panel", self.text,
            "browser_smoke.py must check for the #detail-panel element",
        )

    def test_checks_status_msg_element(self):
        """Script must check for the #status-msg DOM element."""
        self.assertIn(
            "#status-msg", self.text,
            "browser_smoke.py must check for the #status-msg element",
        )

    # --- Server lifecycle ---------------------------------------------------

    def test_polls_healthz(self):
        """Script must poll /healthz to confirm the server is ready."""
        self.assertIn(
            "/healthz", self.text,
            "browser_smoke.py must poll /healthz for server readiness",
        )

    def test_shuts_down_server(self):
        """Script must terminate or kill the server subprocess when finished."""
        self.assertTrue(
            "terminate" in self.text or "proc.kill" in self.text,
            "browser_smoke.py must shut down the server subprocess cleanly",
        )

    def test_exits_nonzero_on_failure(self):
        """Script must return exit code 1 when any check fails."""
        self.assertIn(
            "return 1", self.text,
            "browser_smoke.py must return exit code 1 on failure",
        )

    # --- Playwright unavailable error handling ------------------------------

    def test_install_instructions_on_missing_playwright(self):
        """Script must print clear install instructions when Playwright is missing."""
        self.assertIn(
            "pip install -e .[browser-test]", self.text,
            "browser_smoke.py must print 'pip install -e .[browser-test]' "
            "when Playwright is not available",
        )

    def test_does_not_silently_pass_without_playwright(self):
        """Script must call sys.exit or raise when Playwright is missing, not silently pass."""
        self.assertIn(
            "sys.exit", self.text,
            "browser_smoke.py must call sys.exit when Playwright is not installed "
            "— it must not silently pass",
        )


# ---------------------------------------------------------------------------
# .github/workflows/browser-smoke.yml — existence and structure
# ---------------------------------------------------------------------------

class TestBrowserSmokeWorkflowExists(unittest.TestCase):
    """The browser-smoke GitHub Actions workflow file must exist."""

    def test_workflow_file_exists(self):
        self.assertTrue(
            _WORKFLOW.is_file(),
            f".github/workflows/browser-smoke.yml not found at {_WORKFLOW}",
        )

    def test_workflow_is_nonempty(self):
        self.assertGreater(
            _WORKFLOW.stat().st_size,
            0,
            ".github/workflows/browser-smoke.yml must not be empty",
        )


class TestBrowserSmokeWorkflowContent(unittest.TestCase):
    """The browser-smoke workflow must be correctly and safely configured."""

    @classmethod
    def setUpClass(cls):
        cls.text = _WORKFLOW.read_text(encoding="utf-8")

    def test_is_workflow_dispatch_only(self):
        """Workflow trigger must be workflow_dispatch (manual only, not on every push/PR)."""
        self.assertIn(
            "workflow_dispatch", self.text,
            "browser-smoke.yml must use the workflow_dispatch trigger",
        )

    def test_installs_browser_test_extra(self):
        """Workflow must install the [browser-test] optional extra."""
        self.assertIn(
            "browser-test", self.text,
            "browser-smoke.yml must install the [browser-test] optional extra",
        )

    def test_installs_playwright_chromium(self):
        """Workflow must install Playwright Chromium."""
        self.assertIn(
            "chromium", self.text,
            "browser-smoke.yml must install Playwright Chromium",
        )

    def test_runs_browser_smoke_script(self):
        """Workflow must run scripts/browser_smoke.py."""
        self.assertIn(
            "browser_smoke.py", self.text,
            "browser-smoke.yml must run scripts/browser_smoke.py",
        )

    def test_no_publish_action_steps(self):
        """Workflow must not contain actual publish / PyPI upload action steps."""
        # Check for known publish action patterns (not just the word "publish")
        self.assertNotIn(
            "pypa/gh-action-pypi-publish", self.text,
            "browser-smoke.yml must not contain a pypa publish action",
        )
        self.assertNotIn(
            "twine upload", self.text,
            "browser-smoke.yml must not contain a twine upload step",
        )

    def test_no_pypi_upload_reference(self):
        """Workflow must not contain a step that uploads to PyPI."""
        self.assertNotIn(
            "upload-to-pypi", self.text.lower(),
            "browser-smoke.yml must not upload to PyPI",
        )

    def test_no_git_tag_creation(self):
        """Workflow must not create git tags."""
        self.assertNotIn(
            "git tag", self.text,
            "browser-smoke.yml must not create git tags",
        )

    def test_does_not_trigger_on_push(self):
        """Workflow must NOT trigger on push (no automatic runs on every commit)."""
        # The trigger block is `on: workflow_dispatch` only.
        # There must be no standalone `push:` trigger key.
        import re
        # Look for a top-level push trigger (indented under `on:`)
        push_trigger = re.search(r'^\s{0,4}push\s*:', self.text, re.MULTILINE)
        self.assertIsNone(
            push_trigger,
            "browser-smoke.yml must NOT trigger on push; "
            "use workflow_dispatch only to avoid adding cost to every commit",
        )


# ---------------------------------------------------------------------------
# pyproject.toml — browser-test optional extra
# ---------------------------------------------------------------------------

class TestPyprojectBrowserTestExtra(unittest.TestCase):
    """pyproject.toml must declare the browser-test optional extra correctly."""

    @classmethod
    def setUpClass(cls):
        cls.toml = _PYPROJECT.read_text(encoding="utf-8")

    def test_browser_test_extra_present(self):
        """pyproject.toml must define a browser-test optional extra."""
        self.assertIn(
            "browser-test", self.toml,
            "pyproject.toml must define a [browser-test] optional extra",
        )

    def test_playwright_in_browser_test_extra(self):
        """The browser-test extra must include playwright."""
        self.assertIn(
            "playwright", self.toml,
            "pyproject.toml browser-test extra must include playwright",
        )

    def test_runtime_dependencies_remain_empty(self):
        """Core runtime dependencies must remain empty — browser test is optional."""
        self.assertIn(
            "dependencies = []", self.toml,
            "pyproject.toml core dependencies must remain empty "
            "(browser-test dependency must be optional only)",
        )


if __name__ == "__main__":
    unittest.main()
