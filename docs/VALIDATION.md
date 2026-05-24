# Real-world Validation Matrix

This document defines the manual validation matrix for Docker Topology Live.

The goal is to verify the project beyond unit tests: sample mode, live Docker mode, SSE behavior, metrics, diagnostics, privacy redaction, and browser UI behavior across real environments.

Use this before public demos, release tags, or large feature work.

---

## Validation principles

1. Keep validation local.
2. Do not use production Docker environments.
3. Do not include secrets in containers, labels, network names, or mount paths used for validation.
4. Prefer a disposable local test stack or an existing harmless local Docker setup.
5. Confirm that Docker Topology Live remains read-only.
6. Record OS, Docker engine, Python version, browser, and command line used.

---

## Environments to cover

| Environment | Priority | Notes |
|---|---:|---|
| Sample mode without Docker | Required | Must work on every machine with Python. |
| Docker Desktop on macOS | High | Common developer setup; validates path handling under `/Users`. |
| Docker Desktop on Windows / WSL2 | Medium | Useful for path and networking differences. |
| Linux Docker Engine | High | Closest to server-like Docker behavior. |
| Browser: Chrome / Chromium | High | Primary target. |
| Browser: Safari | Medium | Important for macOS users. |
| Browser: Firefox | Medium | Useful for EventSource behavior differences. |

---

## Baseline commands

Run from the repository root.

```bash
python -m compileall app.py src tests
python -m unittest discover -s tests -v
python app.py sample --output topology.json
python app.py diagnose --sample
python app.py sample --redact-host-paths --output topology.redacted.json
python app.py diagnose --sample --redact-host-paths
```

Expected result:

- commands complete without tracebacks
- generated JSON is valid
- redacted sample output uses `[redacted]` for bind mount source paths
- diagnostics output includes findings and summary
- sample mode does not require the Docker Python package or Docker daemon

---

## Sample server validation

Start the sample server:

```bash
python app.py serve --sample --metrics --diagnostics --redact-host-paths
```

Open:

```text
http://127.0.0.1:8080
```

Checklist:

| Check | Expected result |
|---|---|
| Page loads | Browser UI opens without console errors. |
| Graph appears | Containers and networks are visible. |
| Live status | Topbar shows live or idle status. |
| Metrics | Metric Glow is visible in sample mode. |
| Diagnostics | Diagnostics badges appear when findings exist. |
| Node detail | Clicking a node opens the detail panel. |
| Redacted mount | Bind mount source is shown as `[redacted]` with a category. |
| No unsafe rendering | Docker metadata appears as text, not HTML. |
| Offline D3 | Open browser DevTools → Network tab. Confirm no request is made to `cdn.jsdelivr.net`. D3 is loaded from `/vendor/d3.min.js` (status 200). |

API checks while server is running:

```bash
curl -s http://127.0.0.1:8080/healthz
curl -s http://127.0.0.1:8080/api/topology
curl -s http://127.0.0.1:8080/api/metrics
curl -s http://127.0.0.1:8080/api/diagnostics
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://127.0.0.1:8080/vendor/d3.min.js
```

Expected result:

- `/healthz` returns a healthy JSON response
- `/api/topology` returns topology JSON
- `/api/metrics` returns metrics JSON
- `/api/diagnostics` returns diagnostics JSON
- `/vendor/d3.min.js` returns HTTP 200 with `application/javascript` content type
- no Python traceback appears in responses

---

## Live Docker validation

Use a disposable local Docker environment with non-sensitive names and paths.

Start the server:

```bash
python app.py serve --metrics --diagnostics --redact-host-paths
```

Checklist:

| Area | Expected result |
|---|---|
| `/api/topology` | Shows real containers and networks. |
| `/api/events` | Browser updates after container or network lifecycle changes. |
| `/api/metrics` | Returns running container metrics when Docker stats are available. |
| `/api/diagnostics` | Returns findings or an empty findings list with safe warnings if data is unavailable. |
| Redaction | Bind mount source paths are not exposed when `--redact-host-paths` is enabled. |
| Diagnostics | Broad bind mount findings use `sourceCategory` when source paths are redacted. |
| CORS | `Access-Control-Allow-Origin` is absent unless `--allow-cors` is explicitly used. |
| Default bind | Server binds to `127.0.0.1` unless changed intentionally. |

Suggested manual actions during live validation:

- start or pause activity in a harmless test container and confirm the UI updates
- open one browser tab and then two browser tabs to observe repeated SSE connections
- test with and without `--metrics`
- test with and without `--diagnostics`
- test with and without `--redact-host-paths`

Record any environment-specific behavior in an issue.

---

## Metrics validation

Commands:

```bash
python app.py serve --metrics
curl -s http://127.0.0.1:8080/api/metrics
```

Checklist:

| Check | Expected result |
|---|---|
| Metrics endpoint | JSON document includes `schemaVersion`, `containers`, `summary`, and `warnings`. |
| CPU field | `cpuPercent` is present for containers with stats. |
| Memory fields | memory usage, limit, and percent are present when Docker provides them. |
| Network fields | RX/TX bytes are present. |
| Block I/O fields | read/write byte counters are present. |
| UI glow | Nodes receive glow classes when metrics show activity. |
| Failure behavior | If Docker stats are unavailable, output is safe and no traceback is exposed. |

Known caveat:

Docker stats payloads can vary across cgroups versions and Docker platforms. Record zero or missing values by environment.

---

## Diagnostics validation

Commands:

```bash
python app.py diagnose --sample
python app.py diagnose --sample --redact-host-paths
python app.py serve --sample --diagnostics
```

Checklist:

| Check | Expected result |
|---|---|
| CLI output | Valid JSON with `summary`, `findings`, and `warnings`. |
| Rule IDs | Findings include stable `ruleId` values. |
| Severity | Findings include `info`, `low`, `medium`, or `high`. |
| Recommendation | Cleanup-related recommendations include manual-review wording. |
| Secrets | Raw secret values do not appear. |
| Redaction | Raw bind mount source paths do not appear when redaction is enabled. |
| UI | Selected node detail panel shows findings for that node. |

---

## Privacy redaction validation

Commands:

```bash
python app.py sample --redact-host-paths --output topology.redacted.json
python app.py diagnose --sample --redact-host-paths
python app.py serve --sample --redact-host-paths --diagnostics
```

Checklist:

| Check | Expected result |
|---|---|
| Bind mount source | Replaced with `[redacted]`. |
| `sourceRedacted` | Present and true for redacted bind mounts. |
| `sourceCategory` | Present for bind mounts. |
| Named volumes | Not redacted as host paths. |
| Diagnostics evidence | Does not include raw host paths when redaction is enabled. |
| Browser UI | Shows `[redacted]` and category using safe text rendering. |

---

## SSE validation

Use the browser UI and watch the status text.

Checklist:

| Check | Expected result |
|---|---|
| Initial topology | UI loads a topology snapshot. |
| EventSource | UI enters live mode when SSE connects. |
| Fallback | UI falls back to polling if SSE fails repeatedly. |
| Metrics events | Emitted only with `--metrics`. |
| Diagnostics events | Emitted only with `--diagnostics`. |
| Safe errors | SSE error payloads do not contain Python tracebacks. |

Optional local stream check:

```bash
curl -N http://127.0.0.1:8080/api/events
```

Expected event names include `topology`, `heartbeat`, `metrics`, or `diagnostics` depending on the flags used.

---

## Validation report template

Use this template when reporting validation results:

```text
Environment:
- OS:
- Docker platform:
- Docker version:
- Python version:
- Browser:
- Command used:

Validation scope:
- sample mode:
- live topology:
- SSE:
- metrics:
- diagnostics:
- redaction:

Result:
- pass/fail:
- unexpected behavior:
- screenshots/logs:
- follow-up issue:
```

---

## Offline D3 validation

Checks that the browser UI works without any CDN access:

```bash
# Confirm the vendor file is served correctly
curl -s -o /dev/null -w "HTTP %{http_code} | type: %{content_type}\n" http://127.0.0.1:8080/vendor/d3.min.js

# Confirm index.html references the local path
grep -c "vendor/d3.min.js" src/docker_topology_live/web/index.html

# Confirm no CDN reference for D3 in index.html
grep "cdn.jsdelivr.net" src/docker_topology_live/web/index.html && echo "FAIL: CDN found" || echo "OK: no CDN"
```

Expected result:

- HTTP 200 with `application/javascript` content type for `/vendor/d3.min.js`
- `grep` count of 1 for `vendor/d3.min.js` in `index.html`
- no `cdn.jsdelivr.net` reference in `index.html`

Browser check:

1. Open `http://127.0.0.1:8080/` in a browser.
2. Open DevTools → Network tab.
3. Reload the page.
4. Confirm no request to `cdn.jsdelivr.net` appears.
5. Confirm `d3.min.js` loads from `/vendor/d3.min.js` with status 200.
6. Confirm the topology graph renders correctly.

---

## Release readiness checklist

Before a release or public demo:

- all unit tests pass
- sample mode works without Docker
- live Docker topology works on at least one real Docker environment
- metrics work or fail safely
- diagnostics work or fail safely
- redaction mode hides raw bind mount source paths
- offline D3: `/vendor/d3.min.js` served correctly, no CDN egress
- README matches current behavior
- SECURITY.md matches current behavior
- no known traceback leaks in API or SSE responses
- no unintended external network calls
