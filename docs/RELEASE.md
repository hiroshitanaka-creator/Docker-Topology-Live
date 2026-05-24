# Release Checklist

This document describes the release process for Docker Topology Live. It is split into two parts: (A) release readiness work that lives in a PR, and (B) the manual release action that must be approved before a tag and publish happen.

> **Important**: Part B must never be executed automatically, by CI, or without human approval. No tag, GitHub Release, or PyPI upload should be created until Part A is verified complete and a human explicitly approves the release.

---

## Part A — Release Readiness (in PR)

### 1. Tests and compilation

- [ ] `PYTHONPATH=src python -m compileall app.py src tests` — exits zero
- [ ] `PYTHONPATH=src python -m unittest discover -s tests -v` — all tests pass
- [ ] No new test failures introduced by release-prep changes

### 2. CLI smoke tests

- [ ] `PYTHONPATH=src python app.py sample --output topology.json` — exits zero, produces valid JSON
- [ ] `PYTHONPATH=src python app.py diagnose --sample` — exits zero, produces valid JSON
- [ ] `PYTHONPATH=src python app.py sample --redact-host-paths --output topology.redacted.json` — exits zero, `sourceRedacted: true` present
- [ ] `PYTHONPATH=src python app.py diagnose --sample --redact-host-paths` — exits zero, findings present

### 3. Package build

- [ ] `pip install --upgrade build` — build tool available
- [ ] `python -m build` — exits zero, produces `dist/*.whl` and `dist/*.tar.gz`
- [ ] `unzip -l dist/*.whl | grep vendor` — confirms `d3.min.js` and `D3_LICENSE.txt` are in the wheel
- [ ] `unzip -l dist/*.whl | grep index.html` — confirms `index.html` is in the wheel
- [ ] `tar -tzf dist/*.tar.gz | grep LICENSE` — confirms `LICENSE` is in the sdist
- [ ] Wheel size is reasonable (not missing assets, not inflated with test artifacts)

### 4. Asset integrity

- [ ] `grep -c "vendor/d3.min.js" src/docker_topology_live/web/index.html` — returns 1
- [ ] `grep "cdn.jsdelivr.net" src/docker_topology_live/web/index.html` — returns no output (no CDN)
- [ ] `cat src/docker_topology_live/web/vendor/D3_LICENSE.txt` — ISC licence, Mike Bostock, version present
- [ ] No `innerHTML` in authored UI files (vendored `d3.min.js` is excluded from this check):
  ```
  grep -n "innerHTML" src/docker_topology_live/web/index.html
  grep -nE '\.innerHTML[[:space:]]*=' src/docker_topology_live/web/assets/app.js
  ```
  Both commands must return no output.

### 5. Documentation review

- [ ] `README.md` accurately reflects completed features
- [ ] `SECURITY.md` accurately reflects all security controls
- [ ] `docs/VALIDATION.md` includes offline D3 and redaction checks
- [ ] `CHANGELOG.md` includes the v0.3.0 draft section
- [ ] `docs/releases/v0.3.0.md` draft notes are present
- [ ] Version in `pyproject.toml` matches intended release version

### 6. Manual validation

- [ ] `bash scripts/release_check.sh` — exits zero (or failure is documented and understood)
- [ ] `bash scripts/manual_validation.sh` — local compile, test, sample export, and CLI checks pass
- [ ] Manual browser validation:
  ```
  python app.py serve --sample --metrics --diagnostics --redact-host-paths
  ```
  Open `http://127.0.0.1:8080` and confirm:
  - Browser UI loads without console errors
  - DevTools → Network tab shows no `cdn.jsdelivr.net` request
  - `/vendor/d3.min.js` loads with HTTP 200 and `application/javascript` content type
  - Topology graph renders; node detail panel opens on click

---

## Part B — Manual Release Action (human approval required)

> **Do not execute Part B in a PR or CI job. Execute only after Part A is verified and a human approves the release explicitly.**

### 7. Pre-release final checks

- [ ] All Part A checks confirmed green
- [ ] Release notes in `docs/releases/v0.3.0.md` reviewed and approved
- [ ] CHANGELOG.md `[Unreleased]` section reviewed and accurate
- [ ] No known blocking issues

### 8. Tag and release (manual, after approval)

- [ ] `git tag -a v0.3.0 -m "Release v0.3.0"` — create annotated tag locally
- [ ] `git push origin v0.3.0` — push tag to GitHub
- [ ] Create GitHub Release from tag, copy release notes from `docs/releases/v0.3.0.md`
- [ ] Upload wheel and sdist from `dist/` as release assets (optional)
- [ ] If publishing to PyPI: `python -m twine upload dist/*` (optional, future decision)

### 9. Post-release

- [ ] Update `CHANGELOG.md`: rename `[Unreleased]` to `[0.3.0] — YYYY-MM-DD`
- [ ] Update `docs/AI_WORKFLOW.md` to reflect release status
- [ ] Open next milestone planning issue
