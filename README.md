# Docker Topology Live

**Docker Topology Live** is a local, read-only Docker topology viewer that turns containers, networks, ports, mounts, labels, live events, and runtime metrics into an interactive browser graph.

It is designed for developers who want to understand what is actually happening inside a local Docker environment without digging through `docker ps`, `docker network inspect`, and `docker stats` manually.

> From static Docker lists to a living local infrastructure map.

---

## What it does

Docker Topology Live can:

- scan local Docker containers and networks
- map container-to-network relationships
- show IP addresses, exposed ports, mounts, labels, and Docker Compose metadata
- redact secret-like label values
- serve a browser-based topology graph
- stream live topology updates with Server-Sent Events
- listen to Docker Event API changes in read-only mode
- collect opt-in runtime metrics from `docker stats`
- visualize load with Metric Glow
- run in sample mode without Docker

The project is intentionally local-first. By default, the server binds to `127.0.0.1`.

---

## Current status

Implemented:

- Packaged Python project under `src/docker_topology_live/`
- Top-level `app.py` entrypoint
- Read-only Docker topology scanner
- Container / network / port / mount / label / compose metadata extraction
- Secret-like label redaction
- Browser UI using D3 force-directed graph
- `/api/topology`
- `/api/stats`
- `/api/events` using Server-Sent Events
- Docker Event API live topology updates
- Polling fallback when SSE is unavailable
- `/api/metrics`
- Opt-in `docker stats` metrics collection
- Metric Glow UI
- Sample mode
- JSON schemas
- Unit tests and CI
- MIT License

In progress / roadmap:

- AI Diagnosis Mode
- diagnostics findings for security, reliability, resource, and maintenance risks
- optional host path redaction for mount sources
- Docker API-side event filters
- historical metrics / sparklines
- local D3 asset option for offline use

---

## Requirements

- Python 3.9+
- Docker daemon for live mode
- Docker Python SDK for live scanning and metrics
- A modern browser

Sample mode works without Docker.

---

## Installation

For sample mode and basic package installation:

```bash
pip install -e .
```

For live Docker scanning and metrics:

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

### 4. Sample UI with fake metrics

```bash
python app.py serve --sample --metrics
```

---

## CLI

```bash
python app.py scan [--output topology.json] [--sample-on-error]
python app.py sample [--output topology.json]
python app.py serve [--host 127.0.0.1] [--port 8080] [--sample] [--allow-cors] [--metrics] [--metrics-interval 2.0]
python app.py doctor
```

After installation, the console script is also available:

```bash
dtl serve --sample
dtl serve --metrics
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

### Check Docker daemon connectivity

```bash
python app.py doctor
```

### Start with metrics every 5 seconds

```bash
python app.py serve --metrics --metrics-interval 5.0
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
- CPU percentage in tooltip when metrics are enabled
- metrics detail panel with:
  - CPU %
  - memory usage / limit
  - memory %
  - network RX / TX
  - block read / write
  - PID count

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
| `error` | Safe error payload, no Python traceback |

The browser uses `EventSource('/api/events')`.

If SSE fails repeatedly, the UI falls back to 15-second polling.

---

## Metrics

Metrics are opt-in.

```bash
python app.py serve --metrics
```

Docker Topology Live uses:

```python
container.stats(stream=False)
```

The metrics collector is read-only.

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

Metrics document shape:

```json
{
  "schemaVersion": "1.0",
  "generatedAt": "2024-01-15T12:00:00Z",
  "source": {
    "engine": "docker",
    "host": "local"
  },
  "sample": false,
  "containers": [
    {
      "id": "container:abc123abc123",
      "name": "web",
      "status": "running",
      "cpuPercent": 12.34,
      "memoryUsageBytes": 104857600,
      "memoryLimitBytes": 1073741824,
      "memoryPercent": 9.77,
      "networkRxBytes": 1024,
      "networkTxBytes": 2048,
      "blockReadBytes": 0,
      "blockWriteBytes": 4096,
      "pids": 5
    }
  ],
  "summary": {
    "containers": 1,
    "runningContainers": 1,
    "avgCpuPercent": 12.34,
    "maxCpuPercent": 12.34,
    "totalMemoryUsageBytes": 104857600,
    "totalNetworkRxBytes": 1024,
    "totalNetworkTxBytes": 2048
  },
  "warnings": []
}
```

See:

```text
schemas/metrics.schema.json
```

---

## Data contracts

Schemas:

```text
schemas/topology.schema.json
schemas/metrics.schema.json
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

---

## Architecture

```text
app.py
  -> docker_topology_live.cli
      -> scanner.py       read-only Docker topology scanner
      -> metrics.py       read-only docker stats collector
      -> events.py        SSE formatting, Docker event stream, metrics stream
      -> server.py        ThreadingHTTPServer, API routes, static UI
      -> web/             D3 browser UI
```

Live update flow:

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

---

## Demo stack

Start a demo topology:

```bash
docker compose -f demo/docker-compose.yml up -d
```

Run the UI:

```bash
python app.py serve --metrics
```

Stop demo containers:

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
- no destructive Docker operations
- no `stop`
- no `remove`
- no `kill`
- no `restart`
- no `prune`
- no `exec`
- no `run`
- no image, volume, or network mutation
- no external AI API calls
- no telemetry
- no Docker metadata sent outside the local machine
- secret-like label values are redacted
- browser UI avoids `innerHTML`

Known caution:

- mount source paths may reveal local host paths
- metrics are point-in-time snapshots, not a security boundary
- D3 is currently loaded from CDN in the browser UI

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

Run sample server:

```bash
PYTHONPATH=src python app.py serve --sample
```

Run sample server with metrics:

```bash
PYTHONPATH=src python app.py serve --sample --metrics
```

Or use Make:

```bash
make test
make compile
make sample
make serve
```

---

## Development principles

This repository follows a strict safety-first development model:

1. read-only first
2. local-first
3. no destructive Docker operations
4. no external metadata transmission
5. deterministic JSON contracts
6. test before merge
7. AI-generated code must be reviewed before merge

The project is intentionally evolving through AI-assisted development, but AI-generated changes are treated as review targets, not automatically trusted output.

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

### Next

- [ ] AI Diagnosis Mode
- [ ] diagnostics JSON schema
- [ ] `python app.py diagnose`
- [ ] `/api/diagnostics`
- [ ] diagnostics UI
- [ ] host path redaction option
- [ ] offline D3 asset option
- [ ] historical metrics / sparkline
- [ ] Prometheus export, optional
- [ ] rule-based recommendations

---

## License

MIT. See:

```text
LICENSE
```