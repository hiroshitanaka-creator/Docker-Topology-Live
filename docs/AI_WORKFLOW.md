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

Current release:

- **v0.3.0** — published on GitHub Releases, 2026-05-25

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
- PR #17: AI workflow update after offline D3
- PR #18: v0.3.0 release readiness
- PR #19: Release Readiness GitHub Actions workflow
- PR #20: post-v0.3.0 release bookkeeping
- PR #21: Docker API-side event filters with Python-side defense-in-depth
- PR #22: AI workflow update after event filters
- PR #23: browser-local metric history and SVG sparklines
- PR #24: auto-refresh selected-node metric sparklines
- PR #25: AI workflow update after browser-local metric sparklines
- PR #26: optional Prometheus text exposition endpoint
- PR #27: post-Prometheus AI workflow and security policy sync
- PR #28: prepare docs for diagnostics severity tuning goal
- PR #29: diagnostics severity tuning wording improvements and rationale docs
- PR #30: AI workflow update after diagnostics tuning
- PR #31: real-world validation issue workflow and GitHub issue templates
- PR #37: disposable Postgres demo command fix from Codex review

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
- Docker API-side event filters for container/network lifecycle and membership events
- Python-side `is_relevant_event()` retained as defense-in-depth
- safe fallback to unfiltered Docker event stream when API-side filters are unsupported
- EventSource UI with polling fallback
- opt-in Docker stats metrics via `--metrics`
- Metric Glow UI
- browser-local metric history with rolling in-memory samples
- SVG sparklines for selected container metrics
- auto-refresh of selected container's Recent metrics section when metrics events arrive
- optional Prometheus text exposition via `--prometheus` (`GET /metrics`, disabled by default)
- Prometheus output limited to already-normalised metric fields; no raw labels, env vars, or host paths
- local rule-based diagnostics via `diagnose` and `--diagnostics`
- diagnostics findings by severity and category
- evidence-driven diagnostics wording improvements for exposed-port, exited-container, and no-network
- diagnostics tuning rationale document at `docs/DIAGNOSTICS_TUNING.md`
- real-world validation issue workflow at `docs/VALIDATION_ISSUES.md`
- GitHub issue templates for validation results and bug reports
- validation tracking issues for Docker Desktop, Linux Engine, browsers, and Prometheus export
- manual-review wording for cleanup-related diagnostic recommendations
- validation guide under `docs/VALIDATION.md`
- local validation helper under `scripts/manual_validation.sh`
- release readiness helper under `scripts/release_check.sh`
- release readiness GitHub Actions workflow
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
15. Release automation must never publish tags, GitHub Releases, or PyPI packages without explicit human approval.
16. Metric history must remain local/browser-scoped unless a future goal explicitly changes that.
17. Prometheus export must remain opt-in; `GET /metrics` must return 404 without `--prometheus`; no raw Docker labels, environment variables, or host paths may appear in the output; no data may be persisted or pushed to external services.
18. Diagnostics severity tuning must be evidence-driven and must not increase severity merely to make findings look more serious.
19. Diagnostics wording may reduce false-positive noise, but severity and thresholds require documented real-world evidence before changing.
20. Validation result workflows and issue templates must not request secrets, production metadata, raw private host paths, or unreduced Docker inspect output.

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
14. For release work, whether tag/release/publish actions are manual-only unless explicitly approved
15. For Docker event-stream changes, whether API-side filtering has Python-side defense and safe fallback
16. For metric-history changes, whether data remains local, non-persistent, and not sent externally
17. For Prometheus or export-format changes, whether the endpoint remains disabled by default, whether no raw Docker labels/env vars/host paths are included, and whether no data is persisted or sent to external services
18. For diagnostics severity changes, whether each severity change is backed by real validation evidence, tests, and documented rationale
19. For diagnostics wording changes, whether finding IDs, severities, schema, and no-remediation constraints remain stable unless explicitly justified
20. For validation-result or issue-workflow PRs, whether: (a) no runtime code changes are present unless explicitly justified; (b) issue templates do not request secrets or production metadata; (c) validation docs preserve the local-first/read-only posture; (d) docs do not imply production readiness; (e) docs do not overclaim platform coverage

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
- v0.3.0 has been published on GitHub Releases.
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
- PR #14 mount source category tightening is complete.
- PR #15 real-world validation matrix is complete.
- PR #16 local vendored D3 asset for offline UI is complete.
- PR #18 v0.3.0 release readiness is complete.
- PR #19 Release Readiness GitHub Actions workflow is complete.
- PR #20 post-v0.3.0 release bookkeeping is complete.
- PR #21 Docker API-side event filters with Python-side defense-in-depth is complete.
- PR #22 AI workflow update after event filters is complete.
- PR #23 browser-local metric history and SVG sparklines is complete.
- PR #24 auto-refresh selected-node metric sparklines is complete.
- PR #25 AI workflow update after browser-local metric sparklines is complete.
- PR #26 optional Prometheus text exposition endpoint is complete.
- PR #27 post-Prometheus AI workflow and security policy sync is complete.
- PR #28 prepare docs for diagnostics severity tuning goal is complete.
- PR #29 diagnostics severity tuning wording improvements and rationale docs is complete.
- PR #30 AI workflow update after diagnostics tuning is complete.
- PR #31 real-world validation issue workflow and GitHub issue templates is complete.
- PR #37 disposable Postgres demo command fix from Codex review is complete.

Current capabilities:
- read-only Docker topology scanner
- ports, mounts, labels, Compose metadata
- secret-like label redaction
- optional host path redaction
- browser UI with vendored local D3 asset
- no default CDN dependency
- SSE live updates
- Docker API-side event filters plus Python-side is_relevant_event defense
- opt-in metrics
- Metric Glow
- browser-local metric history
- SVG sparklines in the selected container detail panel
- selected-node sparkline auto-refresh on incoming metrics events
- optional Prometheus text exposition via `--prometheus` (`GET /metrics`, disabled by default)
- local diagnostics findings
- evidence-driven diagnostics wording improvements
- diagnostics tuning rationale in `docs/DIAGNOSTICS_TUNING.md`
- issue-driven real-world validation workflow in `docs/VALIDATION_ISSUES.md`
- GitHub issue templates for validation results and bug reports
- validation tracking issues for Docker Desktop, Linux Engine, browsers, and Prometheus export
- CLI, HTTP API, SSE, and UI integration
- validation docs and helper scripts
- release readiness workflow

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
- For release automation, never publish tags, GitHub Releases, or PyPI packages without explicit human approval.
- For event-stream changes, preserve Python-side filtering and safe fallback.
- For metric-history changes, do not persist history or send it outside the local browser unless explicitly approved.
- Prometheus export must remain opt-in; `GET /metrics` must return 404 without `--prometheus`; no raw Docker metadata in output; no persistence or external push.
- Diagnostics severity tuning must be evidence-driven and must not add Docker mutations or remediation execution.
- Diagnostics wording changes must preserve finding ID stability, severity stability, and schema stability unless explicitly justified.
- Validation issues and bug reports must not request secrets, production metadata, or raw private host paths.

Review protocol:
- Inspect actual files and CI, not just PR text.
- Check safety constraints.
- Check tests.
- Check docs and packaging where relevant.
- Check whether the goal was actually met.
- Give one of: MERGE OK, REQUEST CHANGES, or REJECT / REVERT recommended.

Recommended next goal:
Post-release feedback and issue triage.

Answer format:
1. 【現状分析と評価】
2. 【本質的課題の抽出】
3. 【戦略的提言】
```

---

## Current planning phase

### Goal 15 — Post-release feedback and issue triage

Purpose:

Use the new validation tracking issues and any existing open issues to decide what should become v0.3.1 candidates, what should remain documentation-only, and what should be deferred.

Scope boundary:

- Triage and planning first
- No runtime feature expansion unless tied to a concrete issue
- No release automation changes
- No Docker mutation APIs
- No external telemetry
- No external AI API
- Do not claim production readiness

Primary focus areas:

- Review open validation tracking issues (#32–#36)
- Identify actual blockers vs platform-specific caveats
- Decide whether validation-driven bug fixes are needed before v0.3.1
- Keep package publishing automation deferred until the manual release process is stable
- Decide whether optional browser/E2E smoke testing should come before any packaging automation

---

## Future goal candidates after Goal 15

1. Package publishing automation only after manual release process is stable
2. Optional browser/E2E smoke testing
3. Validation-driven bug fixes
4. v0.3.1 release readiness
