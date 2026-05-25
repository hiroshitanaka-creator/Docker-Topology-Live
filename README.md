# Docker Topology Live

**Docker Topology Live** is a local, read-only Docker topology, metrics, and diagnostics viewer.

It turns local Docker containers, networks, ports, mounts, labels, live events, runtime metrics, and deterministic diagnostic findings into an interactive browser graph.

The project is built for developers who want to understand what is actually happening inside a local Docker environment without manually combining `docker ps`, `docker network inspect`, `docker events`, and `docker stats`.

> From static Docker lists to a living local infrastructure map.

---

## What it does

Docker Topology Live can:

- scan local Docker containers and networks
- map container-to-network relationships
- show IP addresses, published ports, mounts, labels, and Docker Compose metadata
- redact secret-like label values before they enter topology output
- serve an interactive browser graph
- stream live topology updates with Server-Sent Events
- listen to Docker Event API changes in read-only mode
- collect opt-in runtime metrics from Docker stats
- visualize load with Metric Glow
- run deterministic local diagnostics across topology and metrics
- display diagnostic findings in the browser UI
- run in sample mode without Docker

The project is intentionally local-first. By default, the server binds to `127.0.0.1`.

---

## Current status

Implemented:

- Packaged Python project under `src/docker_topology_live/`
- Top-level `app.py` entrypoint
- Read-only Docker topology scanner
- Container / network / port / mount / label / Compose metadata extraction
- Secret-like label redaction
- Browser UI using a D3 force-directed graph
- `/api/topology`
- `/api/stats`
- `/api/events` using Server-Sent Events
- Docker Event API live topology updates
- Polling fallback when SSE is unavailable
- `/api/metrics`
- Opt-in Docker stats metrics via `--metrics`
- Metric Glow UI
- `/api/diagnostics`
- `python app.py diagnose`
- Opt-in diagnostics stream via `--diagnostics`
- Local rule-based diagnostics for security, reliability, resource, and maintenance findings
- Manual-review wording for cleanup-related diagnostic recommendations
- Sample mode
- JSON schemas
- Unit tests and CI
- MIT License
- AI-assisted development workflow document
- Host path redaction (`--redact-host-paths`) for privacy-safe topology output
- Offline D3 asset: D3 v7 vendored locally — no CDN required

Roadmap candidates:

- Docker API-side event filters
- historical metrics / sparklines
- optional Prometheus export
- real-world validation matrix across Docker Desktop and Linux Docker Engine
- diagnostics severity tuning after real environment testing

---

## Requirements

- Python 3.9+
- Docker daemon for live mode
- Docker Python SDK for live scanning, live events, and metrics
- A modern browser

Sample mode works without Docker.

---

## Installation

For sample mode and basic package installation:

```bash
pip install -e .
```

For live Docker scanning, events, and metrics:

```bash
pip install -e ".[docker]"
```

Alternatively:

```bash
pip install docker
```

Run without installing by setting `PYTHONPATH`:

```bash
PYTHONPATH=src python app.py <command>
```

---

## Quick start

### 1. Start sample UI

No Docker required.

```bash
python app.py serve --sample
```

Open:

```text
http://127.0.0.1:8080
```

### 2. Start live Docker UI

```bash
python app.py serve
```

### 3. Start live UI with metrics

```bash
python app.py serve --metrics
```

### 4. Start sample UI with fake metrics and diagnostics

```bash
python app.py serve --sample --metrics --diagnostics
```

### 5. Start live UI with metrics and diagnostics

```bash
python app.py serve --metrics --diagnostics
```

---

## CLI

```bash
python app.py scan [--output topology.json] [--sample-on-error]
python app.py sample [--output topology.json]
python app.py diagnose [--sample] [--include-metrics] [--output FILE] [--format json]
python app.py serve [--host 127.0.0.1] [--port 8080] [--sample] [--allow-cors] [--metrics] [--metrics-interval 2.0] [--diagnostics] [--diagnostics-interval 5.0]
python app.py doctor
```

After installation, the console script is also available:

```bash
dtl serve --sample
dtl serve --metrics --diagnostics
dtl diagnose --sample
```

---

## Common commands

### Export live topology JSON

```bash
python app.py scan --output topology.json
```

### Export sample topology JSON

```bash
python app.py sample --output topology.json
```

### Run sample diagnostics

```bash
python app.py diagnose --sample
```

### Run live diagnostics

```bash
python app.py diagnose
```

### Run live diagnostics with metrics

```bash
python app.py diagnose --include-metrics
```

### Start the server with metrics and diagnostics

```bash
python app.py serve --metrics --diagnostics
```

### Tune metrics and diagnostics intervals

```bash
python app.py serve --metrics --metrics-interval 5.0 --diagnostics --diagnostics-interval 10.0
```

### Check Docker daemon connectivity

```bash
python app.py doctor
```

---

## Web UI

The browser UI provides:

- force-directed topology graph
- containers as circles
- networks as diamonds
- color-coded container status
- drag, zoom, pan, and fit-to-view
- text filter
- node detail panel
- live topology updates through SSE
- polling fallback
- optional Metric Glow
- optional diagnostics summary bar
- per-node diagnostic findings in the detail panel

Metric display includes:

- CPU percentage in tooltip when metrics are enabled
- CPU %
- memory usage / limit
- memory %
- network RX / TX
- block read / write
- PID count

Diagnostic display includes:

- severity counts in the topbar
- findings grouped by selected node
- finding title, description, recommendation, and severity
- manual-review wording for cleanup-related recommendations

Metric Glow levels:

| Class | CPU threshold | Meaning |
|---|---:|---|
| `glow-low` | >= 5% | light activity |
| `glow-medium` | >= 15% | moderate activity |
| `glow-high` | >= 40% | high activity |
| `glow-critical` | >= 80% | critical activity / pulse |

---

## API endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Browser UI |
| `GET /api/topology` | Full topology JSON snapshot |
| `GET /api/stats` | Topology summary statistics |
| `GET /api/events` | Server-Sent Events stream |
| `GET /api/metrics` | Point-in-time container metrics snapshot |
| `GET /api/diagnostics` | Point-in-time local diagnostics snapshot |
| `GET /healthz` | Health check |

---

## Server-Sent Events

`GET /api/events` streams live updates.

Event types:

| Event | Description |
|---|---|
| `topology` | Full topology snapshot |
| `docker-event` | Normalized Docker event metadata |
| `heartbeat` | Sample-mode idle heartbeat |
| `metrics` | Runtime metrics snapshot, only when `--metrics` is enabled |
| `diagnostics` | Diagnostics snapshot, only when `--diagnostics` is enabled |
| `error` | Safe error payload, no Python traceback |

The browser uses `EventSource('/api/events')`.

If SSE fails repeatedly, the UI falls back to 15-second polling.

The Docker event stream uses API-side filters (`type: container, network`) to reduce
noise from image, volume, and plugin events before they reach Python.
`is_relevant_event()` is always applied as a second validation layer.
If the Docker daemon does not support the filter shape, the stream falls back to
unfiltered automatically with no impact on functionality.

---

## Metrics

Metrics are opt-in.

```bash
python app.py serve --metrics
```

Docker Topology Live uses the read-only Docker stats call:

```python
container.stats(stream=False)
```

Metrics include:

- CPU percent
- memory usage bytes
- memory limit bytes
- memory percent
- network RX bytes
- network TX bytes
- block read bytes
- block write bytes
- PIDs, when available

Metrics are point-in-time snapshots. They are not persisted.

See:

```text
schemas/metrics.schema.json
```

---

## Diagnostics

Diagnostics are local, deterministic, and rule-based.

They do **not** call external AI APIs. They do **not** send Docker metadata outside the local machine. They do **not** execute remediation. They only produce findings and recommendations.

Run diagnostics from the CLI:

```bash
python app.py diagnose --sample
python app.py diagnose
python app.py diagnose --include-metrics
```

Run diagnostics in the browser UI:

```bash
python app.py serve --sample --diagnostics
python app.py serve --metrics --diagnostics
```

Diagnostics categories:

- security
- reliability
- resource
- maintenance

Finding fields:

- `id`
- `ruleId`
- `severity`
- `category`
- `target`
- `title`
- `description`
- `evidence`
- `recommendation`
- `confidence`

Example diagnostics shape:

```json
{
  "schemaVersion": "1.0",
  "generatedAt": "2024-01-15T12:00:00Z",
  "source": {
    "engine": "docker",
    "host": "local"
  },
  "sample": false,
  "summary": {
    "findings": 1,
    "bySeverity": {
      "medium": 1
    },
    "byCategory": {
      "security": 1
    }
  },
  "findings": [
    {
      "id": "finding:ebb0f1ccdc88",
      "ruleId": "exposed-port",
      "severity": "medium",
      "category": "security",
      "target": {
        "kind": "container",
        "id": "container:abc123abc123",
        "label": "web"
      },
      "title": "Port 80/tcp published to host",
      "description": "Container port 80/tcp is published to host port 8080.",
      "evidence": {
        "hostPort": 8080,
        "containerPort": 80,
        "protocol": "tcp"
      },
      "recommendation": "Review whether this published port is intentional.",
      "confidence": 1.0
    }
  ],
  "warnings": []
}
```

Cleanup-related recommendations explicitly require manual review before action.

See:

```text
schemas/diagnostics.schema.json
```

---

## Data contracts

Schemas:

```text
schemas/topology.schema.json
schemas/metrics.schema.json
schemas/diagnostics.schema.json
```

Topology data includes:

- containers
- networks
- links
- status
- image
- ports
- mounts
- labels
- Docker Compose metadata
- summary
- warnings

Metrics data includes:

- per-container runtime metrics
- aggregate summary
- warnings

Diagnostics data includes:

- findings
- severity summary
- category summary
- evidence
- recommendation
- confidence
- warnings

---

## Architecture

```text
app.py
  -> docker_topology_live.cli
      -> scanner.py        read-only Docker topology scanner
      -> metrics.py        read-only Docker stats collector
      -> diagnostics.py    local rule-based finding engine
      -> events.py         SSE formatting, Docker event stream, metrics stream, diagnostics stream
      -> server.py         ThreadingHTTPServer, API routes, static UI
      -> web/              D3 browser UI
```

Live topology flow:

```text
Docker Event API
  -> events.py
      -> debounce
          -> scan_live()
              -> SSE topology event
                  -> browser render()
```

Metrics flow:

```text
container.stats(stream=False)
  -> metrics.py
      -> /api/metrics
      -> SSE metrics event
          -> browser Metric Glow
```

Diagnostics flow:

```text
Topology + optional Metrics
  -> diagnostics.py
      -> /api/diagnostics
      -> SSE diagnostics event
          -> browser diag-bar and node findings
```

---

## Demo stack

Start a demo topology:

```bash
docker compose -f demo/docker-compose.yml up -d
```

Run the UI with metrics and diagnostics:

```bash
python app.py serve --metrics --diagnostics
```

Stop the demo stack when finished:

```bash
docker compose -f demo/docker-compose.yml down
```

---

## Security model

Docker Topology Live is designed as a local read-only inspection tool.

Security defaults:

- binds to `127.0.0.1`
- CORS is disabled by default
- `--allow-cors` is explicit opt-in
- no Docker mutation APIs
- no remediation execution
- no external AI API calls
- no telemetry
- no Docker metadata sent outside the local machine
- secret-like label values are redacted
- browser UI avoids `innerHTML`
- diagnostics are recommendations only
- cleanup-related recommendations require manual review
- D3 visualisation library bundled locally (no CDN egress at runtime)

Known cautions:

- mount source paths may reveal local host paths (use `--redact-host-paths` to suppress)
- metrics are point-in-time snapshots, not a security boundary
- diagnostics are heuristic and may produce false positives

See:

```text
SECURITY.md
```

---

## Testing

Run all tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Compile check:

```bash
PYTHONPATH=src python -m compileall app.py src tests
```

Generate sample topology:

```bash
PYTHONPATH=src python app.py sample --output topology.json
```

Run sample diagnostics:

```bash
PYTHONPATH=src python app.py diagnose --sample
```

Run sample server:

```bash
PYTHONPATH=src python app.py serve --sample
```

Run sample server with metrics and diagnostics:

```bash
PYTHONPATH=src python app.py serve --sample --metrics --diagnostics
```

Or use Make:

```bash
make test
make compile
make sample
make serve
```

Release readiness check (requires `pip install --upgrade build`):

```bash
bash scripts/release_check.sh
```

---

## Changelog and release notes

- `CHANGELOG.md` — project change history following Keep a Changelog conventions
- `docs/RELEASE.md` — repeatable release readiness checklist (Part A: PR work; Part B: manual tag and publish)
- `docs/releases/v0.3.0.md` — draft v0.3.0 release notes

---

## AI-assisted development workflow

This repository is intentionally evolving through AI-assisted development.

AI-generated code is treated as review material, not trusted output. Every meaningful PR should be reviewed for:

- scope control
- security constraints
- read-only behavior
- tests
- CI status
- documentation accuracy

See:

```text
docs/AI_WORKFLOW.md
```

---

## Development principles

1. local-first
2. read-only first
3. deterministic JSON contracts
4. no external metadata transmission
5. no remediation execution
6. test before merge
7. AI-generated code must be reviewed before merge

---

## Roadmap

### Completed

- [x] Package structure
- [x] Docker topology scanner
- [x] Browser topology graph
- [x] Metadata extraction
- [x] Security hardening
- [x] MIT License
- [x] Docker Event API live updates
- [x] Server-Sent Events
- [x] Metric Glow
- [x] `/api/metrics`
- [x] AI Diagnosis Mode
- [x] diagnostics JSON schema
- [x] `python app.py diagnose`
- [x] `/api/diagnostics`
- [x] diagnostics UI
- [x] rule-based recommendations
- [x] manual-review wording for cleanup-related diagnostics
- [x] AI workflow control document
- [x] host path redaction (`--redact-host-paths`)
- [x] offline D3 asset (vendored locally, no CDN)
- [x] v0.3.0 release readiness (changelog, release checklist, draft release notes, build verification)

### Next

- [ ] Docker API-side event filters
- [ ] historical metrics / sparklines
- [ ] Prometheus export, optional
- [ ] diagnostics severity tuning after real-environment validation

---

## License

MIT. See:

```text
LICENSE
```
