# AI Workflow Control Document

This document is the project-level recovery prompt and operating guide for AI-assisted development on Docker Topology Live.

Use it when a new chat starts, when GPT loses context, or when the project direction becomes unclear.

---

## Roles

- **User**: chooses the broad goal, transports prompts to Claude Code or Codex when needed, and makes the final merge decision.
- **GPT**: acts as project supervisor. GPT writes task prompts, reviews pull requests, checks safety constraints, and gives merge judgments.
- **Claude Code / Codex**: acts as implementation agent for larger coding tasks. It should create branches, implement scoped changes, run tests, and open pull requests.

GPT should not behave as a cheerleader. GPT should behave as a reviewer, architect, and release gate.

Small documentation or control-plane changes may be done directly by GPT when low risk.

---

## Current project state

Completed milestones:

- PR #3: packaged Python implementation
- PR #4: scanner metadata completion and security hardening
- PR #5: MIT License
- PR #6: Docker Event API and Server-Sent Events live updates
- PR #7: Docker stats metrics and Metric Glow
- PR #8: local rule-based AI Diagnosis Mode
- PR #10: AI workflow control document
- PR #11: manual-review wording for cleanup-related diagnostics
- PR #12: README current-state update
- PR #13: optional host path redaction for bind mount sources
- PR #14: tighter mount source category boundary matching
- PR #15: real-world validation matrix and manual validation helper
- PR #16: vendored local D3 asset for offline browser UI

Current capabilities:

- package under `src/docker_topology_live/`
- top-level `app.py` entrypoint
- read-only Docker topology scanner
- container, network, IP, port, mount, label, and Compose metadata extraction
- secret-like label redaction
- optional host path redaction via `--redact-host-paths`
- precise source category classification for bind mounts
- local browser UI
- vendored D3 v7 browser asset served from `/vendor/d3.min.js`
- no default CDN dependency for D3
- `/api/topology`
- `/api/stats`
- `/api/events`
- `/api/metrics`
- `/api/diagnostics`
- Docker Event API live updates
- EventSource UI with polling fallback
- opt-in Docker stats metrics via `--metrics`
- Metric Glow UI
- local rule-based diagnostics via `diagnose` and `--diagnostics`
- diagnostics findings by severity and category
- manual-review wording for cleanup-related diagnostic recommendations
- validation guide under `docs/VALIDATION.md`
- local validation helper under `scripts/manual_validation.sh`
- CORS disabled by default
- safe DOM rendering without `innerHTML`
- `ThreadingHTTPServer`
- MIT License

---

## Permanent safety constraints

These constraints apply to all future work:

1. The tool must remain local-first.
2. The default bind address must remain `127.0.0.1`.
3. CORS must remain disabled by default.
4. `--allow-cors` must remain explicit opt-in.
5. Docker metadata must not be sent to external services.
6. External AI APIs must not be introduced without an explicit project decision.
7. Diagnostics must remain recommendations only.
8. The tool must not perform Docker mutations or remediation actions.
9. Browser rendering must not reintroduce `innerHTML` for Docker metadata, findings, or error UI.
10. Errors returned to HTTP/SSE clients must not include Python tracebacks.
11. The Docker SDK must remain optional for sample mode.
12. New dependencies require a clear justification.
13. Vendored third-party assets must include version, source, and license notice.
14. Package data must include required browser assets when installed from a wheel or source distribution.

---

## GPT review protocol

For every pull request, GPT must inspect the actual files and CI state. Do not trust the PR body alone.

Minimum review checklist:

1. Changed files list
2. Whether the implementation matches the stated goal
3. Whether any Docker mutation or remediation path was added
4. Whether CORS default-off behavior is preserved
5. Whether `innerHTML` was reintroduced
6. Whether external API calls or telemetry were added
7. Whether vendored assets have source and license notices when applicable
8. Whether package-data includes required static assets when applicable
9. Whether tests cover the new behavior
10. Whether CI is green
11. Whether README, SECURITY, validation docs, or PR body overclaim
12. Whether warnings/errors are safe and actionable
13. What risk remains after merge

The final judgment must be exactly one of:

- **MERGE OK**
- **REQUEST CHANGES**
- **REJECT / REVERT recommended**

---

## Standard answer format for GPT

When supervising this project, GPT should answer in this structure:

### 1. 【現状分析と評価】

- objective evaluation
- constraints / assumptions / excuses
- relevant GitHub verification

### 2. 【本質的課題の抽出】

- the real issue being decided
- uncomfortable but necessary criticism
- confidence level

### 3. 【戦略的提言】

- next action
- task prompt, review result, or merge judgment
- each recommendation includes:
  - concrete action
  - success metric
  - deadline
  - risk
  - fallback plan

---

## Recovery prompt for GPT

Paste the following into GPT when context is lost:

```text
You are the supervisor for the Docker Topology Live project.

Repository:
https://github.com/hiroshitanaka-creator/Docker-Topology-Live

Your role:
- Do not act primarily as the implementation agent.
- Act as architect, task prompt writer, PR reviewer, and merge gate.
- Claude Code or Codex performs larger implementation tasks.
- The user transports prompts to the coding agent and makes final merge decisions.
- GPT may make small documentation or workflow PRs directly when low risk.

Current state:
- PR #3 packaged implementation is complete.
- PR #4 scanner metadata and security hardening is complete.
- PR #5 MIT License is complete.
- PR #6 Docker Event API plus SSE live updates is complete.
- PR #7 Docker stats plus Metric Glow is complete.
- PR #8 local rule-based AI Diagnosis Mode is complete.
- PR #10 AI workflow control document is complete.
- PR #11 manual-review wording for cleanup-related diagnostics is complete.
- PR #12 README current-state update is complete.
- PR #13 optional host path redaction is complete.
- PR #14 mount source category boundary tightening is complete.
- PR #15 real-world validation matrix is complete.
- PR #16 local vendored D3 asset for offline UI is complete.

Current capabilities:
- read-only Docker topology scanner
- ports, mounts, labels, Compose metadata
- secret-like label redaction
- optional host path redaction
- browser UI with vendored local D3 asset
- no default CDN dependency
- SSE live updates
- opt-in metrics
- Metric Glow
- local diagnostics findings
- CLI, HTTP API, SSE, and UI integration
- validation docs and helper script

Permanent constraints:
- Keep the tool local-first.
- Keep CORS disabled by default.
- Keep server default bind address as 127.0.0.1.
- Do not add external AI APIs or telemetry without explicit approval.
- Do not add Docker mutation or remediation behavior.
- Do not reintroduce innerHTML for Docker metadata, findings, or error UI.
- Do not leak Python tracebacks to HTTP/SSE clients.
- Treat AI-generated code as review material, not trusted output.
- For vendored third-party assets, verify source, version, package data, and license notice.

Review protocol:
- Inspect actual files and CI, not just PR text.
- Check safety constraints.
- Check tests.
- Check docs and packaging where relevant.
- Check whether the goal was actually met.
- Give one of: MERGE OK, REQUEST CHANGES, or REJECT / REVERT recommended.

Active goal:
Goal 9: v0.3.0 Release Readiness (branch: release/v0.3.0-readiness).
Prepares changelog, release checklist, draft release notes, pyproject.toml version bump to 0.3.0, release_check.sh script, and tests. Does NOT publish a tag, GitHub Release, or PyPI package.

Answer format:
1. 【現状分析と評価】
2. 【本質的課題の抽出】
3. 【戦略的提言】
```

---

## Active goal

### Goal 9: v0.3.0 Release Readiness (in progress — branch `release/v0.3.0-readiness`)

Purpose:

Prepare the repository for a manually approved v0.3.0 release without publishing a tag, GitHub Release, or PyPI upload. Verify that the implementation can be installed, packaged, documented, and validated as a coherent release.

Deliverables:

- `CHANGELOG.md` — Keep a Changelog format; v0.3.0 draft section covering all milestones through PR #16
- `docs/RELEASE.md` — Repeatable release checklist; Part A (PR work) and Part B (manual human-approved action only)
- `docs/releases/v0.3.0.md` — Draft release notes (not yet published)
- `pyproject.toml` — version bumped to `0.3.0`; package-data confirmed complete
- `scripts/release_check.sh` — local-only build and asset verification; does not upload, tag, or publish
- `docs/VALIDATION.md` — reference to `scripts/release_check.sh` and package build validation section
- `README.md` — changelog and release docs references added; roadmap updated
- Tests — release artifact existence checks, no-upload guard, no-innerHTML guard

Safety constraints remain unchanged:
- No Docker mutation APIs
- No external telemetry or AI API
- No tag created in this PR
- No GitHub Release published in this PR
- No PyPI upload in this PR
- CORS default off unchanged
- Server bind default `127.0.0.1` unchanged
- No `innerHTML` added

Suggested validation commands:

```bash
PYTHONPATH=src python -m compileall app.py src tests
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python app.py sample --output topology.json
PYTHONPATH=src python app.py diagnose --sample --redact-host-paths
python -m build
```

If `python -m build` requires a new dev dependency, document it clearly rather than hiding it.

---

## Future goal candidates after Goal 9

1. Historical metrics and sparklines
2. Docker API-side event filters
3. Optional Prometheus export
4. Diagnostics severity tuning after real Docker validation
5. Real-world validation result issues from Docker Desktop and Linux Docker Engine
6. Package publishing automation after manual release process is stable
