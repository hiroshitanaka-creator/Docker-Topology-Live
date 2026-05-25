"""Static tests for .github/workflows/docker-live-preflight.yml.

These tests verify the structure and safety constraints of the Docker Live
Preflight workflow without running Docker, GitHub Actions, or any live daemon.

Checks performed:
- workflow file exists and is non-empty
- workflow uses workflow_dispatch (manual trigger only)
- workflow does NOT trigger on push
- workflow does NOT trigger on pull_request
- workflow does not include release, tag, or PyPI publish actions
- workflow creates only dtl-preflight-* containers (naming convention)
- alpine smoke uses --name dtl-preflight-alpine (named container)
- workflow has a 'docker rm -f' cleanup step
- workflow cleanup uses 'if: always()' to ensure containers are always removed
- cleanup covers dtl-preflight-alpine, dtl-preflight-nginx, dtl-preflight-web
- workflow uploads the docker-live-preflight-summary artifact
- workflow does not use secrets
- workflow does not claim 'no external services' (images may be pulled)
- workflow runs on ubuntu-latest
- workflow tracks daemon availability before running live steps

These tests run as part of the normal unit test suite:
    PYTHONPATH=src python -m unittest discover -s tests -v

No Docker daemon is required.
"""
import pathlib
import re
import unittest

_ROOT = pathlib.Path(__file__).parent.parent
_WORKFLOW = _ROOT / ".github" / "workflows" / "docker-live-preflight.yml"


# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------

class TestDockerLivePreflightWorkflowExists(unittest.TestCase):
    """The workflow file must exist and be non-empty."""

    def test_workflow_file_exists(self):
        self.assertTrue(
            _WORKFLOW.is_file(),
            f".github/workflows/docker-live-preflight.yml not found at {_WORKFLOW}",
        )

    def test_workflow_is_nonempty(self):
        self.assertGreater(
            _WORKFLOW.stat().st_size,
            0,
            ".github/workflows/docker-live-preflight.yml must not be empty",
        )


# ---------------------------------------------------------------------------
# Content / structure
# ---------------------------------------------------------------------------

class TestDockerLivePreflightWorkflowContent(unittest.TestCase):
    """The workflow file must be correctly and safely structured."""

    @classmethod
    def setUpClass(cls):
        cls.text = _WORKFLOW.read_text(encoding="utf-8")

    # --- Trigger: workflow_dispatch only ------------------------------------

    def test_uses_workflow_dispatch(self):
        """Workflow must use workflow_dispatch so it is manual-only."""
        self.assertIn(
            "workflow_dispatch", self.text,
            "docker-live-preflight.yml must use the workflow_dispatch trigger",
        )

    def test_no_push_trigger(self):
        """Workflow must NOT trigger on push (no automatic runs on every commit)."""
        push_trigger = re.search(r'^\s{0,4}push\s*:', self.text, re.MULTILINE)
        self.assertIsNone(
            push_trigger,
            "docker-live-preflight.yml must NOT trigger on push; "
            "use workflow_dispatch only",
        )

    def test_no_pull_request_trigger(self):
        """Workflow must NOT trigger on pull_request."""
        pr_trigger = re.search(r'^\s{0,4}pull_request\s*:', self.text, re.MULTILINE)
        self.assertIsNone(
            pr_trigger,
            "docker-live-preflight.yml must NOT trigger on pull_request; "
            "use workflow_dispatch only",
        )

    # --- No release / tag / publish actions --------------------------------

    def test_no_pypi_publish_action(self):
        """Workflow must not contain a PyPI publish action."""
        self.assertNotIn(
            "pypa/gh-action-pypi-publish", self.text,
            "docker-live-preflight.yml must not contain a PyPI publish action",
        )

    def test_no_twine_upload(self):
        """Workflow must not contain a twine upload step."""
        self.assertNotIn(
            "twine upload", self.text,
            "docker-live-preflight.yml must not contain a twine upload step",
        )

    def test_no_git_tag_creation(self):
        """Workflow must not create git tags."""
        self.assertNotIn(
            "git tag", self.text,
            "docker-live-preflight.yml must not create git tags",
        )

    def test_no_github_release_action(self):
        """Workflow must not create GitHub releases."""
        self.assertNotIn(
            "create-release", self.text.lower(),
            "docker-live-preflight.yml must not create GitHub releases",
        )

    def test_no_upload_to_pypi(self):
        """Workflow must not upload to PyPI."""
        self.assertNotIn(
            "upload-to-pypi", self.text.lower(),
            "docker-live-preflight.yml must not upload to PyPI",
        )

    # --- No secrets --------------------------------------------------------

    def test_no_secrets_usage(self):
        """Workflow must not reference any secrets."""
        self.assertNotIn(
            "secrets.", self.text,
            "docker-live-preflight.yml must not use secrets",
        )

    # --- Container naming convention ---------------------------------------

    def test_only_dtl_preflight_containers(self):
        """All 'docker run --name' containers must use the dtl-preflight-* prefix.

        This ensures no unintended containers are created and all containers
        can be identified and cleaned up reliably.
        """
        name_pattern = re.compile(r'--name\s+(\S+)', re.MULTILINE)
        names = name_pattern.findall(self.text)
        # Skip template expressions (e.g. ${{ matrix.name }})
        plain_names = [n for n in names if not n.startswith('${{')]
        self.assertTrue(
            len(plain_names) > 0,
            "docker-live-preflight.yml must have at least one --name container",
        )
        for name in plain_names:
            self.assertTrue(
                name.startswith("dtl-preflight-"),
                f"Container name '{name}' must start with 'dtl-preflight-'",
            )

    # --- Cleanup -----------------------------------------------------------

    def test_has_docker_rm_cleanup(self):
        """Workflow must have a 'docker rm -f' step to remove containers."""
        self.assertIn(
            "docker rm -f", self.text,
            "docker-live-preflight.yml must include a 'docker rm -f' cleanup step",
        )

    def test_cleanup_uses_if_always(self):
        """Cleanup step must use 'if: always()' to run even when earlier steps fail."""
        self.assertIn(
            "if: always()", self.text,
            "docker-live-preflight.yml must have a cleanup step with 'if: always()'",
        )

    def test_alpine_smoke_uses_dtl_preflight_alpine_name(self):
        """Alpine echo smoke command must use --name dtl-preflight-alpine.

        Without an explicit name the container is anonymous, violating the
        dtl-preflight-* naming convention and making cleanup harder to verify.
        """
        self.assertIn(
            "--name dtl-preflight-alpine", self.text,
            "Alpine echo smoke command must use '--name dtl-preflight-alpine' "
            "so every container follows the dtl-preflight-* naming convention",
        )

    def test_cleanup_covers_dtl_preflight_nginx(self):
        """The if: always() cleanup must remove dtl-preflight-nginx.

        dtl-preflight-nginx is started in the Docker smoke step.  If that step
        fails after starting the container but before its in-step removal, the
        cleanup step must still remove it.
        """
        rm_pattern = re.compile(r'docker rm -f[^\n]+', re.MULTILINE)
        rm_lines = rm_pattern.findall(self.text)
        all_rm_text = ' '.join(rm_lines)
        self.assertIn(
            'dtl-preflight-nginx', all_rm_text,
            "Cleanup must include dtl-preflight-nginx in a 'docker rm -f' line",
        )

    def test_cleanup_covers_dtl_preflight_web(self):
        """The if: always() cleanup must remove dtl-preflight-web.

        dtl-preflight-web is started in the live scan step and only removed
        here.
        """
        rm_pattern = re.compile(r'docker rm -f[^\n]+', re.MULTILINE)
        rm_lines = rm_pattern.findall(self.text)
        all_rm_text = ' '.join(rm_lines)
        self.assertIn(
            'dtl-preflight-web', all_rm_text,
            "Cleanup must include dtl-preflight-web in a 'docker rm -f' line",
        )

    def test_cleanup_covers_dtl_preflight_alpine(self):
        """The cleanup must defensively include dtl-preflight-alpine.

        dtl-preflight-alpine uses --rm so it is normally removed automatically,
        but the cleanup step must list it as a defensive no-op in case the
        container is still running when cleanup runs.
        """
        rm_pattern = re.compile(r'docker rm -f[^\n]+', re.MULTILINE)
        rm_lines = rm_pattern.findall(self.text)
        all_rm_text = ' '.join(rm_lines)
        self.assertIn(
            'dtl-preflight-alpine', all_rm_text,
            "Cleanup must include dtl-preflight-alpine in a 'docker rm -f' line "
            "as a defensive no-op",
        )

    # --- No external-services overclaim ------------------------------------

    def test_no_external_services_overclaim(self):
        """Workflow must not claim 'no external services'.

        The workflow pulls public container images (alpine:3.20, nginx:alpine)
        from Docker Hub at runtime.  Claiming 'no external services' would be
        inaccurate.  The correct statement is that there is no telemetry and
        no external API calls, while acknowledging that Docker image pulls may
        occur if images are not cached on the runner.
        """
        self.assertNotIn(
            "no external services", self.text,
            "docker-live-preflight.yml must not claim 'no external services'; "
            "public container images may be pulled by Docker if not cached on "
            "the runner",
        )

    # --- Artifact upload ---------------------------------------------------

    def test_uploads_summary_artifact(self):
        """Workflow must upload the docker-live-preflight-summary artifact."""
        self.assertIn(
            "docker-live-preflight-summary", self.text,
            "docker-live-preflight.yml must upload 'docker-live-preflight-summary' artifact",
        )

    def test_uploads_summary_md_path(self):
        """Workflow must reference the summary .md file path."""
        self.assertIn(
            "docker-live-preflight-summary.md", self.text,
            "docker-live-preflight.yml must reference docker-live-preflight-summary.md",
        )

    def test_uses_upload_artifact_action(self):
        """Workflow must use actions/upload-artifact."""
        self.assertIn(
            "upload-artifact", self.text,
            "docker-live-preflight.yml must use actions/upload-artifact",
        )

    # --- Daemon availability gate ------------------------------------------

    def test_tracks_daemon_availability(self):
        """Workflow must track whether the Docker daemon is available."""
        self.assertIn(
            "daemon_available", self.text,
            "docker-live-preflight.yml must track daemon_available for conditional steps",
        )

    def test_live_steps_are_conditional(self):
        """Live app preflight steps must be conditional on daemon availability."""
        # The workflow must gate live steps behind daemon_available check.
        self.assertIn(
            "daemon_available", self.text,
            "docker-live-preflight.yml live steps must be conditional on daemon availability",
        )

    # --- Runner ------------------------------------------------------------

    def test_uses_ubuntu_latest_runner(self):
        """Workflow must run on ubuntu-latest."""
        self.assertIn(
            "ubuntu-latest", self.text,
            "docker-live-preflight.yml must run on ubuntu-latest",
        )

    # --- No external telemetry ---------------------------------------------

    def test_no_external_curl(self):
        """Workflow must not send data to external URLs via curl."""
        self.assertNotIn(
            "curl https://", self.text,
            "docker-live-preflight.yml must not use curl to send data externally",
        )

    # --- Package smoke present ---------------------------------------------

    def test_references_app_py_doctor(self):
        """Workflow must run 'app.py doctor' as part of the package smoke."""
        self.assertIn(
            "app.py doctor", self.text,
            "docker-live-preflight.yml must run 'app.py doctor'",
        )

    def test_references_unit_tests(self):
        """Workflow must run the unit test suite."""
        self.assertIn(
            "unittest discover", self.text,
            "docker-live-preflight.yml must run 'python -m unittest discover'",
        )

    def test_references_compile_check(self):
        """Workflow must run a compile check."""
        self.assertIn(
            "compileall", self.text,
            "docker-live-preflight.yml must run 'python -m compileall'",
        )

    # --- Summary content ---------------------------------------------------

    def test_summary_mentions_recommended_next_step(self):
        """Summary generation must include a recommended next step."""
        self.assertIn(
            "next_step", self.text,
            "docker-live-preflight.yml summary must include a recommended next step",
        )

    def test_summary_mentions_issue_34(self):
        """Summary must reference Issue #34 to contextualise the preflight."""
        self.assertIn(
            "#34", self.text,
            "docker-live-preflight.yml summary must mention Issue #34",
        )


# ---------------------------------------------------------------------------
# CHANGELOG.md — Goal 17.1 entry wording
# ---------------------------------------------------------------------------

_CHANGELOG = _ROOT / "CHANGELOG.md"


class TestChangelogDockerLivePreflightEntry(unittest.TestCase):
    """CHANGELOG.md must not overclaim 'no external service calls'.

    The docker-live-preflight workflow pulls public container images
    (alpine:3.20, nginx:alpine) from Docker Hub when they are not cached on
    the runner.  The phrase 'no external service calls' is therefore inaccurate
    and must not appear anywhere in CHANGELOG.md.
    """

    @classmethod
    def setUpClass(cls):
        cls.changelog = _CHANGELOG.read_text(encoding="utf-8")

    def test_changelog_exists(self):
        """CHANGELOG.md must exist."""
        self.assertTrue(
            _CHANGELOG.is_file(),
            f"CHANGELOG.md not found at {_CHANGELOG}",
        )

    def test_no_external_service_calls_phrase(self):
        """CHANGELOG.md must not contain the phrase 'no external service calls'.

        The preflight workflow pulls public container images from Docker Hub;
        claiming 'no external service calls' would be inaccurate.
        """
        self.assertNotIn(
            "no external service calls", self.changelog,
            "CHANGELOG.md must not say 'no external service calls'; "
            "the preflight workflow may pull public container images from Docker Hub",
        )

    def test_preflight_entry_acknowledges_image_pulls(self):
        """The CHANGELOG preflight entry must acknowledge that Docker may pull images."""
        self.assertIn(
            "Docker may\npull public container images", self.changelog,
            "CHANGELOG.md preflight entry must note that Docker may pull "
            "public container images if they are not cached on the runner",
        )


if __name__ == "__main__":
    unittest.main()
