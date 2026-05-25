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
| Sparklines appear | After multiple metric intervals, clicking a container shows sparklines in the detail panel. |
| Sparkline content | CPU % and Memory % sparklines have a 0–100 y-axis. Byte-counter sparklines show raw trends. |
| No persistence | Refreshing the page clears all sparkline history. No data is stored outside the browser tab. |

Known caveat:

Docker stats payloads can vary across cgroups versions and Docker platforms. Record zero or missing values by environment.

---

## Metric history and sparklines validation

Start the sample server with metrics:

```bash
python app.py serve --sample --metrics
```

Open:

```text
http://127.0.0.1:8080
```

Leave the browser open for at least 3–4 metric intervals (default: 2 seconds each), then click a container node.

Checklist:

| Check | Expected result |
|---|---|
| "Recent metrics" heading | Appears in the detail panel for container nodes. |
| Sparklines visible | CPU % and Memory % sparklines are visible after several metric intervals. |
| "Not enough history yet" | Shown if fewer than 2 samples have been received for that container. |
| Sample mode sparklines | May appear flat or identical since sample metrics are deterministic. That is acceptable. |
| No persistence | Reload the page; sparkline history is reset. No data is stored in browser storage. |
| Network nodes | Clicking a network node does not show sparklines (containers only). |
| No external chart library | DevTools → Network tab confirms no request to an external chart CDN. |
| No innerHTML | DevTools → Elements; sparklines are SVG elements built via `createElementNS`. |

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
| False positives | `exposed-port` and `no-network` descriptions acknowledge common intentional configurations. |
| Crash-loop wording | A container in `restarting` state shows a description that mentions crash-looping, not "not serving traffic". |
| Exited context | A container in `exited` state description mentions the possibility of intentional stops. |

See `docs/DIAGNOSTICS_TUNING.md` for the rationale behind each rule's current
severity level and the evidence required before any threshold change.

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
| API-side event filters | After starting/stopping a container, `docker-event` SSE events appear correctly; live topology updates still work with API-side filtering active. |
| Filter fallback | If the Docker daemon is older and does not support `filters=` on the event stream, a warning appears in the server log and the stream still works (check `docker_topology_live.events` logger at WARNING level). |

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

## Prometheus export validation

Start the sample server with Prometheus enabled:

```bash
python app.py serve --sample --prometheus
```

Check the endpoint:

```bash
curl -s http://127.0.0.1:8080/metrics | head -30
```

Checklist:

| Check | Expected result |
|---|---|
| HELP lines present | Output contains `# HELP docker_topology_live_` lines. |
| TYPE lines present | Output contains `# TYPE … gauge` lines. |
| Container metrics | `container_cpu_percent`, `container_memory_usage_bytes`, etc. appear. |
| Summary metrics | `containers_total` and `running_containers` appear. |
| Warnings metric | `metrics_warnings_total` appears. |
| Label format | Labels contain `container_id`, `container_name`, `status`. |
| No raw secrets | No Docker labels, env vars, or host paths in the output. |
| No traceback | No Python traceback in the response body. |
| Content-Type | `Content-Type: text/plain; version=0.0.4; charset=utf-8`. |
| Trailing newline | Output ends with a newline character. |
| 404 without flag | `curl http://127.0.0.1:8080/metrics` without `--prometheus` returns HTTP 404. |
| `/api/metrics` unchanged | `curl http://127.0.0.1:8080/api/metrics` still returns JSON. |

Optional: test with `--metrics` (live Docker) to confirm real container stats appear:

```bash
python app.py serve --metrics --prometheus
curl -s http://127.0.0.1:8080/metrics
```

---

## Filing and tracking validation results

After completing a validation run, record results as GitHub issues using the
workflow defined in `docs/VALIDATION_ISSUES.md`.

**Privacy requirements when filing issues:**

- Do not test on production Docker environments.
- Do not paste secrets, sensitive labels, raw host paths, or private client or
  project names into issues.
- Use `--redact-host-paths` when sharing any topology or diagnostics output.
- Prefer sample mode or a disposable demo stack for UI and SSE validation.

**Result classifications** (pass / bug / platform-specific caveat / documentation
gap / false positive / false negative / enhancement request) are defined in
`docs/VALIDATION_ISSUES.md`.  False-positive and false-negative diagnostics
findings are the primary input for future severity tuning — see
`docs/DIAGNOSTICS_TUNING.md` for the evidence requirements.

Use the issue templates in `.github/ISSUE_TEMPLATE/` to file results:

- `validation-result.md` — for structured validation run results
- `bug-report.md` — for reproducible bugs with steps to reproduce

---

## Package build validation

Use the automated release readiness script to verify compilation, tests, CLI smoke checks, asset integrity, and package build in one step:

```bash
# Requires: pip install --upgrade build
bash scripts/release_check.sh
```

The script checks:

- Python source compiles without errors (`python -m compileall`)
- All unit tests pass (`python -m unittest discover`)
- Sample topology and diagnostics export without error
- Redacted variants produce `sourceRedacted` fields
- `web/vendor/d3.min.js` and `D3_LICENSE.txt` are present on disk
- `index.html` references `/vendor/d3.min.js` and has no CDN reference
- No `innerHTML` in any web asset
- Built wheel (`python -m build`) contains `web/vendor/d3.min.js`, `D3_LICENSE.txt`, and `index.html`
- Built sdist contains `LICENSE`

The script does **not** upload anything, create tags, or publish releases. See `docs/RELEASE.md` for the full manual release checklist.

---

## Release readiness checklist

Before a release or public demo:

- all unit tests pass (`bash scripts/release_check.sh` exits zero)
- sample mode works without Docker
- live Docker topology works on at least one real Docker environment
- metrics work or fail safely
- diagnostics work or fail safely
- redaction mode hides raw bind mount source paths
- offline D3: `/vendor/d3.min.js` served correctly, no CDN egress
- `bash scripts/release_check.sh` wheel inspection confirms vendor assets included
- `CHANGELOG.md` includes the release section
- `docs/releases/v0.3.0.md` draft release notes reviewed
- `docs/RELEASE.md` Part A checklist completed
- README matches current behavior
- SECURITY.md matches current behavior
- no known traceback leaks in API or SSE responses
- no unintended external network calls
