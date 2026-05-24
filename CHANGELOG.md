# Changelog

All notable changes to Docker Topology Live are documented here.

Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) conventions.

## [Unreleased] — v0.3.0 Draft

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

- AI workflow control document (`docs/AI_WORKFLOW.md`) describing roles, completed milestones, safety constraints, and branch conventions (PR #10)
- `SECURITY.md` covering read-only access, loopback bind, label redaction, host path redaction, vendored D3, and no outbound connections
- `schemas/topology.schema.json`, `schemas/metrics.schema.json`, `schemas/diagnostics.schema.json` for all JSON contracts
- `docs/DATA_CONTRACT.md` and `docs/ARCHITECTURE.md` describing data flow and module layout

### Validation

- Real-world validation matrix in `docs/VALIDATION.md` covering sample mode, live Docker, metrics, diagnostics, privacy redaction, SSE, and offline D3 (PR #15, PR #16)
- `scripts/manual_validation.sh` interactive helper for local environment checks (PR #15)
- Unit test suite passes with `PYTHONPATH=src python -m unittest discover -s tests -v` (no Docker daemon required)

### Known Limitations

- Docker stats payloads vary across cgroups v1/v2 and Docker Desktop platforms; some metric fields may be zero or absent in certain environments
- Diagnostics rules are heuristic; false positives are possible, especially for `exposed-port` and `broad-bind-mount` rules in intentional configurations
- Browser UI tested manually; no automated browser/Selenium tests
- No Prometheus export
- No historical metrics or sparklines
- No Docker API-side event filters
- Production readiness on Linux Docker Engine and Docker Desktop requires manual validation per environment

[Unreleased]: https://github.com/hiroshitanaka-creator/Docker-Topology-Live/compare/main...HEAD
