# Changelog

All notable changes to Docker Topology Live are documented here.

Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) conventions.

## [Unreleased]

### Added

- `docs/DIAGNOSTICS_TUNING.md`: evidence-driven diagnostics tuning notes
  documenting current rule thresholds, per-rule rationale, known
  false-positive patterns, and the evidence required before any severity
  or threshold change.  Includes a Goal 13 audit summary covering all
  14 diagnostic rules.

### Changed

- `exited-container` rule: description for `restarting` state changed from
  "is not serving traffic" (imprecise) to a precise crash-loop explanation
  noting that the restart policy is repeatedly bringing the container back
  after failures.
- `exited-container` rule: description for `exited` state now explicitly notes
  that an exited container may be intentional (e.g. a completed batch job) and
  directs the operator to check the exit code and logs.
- `no-network` rule: description now acknowledges that some containers (CLI
  tools, batch jobs, host-networked containers) are intentionally isolated.
  Recommendation now distinguishes between the "needs network" case and the
  "intentionally isolated" case to reduce false-positive noise.
- `exposed-port` rule (medium severity): recommendation now notes that binding
  to `0.0.0.0` is common in local development environments and may be
  intentional, to reduce false-positive noise for dev Docker stacks.

No severity levels or finding IDs were changed.  All changes are wording-only
and evidence-justified per the criteria in `docs/DIAGNOSTICS_TUNING.md`.

### Added (continued)

- Optional Prometheus text exposition endpoint at `GET /metrics`, enabled
  with `--prometheus`.  Disabled by default (returns HTTP 404 without the
  flag).  Exposes point-in-time container metrics (CPU%, memory, network,
  block I/O, PIDs, summary counters) in Prometheus text format 0.0.4.
  Only normalised fields are exported; raw Docker labels, env vars, and host
  paths are never included.  On collection failure a valid Prometheus
  response is returned with `metrics_warnings_total 1` — no traceback is
  exposed.  The existing `/api/metrics` JSON endpoint is unchanged.
  New module: `src/docker_topology_live/prometheus.py`.
  New CLI flag: `--prometheus` on the `serve` subcommand.

- Browser-local metric history and SVG sparklines in the node detail panel.
  When `--metrics` is enabled, each SSE `metrics` event appends one sample
  per container to an in-memory rolling window (up to 60 samples). Clicking
  a container shows CPU %, Memory %, Net RX/TX, and Block Write sparklines.
  History is never persisted and never sent outside the browser tab.
  Sparklines are rendered via `createElementNS` — no innerHTML, no external
  chart library.

### Changed

- Selected container detail panels now refresh only their `Recent metrics`
  sparkline section as new metrics events arrive. The graph is not re-rendered,
  topology is not refetched, and metric history remains browser-local and
  non-persistent.
- Docker event stream now requests API-side filtering via `client.events(filters=...)`,
  narrowing the stream to container and network lifecycle/membership events before
  Python receives them. Python-side `is_relevant_event()` is retained as defense-in-depth.
  If the Docker SDK or daemon does not support the requested filter shape, a warning is
  logged and the stream falls back to unfiltered automatically. Raw Docker events are
  still normalized before any SSE payload is sent to clients.

## [0.3.0] — 2026-05-25

### Added

- Packaged Python project under `src/docker_topology_live/` with `app.py` entrypoint and `dtl` console script (PR #3)
- Read-only Docker topology scanner: containers, networks, ports, mounts, labels, Docker Compose metadata extraction (PR #4)
- MIT License (PR #5)
- Docker Event API live topology updates and Server-Sent Events stream at `/api/events` with polling fallback (PR #6)
- Opt-in Docker stats metrics via `--metrics`; `/api/metrics` endpoint; Metric Glow UI with per-node CPU glow levels (PR #7)
- Local rule-based diagnostics engine (14 rules); `/api/diagnostics` endpoint; `python app.py diagnose` CLI; opt-in diagnostics SSE stream via `--diagnostics`; findings in browser detail panel (PR #8)
- Vendored D3 v7 browser bundle at `web/vendor/d3.min.js`; served locally at `/vendor/d3.min.js`; no CDN runtime dependency; ISC licence notice at `web/vendor/D3_LICENSE.txt` (PR #16)
- Optional host path redaction for bind mount sources via `--redact-host-paths`; `sourceCategory` always computed for bind mounts; `sourceRedacted` field in topology JSON (PR #13)
- Precise bind mount source category boundary matching using `_path_is_or_under()` to avoid false prefix matches (PR #14)
- Real-world validation matrix and manual validation helper (PR #15)
- Release readiness checklist, release notes draft, package build verification, and release readiness GitHub Actions workflow (PR #18, PR #19)

### Changed

- Manual-review wording added to cleanup-related diagnostic recommendations (`broad-bind-mount`, `privileged-label`, `exited-container`, `orphan-network`) (PR #11)
- Metrics failure during diagnostics now propagates a safe warning string into the diagnostics JSON `warnings` array instead of only logging server-side (PR #8 review fix)
- README updated to reflect all completed milestones through PR #16 (PR #12, PR #16)
- `pyproject.toml` version bumped to `0.3.0` for this release cycle

### Security

- Secret-like label values (keys containing `password`, `secret`, `token`, `apikey`, etc.) redacted with `***REDACTED***` before entering topology output (PR #4)
- Server binds to `127.0.0.1` by default; CORS disabled by default; `--allow-cors` is explicit opt-in (PR #3, PR #4)
- No Docker mutation APIs at any point; no container stop/remove/prune; no image or volume operations
- No external AI API calls; diagnostics are local, deterministic, and rule-based
- No telemetry; no outbound network connections except to the local Docker socket
- D3 visualisation library bundled locally; browser makes no CDN request at runtime (PR #16)
- Host path redaction option prevents bind mount source paths from entering topology output (PR #13)
- `innerHTML` absent from browser UI (`app.js` and `index.html`); DOM manipulation uses `createElement`, `textContent`, and `classList` only

### Documentation

- AI workflow control document (`docs/AI_WORKFLOW.md`) describing roles, completed milestones, safety constraints, and branch conventions (PR #10, PR #17)
- `SECURITY.md` covering read-only access, loopback bind, label redaction, host path redaction, vendored D3, and no outbound connections
- `schemas/topology.schema.json`, `schemas/metrics.schema.json`, `schemas/diagnostics.schema.json` for all JSON contracts
- `docs/DATA_CONTRACT.md` and `docs/ARCHITECTURE.md` describing data flow and module layout
- `CHANGELOG.md`, `docs/RELEASE.md`, and `docs/releases/v0.3.0.md` added for release management (PR #18)

### Validation

- Real-world validation matrix in `docs/VALIDATION.md` covering sample mode, live Docker, metrics, diagnostics, privacy redaction, SSE, and offline D3 (PR #15, PR #16)
- `scripts/manual_validation.sh` helper for local CLI/export checks (PR #15)
- `scripts/release_check.sh` helper for local package build and release-readiness checks (PR #18)
- Release Readiness GitHub Actions workflow for iPhone/browser-based release verification (PR #19)
- Unit test suite passes with `PYTHONPATH=src python -m unittest discover -s tests -v` (no Docker daemon required)

### Known Limitations

- Docker stats payloads vary across cgroups v1/v2 and Docker Desktop platforms; some metric fields may be zero or absent in certain environments
- Diagnostics rules are heuristic; false positives are possible, especially for `exposed-port` and `broad-bind-mount` rules in intentional configurations
- Browser UI tested manually; no automated browser/Selenium tests
- No Prometheus export
- No historical metrics or sparklines
- No Docker API-side event filters
- Production readiness on Linux Docker Engine and Docker Desktop requires manual validation per environment

[Unreleased]: https://github.com/hiroshitanaka-creator/Docker-Topology-Live/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/hiroshitanaka-creator/Docker-Topology-Live/releases/tag/v0.3.0
