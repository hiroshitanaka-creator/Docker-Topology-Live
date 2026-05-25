"""Static tests for .github/workflows/linux-docker-validation.yml.

These tests verify the structure and safety constraints of the Linux Docker
full-validation workflow (Goal 17.2) without running Docker, GitHub Actions,
or any live daemon.

Checks performed:
- workflow file exists and is non-empty
- workflow uses workflow_dispatch (manual trigger only)
- workflow does NOT trigger on push
- workflow does NOT trigger on pull_request
- workflow does NOT trigger on schedule
- workflow does not reference secrets.
- workflow does not contain release, tag, or PyPI publish actions
- all created containers use the dtl-validate-* naming convention
- workflow has 'if: always()' cleanup step
- cleanup removes dtl-validate-* containers
- cleanup removes dtl-validate-* networks
- summary artifact name is linux-docker-validation-summary
- summary file path is /tmp/linux-docker-validation-summary.md
- workflow references app.py scan
- workflow references app.py diagnose
- workflow references --metrics
- workflow references --diagnostics
- workflow references --prometheus
- workflow checks /api/topology
- workflow checks /api/metrics
- workflow checks /api/diagnostics
- workflow checks /metrics (Prometheus endpoint)
- workflow references /api/events (SSE)
- workflow checks for absence of traceback text
- workflow does not claim production readiness
- workflow text acknowledges public container images may be pulled if not cached
- workflow runs on ubuntu-latest
- workflow does not use push, pull_request, or schedule triggers
- CORS default check is present (--allow-cors not used)
- Prometheus is opt-in (--prometheus present for this validation workflow)

These tests run as part of the normal unit test suite:
    PYTHONPATH=src python -m unittest discover -s tests -v

No Docker daemon is required.
"""
import pathlib
import re
import unittest

_ROOT = pathlib.Path(__file__).parent.parent
_WORKFLOW = _ROOT / ".github" / "workflows" / "linux-docker-validation.yml"


# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------

class TestLinuxDockerValidationWorkflowExists(unittest.TestCase):
    """The workflow file must exist and be non-empty."""

    def test_workflow_file_exists(self):
        self.assertTrue(
            _WORKFLOW.is_file(),
            f".github/workflows/linux-docker-validation.yml not found at {_WORKFLOW}",
        )

    def test_workflow_is_nonempty(self):
        self.assertGreater(
            _WORKFLOW.stat().st_size,
            0,
            ".github/workflows/linux-docker-validation.yml must not be empty",
        )


# ---------------------------------------------------------------------------
# Content / structure
# ---------------------------------------------------------------------------

class TestLinuxDockerValidationWorkflowContent(unittest.TestCase):
    """The workflow file must be correctly and safely structured."""

    @classmethod
    def setUpClass(cls):
        cls.text = _WORKFLOW.read_text(encoding="utf-8")

    # --- Trigger: workflow_dispatch only ------------------------------------

    def test_uses_workflow_dispatch(self):
        """Workflow must use workflow_dispatch so it is manual-only."""
        self.assertIn(
            "workflow_dispatch", self.text,
            "linux-docker-validation.yml must use the workflow_dispatch trigger",
        )

    def test_no_push_trigger(self):
        """Workflow must NOT trigger on push."""
        push_trigger = re.search(r'^\s{0,4}push\s*:', self.text, re.MULTILINE)
        self.assertIsNone(
            push_trigger,
            "linux-docker-validation.yml must NOT trigger on push; "
            "use workflow_dispatch only",
        )

    def test_no_pull_request_trigger(self):
        """Workflow must NOT trigger on pull_request."""
        pr_trigger = re.search(r'^\s{0,4}pull_request\s*:', self.text, re.MULTILINE)
        self.assertIsNone(
            pr_trigger,
            "linux-docker-validation.yml must NOT trigger on pull_request; "
            "use workflow_dispatch only",
        )

    def test_no_schedule_trigger(self):
        """Workflow must NOT trigger on schedule."""
        sched_trigger = re.search(r'^\s{0,4}schedule\s*:', self.text, re.MULTILINE)
        self.assertIsNone(
            sched_trigger,
            "linux-docker-validation.yml must NOT trigger on schedule; "
            "use workflow_dispatch only",
        )

    # --- No secrets --------------------------------------------------------

    def test_no_secrets_usage(self):
        """Workflow must not reference any secrets."""
        self.assertNotIn(
            "secrets.", self.text,
            "linux-docker-validation.yml must not use secrets",
        )

    # --- No release / tag / publish actions --------------------------------

    def test_no_pypi_publish_action(self):
        """Workflow must not contain a PyPI publish action."""
        self.assertNotIn(
            "pypa/gh-action-pypi-publish", self.text,
            "linux-docker-validation.yml must not contain a PyPI publish action",
        )

    def test_no_twine_upload(self):
        """Workflow must not contain a twine upload step."""
        self.assertNotIn(
            "twine upload", self.text,
            "linux-docker-validation.yml must not contain a twine upload step",
        )

    def test_no_git_tag_creation(self):
        """Workflow must not create git tags."""
        self.assertNotIn(
            "git tag", self.text,
            "linux-docker-validation.yml must not create git tags",
        )

    def test_no_github_release_action(self):
        """Workflow must not create GitHub releases."""
        self.assertNotIn(
            "create-release", self.text.lower(),
            "linux-docker-validation.yml must not create GitHub releases",
        )

    def test_no_upload_to_pypi(self):
        """Workflow must not upload to PyPI."""
        self.assertNotIn(
            "upload-to-pypi", self.text.lower(),
            "linux-docker-validation.yml must not upload to PyPI",
        )

    # --- Container naming convention ---------------------------------------

    def test_only_dtl_validate_containers(self):
        """All 'docker run --name' containers must use the dtl-validate-* prefix.

        This ensures no unintended containers are created and all containers
        can be identified and cleaned up reliably.
        """
        name_pattern = re.compile(r'--name\s+(\S+)', re.MULTILINE)
        names = name_pattern.findall(self.text)
        # Skip template expressions (e.g. ${{ matrix.name }})
        plain_names = [n for n in names if not n.startswith('${{')]
        self.assertTrue(
            len(plain_names) > 0,
            "linux-docker-validation.yml must have at least one --name container",
        )
        for name in plain_names:
            self.assertTrue(
                name.startswith("dtl-validate-"),
                f"Container name '{name}' must start with 'dtl-validate-'",
            )

    # --- Cleanup -----------------------------------------------------------

    def test_has_docker_rm_cleanup(self):
        """Workflow must have a 'docker rm -f' step to remove containers."""
        self.assertIn(
            "docker rm -f", self.text,
            "linux-docker-validation.yml must include a 'docker rm -f' cleanup step",
        )

    def test_cleanup_uses_if_always(self):
        """Cleanup step must use 'if: always()' to run even when earlier steps fail."""
        self.assertIn(
            "if: always()", self.text,
            "linux-docker-validation.yml must have a cleanup step with 'if: always()'",
        )

    def test_cleanup_removes_dtl_validate_containers(self):
        """The if: always() cleanup must remove dtl-validate-* containers."""
        rm_pattern = re.compile(r'docker rm -f[^\n]+', re.MULTILINE)
        rm_lines = rm_pattern.findall(self.text)
        all_rm_text = ' '.join(rm_lines)
        self.assertIn(
            'dtl-validate-', all_rm_text,
            "Cleanup must include dtl-validate-* containers in a 'docker rm -f' line",
        )

    def test_cleanup_removes_dtl_validate_networks(self):
        """The if: always() cleanup must remove dtl-validate-* networks."""
        self.assertIn(
            "docker network rm", self.text,
            "Cleanup must include 'docker network rm' for dtl-validate-* networks",
        )
        net_rm_pattern = re.compile(r'docker network rm[^\n]+', re.MULTILINE)
        net_rm_lines = net_rm_pattern.findall(self.text)
        all_net_rm_text = ' '.join(net_rm_lines)
        self.assertIn(
            'dtl-validate-', all_net_rm_text,
            "Cleanup must remove dtl-validate-* networks",
        )

    # --- Artifact upload ---------------------------------------------------

    def test_summary_artifact_name(self):
        """Workflow must use artifact name 'linux-docker-validation-summary'."""
        self.assertIn(
            "linux-docker-validation-summary", self.text,
            "linux-docker-validation.yml must upload 'linux-docker-validation-summary' artifact",
        )

    def test_summary_file_path(self):
        """Workflow must reference the summary .md file at /tmp/linux-docker-validation-summary.md."""
        self.assertIn(
            "/tmp/linux-docker-validation-summary.md", self.text,
            "linux-docker-validation.yml must reference /tmp/linux-docker-validation-summary.md",
        )

    def test_uses_upload_artifact_action(self):
        """Workflow must use actions/upload-artifact."""
        self.assertIn(
            "upload-artifact", self.text,
            "linux-docker-validation.yml must use actions/upload-artifact",
        )

    # --- Required app.py subcommands ---------------------------------------

    def test_references_app_py_scan(self):
        """Workflow must run 'app.py scan'."""
        self.assertIn(
            "app.py scan", self.text,
            "linux-docker-validation.yml must reference 'app.py scan'",
        )

    def test_references_app_py_diagnose(self):
        """Workflow must run 'app.py diagnose'."""
        self.assertIn(
            "app.py diagnose", self.text,
            "linux-docker-validation.yml must reference 'app.py diagnose'",
        )

    def test_references_metrics_flag(self):
        """Workflow must reference --metrics (live metrics enable)."""
        self.assertIn(
            "--metrics", self.text,
            "linux-docker-validation.yml must reference '--metrics'",
        )

    def test_references_diagnostics_flag(self):
        """Workflow must reference --diagnostics (live diagnostics enable)."""
        self.assertIn(
            "--diagnostics", self.text,
            "linux-docker-validation.yml must reference '--diagnostics'",
        )

    def test_references_prometheus_flag(self):
        """Workflow must reference --prometheus (Prometheus endpoint enable)."""
        self.assertIn(
            "--prometheus", self.text,
            "linux-docker-validation.yml must reference '--prometheus'",
        )

    # --- Required API endpoint checks --------------------------------------

    def test_checks_api_topology(self):
        """Workflow must check /api/topology."""
        self.assertIn(
            "/api/topology", self.text,
            "linux-docker-validation.yml must check '/api/topology'",
        )

    def test_checks_api_metrics(self):
        """Workflow must check /api/metrics."""
        self.assertIn(
            "/api/metrics", self.text,
            "linux-docker-validation.yml must check '/api/metrics'",
        )

    def test_checks_api_diagnostics(self):
        """Workflow must check /api/diagnostics."""
        self.assertIn(
            "/api/diagnostics", self.text,
            "linux-docker-validation.yml must check '/api/diagnostics'",
        )

    def test_checks_prometheus_endpoint(self):
        """Workflow must check /metrics (Prometheus endpoint)."""
        self.assertIn(
            "/metrics", self.text,
            "linux-docker-validation.yml must check '/metrics' (Prometheus endpoint)",
        )

    def test_references_api_events(self):
        """Workflow must reference /api/events (SSE endpoint)."""
        self.assertIn(
            "/api/events", self.text,
            "linux-docker-validation.yml must reference '/api/events'",
        )

    # --- Safety checks -----------------------------------------------------

    def test_checks_for_absent_traceback_text(self):
        """Workflow must check for absence of Python traceback text in output."""
        self.assertIn(
            "Traceback (most recent call last)", self.text,
            "linux-docker-validation.yml must check for absence of Python traceback text",
        )

    def test_no_production_readiness_claim(self):
        """Workflow must not claim production readiness."""
        self.assertNotIn(
            "production ready", self.text.lower(),
            "linux-docker-validation.yml must not claim production readiness",
        )
        self.assertNotIn(
            "production-ready", self.text.lower(),
            "linux-docker-validation.yml must not claim production readiness",
        )

    def test_acknowledges_public_image_pulls(self):
        """Workflow must acknowledge that public container images may be pulled if not cached."""
        # The workflow should mention that images may be pulled from Docker Hub
        has_pull_note = (
            "pulled by Docker if not cached" in self.text
            or "may be pulled" in self.text
            or "pulled if not cached" in self.text
        )
        self.assertTrue(
            has_pull_note,
            "linux-docker-validation.yml must acknowledge that public container images "
            "may be pulled by Docker if not cached on the runner",
        )

    def test_uses_ubuntu_latest_runner(self):
        """Workflow must run on ubuntu-latest."""
        self.assertIn(
            "ubuntu-latest", self.text,
            "linux-docker-validation.yml must run on ubuntu-latest",
        )

    def test_no_external_curl_to_external_host(self):
        """Workflow must not send data to external URLs via curl."""
        self.assertNotIn(
            "curl https://", self.text,
            "linux-docker-validation.yml must not use curl to send data externally",
        )

    def test_references_compile_check(self):
        """Workflow must run a compile check."""
        self.assertIn(
            "compileall", self.text,
            "linux-docker-validation.yml must run 'python -m compileall'",
        )

    def test_references_unit_tests(self):
        """Workflow must run the unit test suite."""
        self.assertIn(
            "unittest discover", self.text,
            "linux-docker-validation.yml must run 'python -m unittest discover'",
        )

    def test_references_app_py_doctor(self):
        """Workflow must run 'app.py doctor'."""
        self.assertIn(
            "app.py doctor", self.text,
            "linux-docker-validation.yml must run 'app.py doctor'",
        )

    def test_issue_34_mentioned(self):
        """Workflow must mention Issue #34."""
        self.assertIn(
            "#34", self.text,
            "linux-docker-validation.yml must mention Issue #34",
        )

    def test_no_cors_allow_flag(self):
        """Workflow must not pass --allow-cors to app.py serve (CORS default must stay off).

        The workflow may mention '--allow-cors' in comments or summary strings to
        document that it is NOT used.  What must not happen is '--allow-cors' being
        passed as an actual flag to any 'app.py serve' invocation.
        """
        serve_invocations = re.findall(r'app\.py serve[^\n]+', self.text)
        for line in serve_invocations:
            self.assertNotIn(
                "--allow-cors", line,
                f"app.py serve must not use '--allow-cors'; "
                f"CORS default must remain off.  Offending line: {line!r}",
            )

    def test_daemon_availability_tracked(self):
        """Workflow must track whether the Docker daemon is available."""
        self.assertIn(
            "daemon_available", self.text,
            "linux-docker-validation.yml must track daemon_available for conditional steps",
        )


# ---------------------------------------------------------------------------
# CHANGELOG.md — Goal 17.2 entry
# ---------------------------------------------------------------------------

_CHANGELOG = _ROOT / "CHANGELOG.md"


class TestChangelogLinuxDockerValidationEntry(unittest.TestCase):
    """CHANGELOG.md must have correct Goal 17.2 entries."""

    @classmethod
    def setUpClass(cls):
        cls.changelog = _CHANGELOG.read_text(encoding="utf-8")

    def test_changelog_exists(self):
        """CHANGELOG.md must exist."""
        self.assertTrue(
            _CHANGELOG.is_file(),
            f"CHANGELOG.md not found at {_CHANGELOG}",
        )

    def test_changelog_references_linux_docker_validation(self):
        """CHANGELOG.md must mention the linux-docker-validation workflow."""
        self.assertIn(
            "linux-docker-validation", self.changelog,
            "CHANGELOG.md must reference the linux-docker-validation workflow",
        )

    def test_changelog_acknowledges_image_pulls(self):
        """CHANGELOG.md must acknowledge that Docker may pull public container images."""
        has_pull_note = (
            "Docker may\npull public container images" in self.changelog
            or "public container images may be pulled" in self.changelog
            or "pulled by Docker if not cached" in self.changelog
        )
        self.assertTrue(
            has_pull_note,
            "CHANGELOG.md must acknowledge that Docker may pull public container images "
            "if they are not cached on the runner",
        )

    def test_no_external_service_calls_phrase(self):
        """CHANGELOG.md must not contain the phrase 'no external service calls'."""
        self.assertNotIn(
            "no external service calls", self.changelog,
            "CHANGELOG.md must not say 'no external service calls'; "
            "validation workflows may pull public container images from Docker Hub",
        )

    def test_changelog_states_no_runtime_changes(self):
        """CHANGELOG.md Goal 17.2 entry must state no runtime behaviour changes."""
        self.assertIn(
            "No runtime", self.changelog,
            "CHANGELOG.md must state 'No runtime' behaviour changes for Goal 17.2",
        )


# ---------------------------------------------------------------------------
# docs/ISSUE_TRIAGE.md — Goal 17.2 section
# ---------------------------------------------------------------------------

_ISSUE_TRIAGE = _ROOT / "docs" / "ISSUE_TRIAGE.md"


class TestIssueTriage172Entry(unittest.TestCase):
    """docs/ISSUE_TRIAGE.md must have a Goal 17.2 section."""

    @classmethod
    def setUpClass(cls):
        cls.text = _ISSUE_TRIAGE.read_text(encoding="utf-8")

    def test_issue_triage_exists(self):
        """docs/ISSUE_TRIAGE.md must exist."""
        self.assertTrue(
            _ISSUE_TRIAGE.is_file(),
            f"docs/ISSUE_TRIAGE.md not found at {_ISSUE_TRIAGE}",
        )

    def test_issue_triage_mentions_goal_172(self):
        """docs/ISSUE_TRIAGE.md must mention Goal 17.2."""
        self.assertIn(
            "17.2", self.text,
            "docs/ISSUE_TRIAGE.md must mention Goal 17.2",
        )

    def test_issue_34_remains_open_statement(self):
        """docs/ISSUE_TRIAGE.md must state #34 remains open until workflow is run."""
        has_open_note = (
            "#34 remains open" in self.text
            or "Issue #34 remains open" in self.text
            or "remains open until" in self.text
        )
        self.assertTrue(
            has_open_note,
            "docs/ISSUE_TRIAGE.md must state that Issue #34 remains open "
            "until the workflow is run and the result is recorded",
        )


# ---------------------------------------------------------------------------
# docs/AI_WORKFLOW.md — Goal 17.2 planning phase
# ---------------------------------------------------------------------------

_AI_WORKFLOW = _ROOT / "docs" / "AI_WORKFLOW.md"


class TestAIWorkflow172Entry(unittest.TestCase):
    """docs/AI_WORKFLOW.md must reference Goal 17.2."""

    @classmethod
    def setUpClass(cls):
        cls.text = _AI_WORKFLOW.read_text(encoding="utf-8")

    def test_ai_workflow_exists(self):
        """docs/AI_WORKFLOW.md must exist."""
        self.assertTrue(
            _AI_WORKFLOW.is_file(),
            f"docs/AI_WORKFLOW.md not found at {_AI_WORKFLOW}",
        )

    def test_ai_workflow_mentions_goal_172(self):
        """docs/AI_WORKFLOW.md must mention Goal 17.2."""
        self.assertIn(
            "17.2", self.text,
            "docs/AI_WORKFLOW.md must mention Goal 17.2",
        )


if __name__ == "__main__":
    unittest.main()
