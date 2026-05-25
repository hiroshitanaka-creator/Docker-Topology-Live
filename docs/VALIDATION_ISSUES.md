# Validation Issue Workflow

This document defines how to turn real-world Docker Topology Live validation
runs into structured, actionable GitHub issues.

Use this alongside the validation matrix in `docs/VALIDATION.md`.

---

## Why real-world validation is needed

Unit tests verify that the code does what it was designed to do on a
controlled fixture.  They cannot verify:

- How Docker Desktop on macOS reports container stats or bind mount paths
- Whether EventSource reconnects correctly in Safari
- How cgroups v2 on Linux affects metric field availability
- Whether the Docker daemon on a specific platform supports API-side event filters
- How Windows path separators appear in bind mount sources

Real-world validation closes the gap.  It converts "works on CI" into "works
on the platforms users actually run."

**Validation data from real runs is also required before diagnostics severity
thresholds can be changed** — see `docs/DIAGNOSTICS_TUNING.md`.

---

## Privacy and safety requirements

Before running any real-world validation:

1. **Do not use production Docker environments.**  Use a disposable local
   test stack or a harmless local setup with non-sensitive container names,
   images, network names, and mount paths.

2. **Do not paste secrets, raw production metadata, client/project names,
   or private host paths into issues.**  If you need to share topology or
   diagnostics output, always use `--redact-host-paths` first.

3. **Do not include real container labels, environment variable names, or
   network names that could identify a production system.**

4. **When sharing any output, scrub container names and image tags that
   identify internal projects.**  Use placeholder names in issue descriptions.

5. **Prefer sample mode** (`--sample`) for UI and SSE behavior checks that
   do not require live Docker data.

6. **Use disposable demo stacks** for live topology validation:
   ```bash
   # Example: start a harmless local demo stack
   docker run -d --name demo-web nginx:alpine
   docker run -d --name demo-db -e POSTGRES_PASSWORD=demo postgres:alpine
   # ... validate ... then clean up
   docker rm -f demo-web demo-db
   ```

---

## Environments to validate

### Required (must pass before any release)

| Environment | Notes |
|---|---|
| Sample mode without Docker | Must work on any machine with Python 3.9+. No Docker package needed. |

### High priority

| Environment | Notes |
|---|---|
| Docker Desktop on macOS | Common developer setup. Validates `/Users` path handling in bind mounts, macOS file-system event behavior. |
| Linux Docker Engine | Closest to server-like Docker. Validates cgroups v2 stats, `/proc`/`/sys` bind mount detection. |
| Browser: Chrome / Chromium | Primary UI target. |

### Medium priority

| Environment | Notes |
|---|---|
| Docker Desktop on Windows / WSL2 | Windows path separators in bind mounts, WSL2 networking differences. |
| Browser: Safari | EventSource behavior on macOS. |
| Browser: Firefox | EventSource reconnect behavior. |

---

## Validation categories and per-category checklist

### 1 — Install and package smoke

```bash
pip install --editable .   # or: pip install dist/docker_topology_live-*.whl
python -c "import docker_topology_live; print('ok')"
python -m compileall app.py src tests
PYTHONPATH=src python -m unittest discover -s tests -v
```

Expected: imports without error; all unit tests pass.

### 2 — Sample mode (no Docker required)

```bash
python app.py sample --output topology.json
python app.py diagnose --sample
python app.py sample --redact-host-paths --output topology.redacted.json
python app.py diagnose --sample --redact-host-paths
```

Expected:
- Commands complete without tracebacks.
- `topology.json` is valid JSON with `schemaVersion`, `nodes`, `links`.
- `topology.redacted.json` contains `[redacted]` for bind mount sources.
- `diagnostics` output has `findings`, `summary`, `warnings`.

### 3 — Sample server UI

```bash
python app.py serve --sample --metrics --diagnostics --redact-host-paths
```

Open `http://127.0.0.1:8080/` in a browser.

| Check | Expected |
|---|---|
| Page loads | No console errors. |
| Graph renders | Force-directed graph of containers and networks is visible. |
| D3 loaded locally | DevTools → Network: `d3.min.js` loads from `/vendor/d3.min.js`, HTTP 200. No request to `cdn.jsdelivr.net`. |
| Node click | Clicking a container node opens the detail panel. |
| Metrics glow | CPU glow visible on container nodes. |
| Sparklines | After 3–4 metric intervals (≥ 6 s), CPU and Memory sparklines appear in the detail panel. |
| Redacted mount | Bind mount source shown as `[redacted]` with a category label. |
| Diagnostics | Findings badges appear in the detail panel when findings exist. |
| No innerHTML | DevTools → Elements: Docker metadata appears as text, not raw HTML. |

### 4 — Live topology scan

```bash
python app.py scan
python app.py serve --metrics --diagnostics --redact-host-paths
curl -s http://127.0.0.1:8080/api/topology
```

Expected:
- `scan` output includes real containers and networks.
- `/api/topology` returns topology JSON matching live state.
- Container names, images, ports, mounts, and network links are correct.

### 5 — SSE live updates

```bash
curl -N http://127.0.0.1:8080/api/events
```

In a separate terminal, start or stop a harmless test container.

| Check | Expected |
|---|---|
| `topology` event | Emitted on startup. |
| `heartbeat` event | Emitted every 30 s when idle. |
| `docker-event` event | Emitted when a container or network lifecycle event occurs. |
| `metrics` event | Emitted only with `--metrics`. |
| `diagnostics` event | Emitted only with `--diagnostics`. |
| No traceback in payload | Event `data:` lines never contain Python tracebacks. |
| Browser update | Graph updates after start/stop without page refresh. |
| Polling fallback | Stop the server while the browser is open — UI falls back to polling and shows fallback status. |

### 6 — Metrics

```bash
python app.py serve --metrics
curl -s http://127.0.0.1:8080/api/metrics | python -m json.tool
```

| Check | Expected |
|---|---|
| Response structure | `schemaVersion`, `containers`, `summary`, `warnings` present. |
| `cpuPercent` | Present for running containers (may be 0.0 on some platforms). |
| `memoryUsageBytes` | Present; non-zero for containers with active processes. |
| `memoryLimitBytes` | Present; may be the host total when no limit is set. |
| `networkRxBytes` / `networkTxBytes` | Present; reflect cumulative traffic since container start. |
| `blockReadBytes` / `blockWriteBytes` | Present; may be 0 on macOS Docker Desktop (cgroups v1 limitation). |
| `pids` | Present for running containers. |
| Missing fields | Document any fields consistently absent on this platform as a platform caveat. |

### 7 — Metric history and sparklines

Start the sample server with metrics:

```bash
python app.py serve --sample --metrics
```

Wait 4–5 metric intervals (≥ 8 s), then click a container node.

| Check | Expected |
|---|---|
| "Recent metrics" heading | Appears in the detail panel. |
| CPU % sparkline | Visible after ≥ 2 samples. |
| Memory % sparkline | Visible. |
| "Not enough history yet" | Shown if fewer than 2 samples received. |
| No persistence | Reload the page — sparkline history resets. |
| No external chart request | DevTools → Network: no request to any external chart CDN. |

### 8 — Diagnostics

```bash
python app.py diagnose --sample
python app.py diagnose --sample --redact-host-paths
python app.py serve --sample --diagnostics
curl -s http://127.0.0.1:8080/api/diagnostics | python -m json.tool
```

| Check | Expected |
|---|---|
| `findings` array | Present; non-empty in sample mode. |
| `ruleId` values | Each finding has a stable `ruleId`. |
| `severity` | One of `info`, `low`, `medium`, `high`. |
| Cleanup rules | `broad-bind-mount`, `privileged-label`, `exited-container`, `orphan-network` recommendations include "Manual review required". |
| `exited-container` (restarting) | Description mentions crash-loop, not just "not serving traffic". |
| `exposed-port` (medium) | Recommendation mentions local dev context. |
| No raw host paths | Redacted output has no raw paths; uses `[redacted]` and `sourceCategory`. |

**Record any diagnostics false positives** per rule per environment —
this data feeds future severity tuning per `docs/DIAGNOSTICS_TUNING.md`.

### 9 — Prometheus export

```bash
python app.py serve --sample --prometheus
curl -s http://127.0.0.1:8080/metrics | head -30
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/metrics
```

Without `--prometheus`:
```bash
python app.py serve --sample
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/metrics
```

| Check | Expected |
|---|---|
| `# HELP` lines | Present; prefixed `docker_topology_live_`. |
| `# TYPE … gauge` lines | Present for every metric. |
| Container metrics | `container_cpu_percent`, `container_memory_usage_bytes`, etc. |
| Label format | `container_id`, `container_name`, `status` labels. |
| No raw metadata | No Docker labels, env vars, or host paths in output. |
| Trailing newline | Output ends with `\n`. |
| Content-Type | `text/plain; version=0.0.4; charset=utf-8`. |
| 404 without flag | HTTP 404 when `--prometheus` is not used. |
| `/api/metrics` unchanged | `/api/metrics` still returns JSON regardless of `--prometheus`. |

### 10 — Host path redaction

```bash
python app.py serve --metrics --diagnostics --redact-host-paths
curl -s http://127.0.0.1:8080/api/topology | python -m json.tool | grep -i source
curl -s http://127.0.0.1:8080/api/diagnostics | python -m json.tool | grep -i source
```

| Check | Expected |
|---|---|
| `source` on bind mounts | `[redacted]` when `--redact-host-paths` is active. |
| `sourceRedacted` | `true` on bind mounts. |
| `sourceCategory` | Present; correct category (`docker-socket`, `system`, `home`, etc.). |
| Named volumes | Not redacted (not host paths). |
| Diagnostics evidence | No raw host paths when redacted. |
| `broad-bind-mount` findings | Still fire using `sourceCategory` when source is redacted. |

### 11 — Offline D3 check

```bash
curl -s -o /dev/null -w "HTTP %{http_code} | type: %{content_type}\n" \
  http://127.0.0.1:8080/vendor/d3.min.js
```

Expected: `HTTP 200 | type: application/javascript`.

In a browser with DevTools Network tab open and the page loaded:
- No request to `cdn.jsdelivr.net`.
- `d3.min.js` loads from `/vendor/d3.min.js`.

### 12 — CORS and bind defaults

```bash
curl -s -I http://127.0.0.1:8080/api/topology | grep -i Access-Control
python app.py serve --sample --allow-cors
curl -s -I http://127.0.0.1:8080/api/topology | grep -i Access-Control
```

| Check | Expected |
|---|---|
| CORS default off | No `Access-Control-Allow-Origin` header without `--allow-cors`. |
| CORS opt-in | `Access-Control-Allow-Origin: *` present when `--allow-cors` is used. |
| Default bind | Server listens on `127.0.0.1`; not reachable from other LAN hosts without explicit `--host`. |

---

## Result classification

After completing a validation run, classify each item as one of:

| Classification | Meaning |
|---|---|
| **pass** | Behavior matches expected. No action needed. |
| **bug** | Behavior is wrong and can be reproduced. File a bug report issue. |
| **platform-specific caveat** | Behavior differs from the primary Linux target but is expected for this platform (e.g. missing block I/O stats on macOS Docker Desktop). Document in the issue; update `docs/VALIDATION.md` if not already noted. |
| **documentation gap** | Validation reveals that existing docs are unclear or wrong. File a docs update issue. |
| **false positive** | A diagnostic finding fires for a legitimate intentional configuration. Record the rule ID, environment, and configuration in a diagnostics tuning issue. |
| **false negative** | A real problem is not caught by any diagnostic rule. Record what was missed and what evidence would justify a new rule. |
| **enhancement request** | The feature works but could be improved for this environment. File a separate enhancement issue. |

---

## How to file a validation result issue

Use the template at `.github/ISSUE_TEMPLATE/validation-result.md`.

**Before filing:**

1. Run the validation with `--redact-host-paths` wherever Docker metadata is
   involved.
2. Replace any real container names, image tags, or network names with
   placeholder values.
3. Do not paste full `docker inspect` output or raw environment variables.
4. If attaching log output, remove anything that could identify a production
   system.

---

## Suggested tracking issues

The following issues were planned for this project.  If they do not yet exist
in the GitHub issue tracker, they can be created from this list:

| Suggested title | Scope |
|---|---|
| Validation: Docker Desktop on macOS | Sections 3–12 from this doc on macOS + Docker Desktop |
| Validation: Docker Desktop on Windows / WSL2 | Sections 3–12 on Windows with WSL2 |
| Validation: Linux Docker Engine | Sections 3–12 on a Linux machine with Docker CE/EE |
| Validation: Browser UI across Chrome, Safari, Firefox | Sections 3, 5, 7 in each browser |
| Validation: Prometheus export in sample and live modes | Section 9 in both sample and live Docker modes |

Each tracking issue should:
- Reference this document as the checklist source.
- Note the OS, Docker version, Python version, and browser used.
- List results by validation section (pass / bug / caveat / gap).
- Avoid including secrets or production metadata.

---

## Recording platform-specific caveats

Known caveats discovered during validation should be added to
`docs/VALIDATION.md` under the relevant section.  Use this format:

```
Known caveat — <Platform>: <one-line description of the difference>.
```

Example:

```
Known caveat — Docker Desktop on macOS (cgroups v1):
`blockReadBytes` and `blockWriteBytes` are consistently 0 for most containers.
This is a Docker Desktop platform limitation, not a bug in Docker Topology Live.
```

---

## Using validation evidence for diagnostics tuning

Real-world validation runs are the **only** accepted basis for changing
diagnostic rule severity or thresholds.  The process is:

1. Complete a validation run on the target environment.
2. Record false-positive and false-negative findings with rule ID, severity,
   environment, and the container/network configuration that triggered them.
3. Open a diagnostics-tuning issue that references the validation run.
4. Propose the change with evidence in the issue before writing code.
5. Reference the issue in the PR that implements the change.

See `docs/DIAGNOSTICS_TUNING.md` for the full evidence requirements per rule.