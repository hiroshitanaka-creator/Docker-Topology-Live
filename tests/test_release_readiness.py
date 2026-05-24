"""Tests for v0.3.0 release readiness artifacts.

Checks that required release-readiness files exist, contain the expected
content, and that the release script does not contain publish or tag commands.

These are static file-content checks; they do not run the build tool,
create tags, or publish releases.
"""
import pathlib
import re
import unittest

_ROOT = pathlib.Path(__file__).parent.parent


class TestReleaseArtifactsExist(unittest.TestCase):
    """All release readiness files must be present."""

    def test_changelog_exists(self):
        """CHANGELOG.md must exist at the repository root."""
        self.assertTrue(
            (_ROOT / "CHANGELOG.md").is_file(),
            "CHANGELOG.md is missing from the repository root",
        )

    def test_release_checklist_exists(self):
        """docs/RELEASE.md must exist."""
        self.assertTrue(
            (_ROOT / "docs" / "RELEASE.md").is_file(),
            "docs/RELEASE.md (release checklist) is missing",
        )

    def test_release_notes_v030_exists(self):
        """docs/releases/v0.3.0.md draft release notes must exist."""
        self.assertTrue(
            (_ROOT / "docs" / "releases" / "v0.3.0.md").is_file(),
            "docs/releases/v0.3.0.md draft release notes are missing",
        )

    def test_release_check_script_exists(self):
        """scripts/release_check.sh must exist."""
        self.assertTrue(
            (_ROOT / "scripts" / "release_check.sh").is_file(),
            "scripts/release_check.sh is missing",
        )


class TestChangelogContent(unittest.TestCase):
    """CHANGELOG.md must cover the expected milestones."""

    @classmethod
    def setUpClass(cls):
        cls.text = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    def test_changelog_has_unreleased_or_v030_section(self):
        """CHANGELOG.md must have an [Unreleased] or v0.3.0 section."""
        has_unreleased = "[Unreleased]" in self.text or "Unreleased" in self.text
        has_v030 = "0.3.0" in self.text
        self.assertTrue(has_unreleased or has_v030,
                        "CHANGELOG.md must contain an [Unreleased] or v0.3.0 section")

    def test_changelog_mentions_packaged_implementation(self):
        self.assertIn("PR #3", self.text,
                      "CHANGELOG.md must mention PR #3 (packaged implementation)")

    def test_changelog_mentions_sse(self):
        self.assertTrue(
            "SSE" in self.text or "Server-Sent Events" in self.text,
            "CHANGELOG.md must mention SSE / Server-Sent Events",
        )

    def test_changelog_mentions_metrics(self):
        self.assertIn("metrics", self.text.lower(),
                      "CHANGELOG.md must mention metrics")

    def test_changelog_mentions_diagnostics(self):
        self.assertIn("diagnostic", self.text.lower(),
                      "CHANGELOG.md must mention diagnostics")

    def test_changelog_mentions_host_path_redaction(self):
        self.assertTrue(
            "redact" in self.text.lower() or "host path" in self.text.lower(),
            "CHANGELOG.md must mention host path redaction",
        )

    def test_changelog_mentions_offline_d3(self):
        self.assertTrue(
            "vendor" in self.text.lower() or "offline" in self.text.lower()
            or "D3" in self.text,
            "CHANGELOG.md must mention the vendored offline D3 asset",
        )

    def test_changelog_mentions_known_limitations(self):
        self.assertTrue(
            "limitation" in self.text.lower() or "Known Limitation" in self.text,
            "CHANGELOG.md must include a Known Limitations section",
        )


class TestReleaseCheckScript(unittest.TestCase):
    """scripts/release_check.sh must be a safe, local-only verification script."""

    @classmethod
    def setUpClass(cls):
        cls.text = (_ROOT / "scripts" / "release_check.sh").read_text(encoding="utf-8")

    def test_script_has_set_euo_pipefail(self):
        """The script must use set -euo pipefail for safety."""
        self.assertIn("set -euo pipefail", self.text,
                      "release_check.sh must use 'set -euo pipefail'")

    def test_script_references_python_m_build(self):
        """The script must invoke python -m build for package verification."""
        self.assertIn("python -m build", self.text,
                      "release_check.sh must reference 'python -m build'")

    def test_script_has_no_twine_upload(self):
        """The script must not upload to PyPI (no twine upload)."""
        self.assertNotIn("twine upload", self.text,
                         "release_check.sh must not contain 'twine upload' — "
                         "this script is local-only and must not publish")

    def test_script_has_no_git_tag_creation(self):
        """The script must not create git tags."""
        # Allow 'tag' in comments/messages but not as a git command
        git_tag_cmds = re.findall(r'\bgit\s+tag\b', self.text)
        self.assertEqual(git_tag_cmds, [],
                         "release_check.sh must not run 'git tag' — "
                         "tag creation requires explicit human approval")

    def test_script_has_no_git_push_tags(self):
        """The script must not push tags."""
        self.assertNotIn("push origin v", self.text,
                         "release_check.sh must not push version tags")

    def test_script_has_no_github_release_creation(self):
        """The script must not create GitHub Releases."""
        self.assertNotIn("gh release create", self.text,
                         "release_check.sh must not create GitHub Releases")

    def test_script_checks_vendor_d3(self):
        """The script must verify that the vendored D3 file is present."""
        self.assertIn("d3.min.js", self.text,
                      "release_check.sh must check for vendored d3.min.js")

    def test_script_checks_d3_license(self):
        """The script must verify that the D3 licence notice is present."""
        self.assertIn("D3_LICENSE.txt", self.text,
                      "release_check.sh must check for D3_LICENSE.txt")

    def test_script_checks_no_cdn(self):
        """The script must verify that index.html has no CDN reference."""
        self.assertIn("cdn.jsdelivr.net", self.text,
                      "release_check.sh must check that no cdn.jsdelivr.net "
                      "reference exists in index.html")

    def test_script_is_executable_or_runnable_with_bash(self):
        """The script must start with a valid shebang."""
        self.assertTrue(
            self.text.startswith("#!/"),
            "release_check.sh must begin with a shebang (#!)",
        )


class TestPyprojectVersion(unittest.TestCase):
    """pyproject.toml must declare version 0.3.0 for the v0.3.0 release cycle."""

    @classmethod
    def setUpClass(cls):
        cls.text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    def test_version_is_030(self):
        """pyproject.toml must declare version = "0.3.0"."""
        self.assertIn('version = "0.3.0"', self.text,
                      "pyproject.toml must set version = \"0.3.0\" for this release")

    def test_package_data_includes_vendor_d3(self):
        """pyproject.toml package-data must include the vendored D3 bundle."""
        self.assertIn("vendor/d3.min.js", self.text,
                      "pyproject.toml package-data must include web/vendor/d3.min.js")

    def test_package_data_includes_d3_license(self):
        """pyproject.toml package-data must include the D3 licence notice."""
        self.assertIn("D3_LICENSE.txt", self.text,
                      "pyproject.toml package-data must include D3_LICENSE.txt")

    def test_package_data_includes_index_html(self):
        """pyproject.toml package-data must include web/index.html."""
        self.assertIn("index.html", self.text,
                      "pyproject.toml package-data must include web/index.html")


class TestNoInnerHTMLRegression(unittest.TestCase):
    """Neither index.html nor app.js may introduce innerHTML assignments."""

    def test_no_innerHTML_in_index_html(self):
        html = (_ROOT / "src/docker_topology_live/web/index.html").read_text(encoding="utf-8")
        self.assertNotIn(
            "innerHTML",
            html,
            "index.html must not use innerHTML — safe DOM only",
        )

    def test_no_innerHTML_assignment_in_app_js(self):
        js = (_ROOT / "src/docker_topology_live/web/assets/app.js").read_text(encoding="utf-8")
        matches = re.findall(r'\.innerHTML\s*=', js)
        self.assertEqual(
            matches, [],
            f"innerHTML assignment(s) found in app.js: {matches}",
        )


if __name__ == "__main__":
    unittest.main()
