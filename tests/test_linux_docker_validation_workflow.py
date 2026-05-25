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
- cleanup removes dtl-validate-* containers (including dtl-validate-bind)
- cleanup removes dtl-validate-* networks
- cleanup removes RUNNER_TEMP/dtl-validate-host-path directory
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
- CORS default check is present and exits 1 on unexpected header (--allow-cors not used)
- Prometheus is opt-in (--prometheus present for this validation workflow)
- topology validation uses real schema: kind+label fields (not name or top-level networks key)
- dtl-validate-bind container is created with a real bind mount from RUNNER_TEMP
- redaction is genuinely exercised (not skipped); sourceRedacted field is checked
- CORS check exits 1 when Access-Control-Allow-Origin header is unexpectedly present

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

    def test_api_topology_fails_if_no_dtl_validate_containers(self):
        """The /api/topology validation must fail if no dtl-validate-* container nodes are returned.

        Computing dtl_nodes but only printing the count is not sufficient —
        the check must append a failure issue when dtl_nodes is empty.
        """
        self.assertIn(
            "api/topology: no dtl-validate-* container nodes returned", self.text,
            "linux-docker-validation.yml /api/topology validation must append a failure "
            "when no dtl-validate-* container nodes are returned by the live server",
        )

    def test_api_topology_fails_if_no_network_nodes(self):
        """The /api/topology validation must fail if no network nodes are returned."""
        self.assertIn(
            "api/topology: no network nodes returned", self.text,
            "linux-docker-validation.yml /api/topology validation must append a failure "
            "when no network nodes (kind='network') are returned by the live server",
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

    # --- Real topology schema: kind + label (Blocker 1) --------------------

    def test_topology_uses_kind_container(self):
        """Topology validation must use kind=='container' to identify container nodes.

        The real topology schema uses node['kind'] == 'container', not a 'name' field.
        """
        self.assertIn(
            '"container"', self.text,
            "linux-docker-validation.yml must filter container nodes by kind=='container'",
        )
        # Specifically check the kind-based filtering pattern
        has_kind_container = (
            "kind\") == \"container\"" in self.text
            or "kind') == 'container'" in self.text
            or "\"kind\") == \"container\"" in self.text
            or "'kind') == 'container'" in self.text
            or "get(\"kind\") == \"container\"" in self.text
            or "get('kind') == 'container'" in self.text
        )
        self.assertTrue(
            has_kind_container,
            "linux-docker-validation.yml must use n.get('kind') == 'container' "
            "to filter container nodes from topology output",
        )

    def test_topology_uses_kind_network(self):
        """Topology validation must use kind=='network' to identify network nodes.

        The real topology schema uses node['kind'] == 'network', not a top-level
        'networks' key.
        """
        has_kind_network = (
            "kind\") == \"network\"" in self.text
            or "kind') == 'network'" in self.text
            or "\"kind\") == \"network\"" in self.text
            or "'kind') == 'network'" in self.text
            or "get(\"kind\") == \"network\"" in self.text
            or "get('kind') == 'network'" in self.text
        )
        self.assertTrue(
            has_kind_network,
            "linux-docker-validation.yml must use n.get('kind') == 'network' "
            "to identify network nodes (networks are nodes in the real schema, "
            "not a separate top-level key)",
        )

    def test_topology_uses_label_field(self):
        """Topology validation must use node['label'] (not node['name']) for container identity.

        The real topology schema exposes container names via node['label'].
        """
        has_label = (
            "\"label\"" in self.text
            or "'label'" in self.text
            or "get(\"label\"" in self.text
            or "get('label'" in self.text
        )
        self.assertTrue(
            has_label,
            "linux-docker-validation.yml must use node['label'] (not node['name']) "
            "for container identity in topology validation",
        )

    def test_topology_does_not_use_top_level_networks_key(self):
        """Topology validation must NOT use data.get('networks') as a top-level key.

        In the real topology schema, networks are represented as nodes with kind='network',
        not as a separate top-level 'networks' key.
        """
        self.assertNotIn(
            "data.get(\"networks\"", self.text,
            "linux-docker-validation.yml must not use data.get('networks') as a top-level "
            "topology key; use n.get('kind') == 'network' to find network nodes instead",
        )
        self.assertNotIn(
            "data.get('networks'", self.text,
            "linux-docker-validation.yml must not use data.get('networks') as a top-level "
            "topology key; use n.get('kind') == 'network' to find network nodes instead",
        )

    # --- Real bind-mount redaction (Blocker 2) ------------------------------

    def test_creates_dtl_validate_bind_container(self):
        """Workflow must create dtl-validate-bind container for real redaction testing."""
        self.assertIn(
            "dtl-validate-bind", self.text,
            "linux-docker-validation.yml must create a 'dtl-validate-bind' container "
            "to exercise bind-mount host path redaction with a real RUNNER_TEMP path",
        )

    def test_uses_bind_mount_with_runner_temp(self):
        """Workflow must create a bind mount from RUNNER_TEMP/dtl-validate-host-path.

        This ensures the redaction check is exercised with a real host path, not skipped.
        """
        has_bind_mount = (
            "RUNNER_TEMP/dtl-validate-host-path" in self.text
            or "$RUNNER_TEMP/dtl-validate-host-path" in self.text
        )
        self.assertTrue(
            has_bind_mount,
            "linux-docker-validation.yml must create a bind mount from "
            "'$RUNNER_TEMP/dtl-validate-host-path' to exercise real host path redaction",
        )

    def test_uses_mount_type_bind(self):
        """Workflow must use --mount type=bind for the bind-mount redaction container."""
        self.assertIn(
            "type=bind", self.text,
            "linux-docker-validation.yml must use '--mount type=bind' for the "
            "dtl-validate-bind container",
        )

    def test_redaction_checks_source_redacted_field(self):
        """Workflow redaction check must verify the sourceRedacted field is set.

        Simply checking that the raw path is absent is not sufficient — we also need
        to confirm sourceRedacted=true appears in the redacted output.
        """
        self.assertIn(
            "sourceRedacted", self.text,
            "linux-docker-validation.yml must check for 'sourceRedacted' in "
            "the redacted scan output to confirm --redact-host-paths worked",
        )

    def test_redaction_check_is_not_skippable(self):
        """Workflow must not allow 'redaction check skipped' as a passing outcome.

        With dtl-validate-bind providing a real bind mount, the redaction check
        must always be exercised and cannot be skipped.
        """
        self.assertNotIn(
            "redaction check skipped (no bind-mount", self.text,
            "linux-docker-validation.yml must not skip the redaction check; "
            "dtl-validate-bind provides a real bind mount to test redaction",
        )

    def test_cleanup_removes_dtl_validate_bind(self):
        """Cleanup must explicitly remove dtl-validate-bind.

        The cleanup uses a multi-line 'docker rm -f' with backslash continuations,
        so the container name appears on a continuation line rather than the first line.
        Search for dtl-validate-bind within 600 chars of any 'docker rm -f' occurrence.
        """
        found = False
        idx = 0
        while True:
            idx = self.text.find("docker rm -f", idx)
            if idx == -1:
                break
            window = self.text[idx: idx + 600]
            if "dtl-validate-bind" in window:
                found = True
                break
            idx += 1
        self.assertTrue(
            found,
            "Cleanup must include 'dtl-validate-bind' within a 'docker rm -f' block; "
            "check that the cleanup step lists it in the multi-line docker rm -f command",
        )

    def test_cleanup_removes_runner_temp_host_path(self):
        """Cleanup must remove the RUNNER_TEMP/dtl-validate-host-path directory."""
        has_rm = (
            "rm -rf" in self.text
            and "dtl-validate-host-path" in self.text
        )
        self.assertTrue(
            has_rm,
            "linux-docker-validation.yml cleanup must remove "
            "'$RUNNER_TEMP/dtl-validate-host-path' using rm -rf",
        )

    # --- CORS check exits 1 (Blocker 3) ------------------------------------

    def test_cors_check_fails_on_unexpected_header(self):
        """CORS check must exit 1 when Access-Control-Allow-Origin header is unexpectedly present.

        Logging a warning is not sufficient — the check must fail the workflow
        if CORS default-off regresses.
        """
        self.assertIn(
            "FAIL: unexpected CORS header", self.text,
            "linux-docker-validation.yml CORS check must emit 'FAIL: unexpected CORS header' "
            "and exit non-zero if Access-Control-Allow-Origin appears without --allow-cors",
        )

    def test_cors_check_has_exit_1(self):
        """CORS check must call exit 1 when unexpected CORS header is found.

        The 'exit 1' must appear in the if-block that handles the unexpected header,
        immediately after the CORS failure message.
        """
        # Find "FAIL: unexpected CORS header" then look for exit 1 nearby
        cors_fail_idx = self.text.find("FAIL: unexpected CORS header")
        self.assertNotEqual(
            cors_fail_idx, -1,
            "CORS failure message 'FAIL: unexpected CORS header' not found in workflow",
        )
        # exit 1 should appear within 200 chars after the failure message
        window = self.text[cors_fail_idx: cors_fail_idx + 200]
        self.assertIn(
            "exit 1", window,
            "The CORS check if-block must call 'exit 1' after emitting "
            "'FAIL: unexpected CORS header'; 'exit 1' was not found within "
            "200 characters of that message",
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
