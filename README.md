# Docker Topology Live

Real-time Docker container topology scanner and browser visualiser.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/hiroshitanaka-creator/Docker-Topology-Live/actions/workflows/ci.yml/badge.svg)](https://github.com/hiroshitanaka-creator/Docker-Topology-Live/actions/workflows/ci.yml)

---

## Overview

Docker Topology Live inspects the local Docker daemon (read-only) and renders
containers, networks, and their connections as an interactive force-directed
graph in the browser.  A built-in **sample mode** lets you explore the UI
without Docker installed.

```
containers  ──attached-to──►  networks
    ▲                              │
    │                          IP address
    └──────── live scan ───────────┘
```

---

## Requirements

| Component | Minimum |
|-----------|---------|
| Python | 3.9+ |
| Docker SDK | optional (`pip install docker`) |
| Browser | Any modern browser |

---

## Installation

```bash
git clone https://github.com/hiroshitanaka-creator/Docker-Topology-Live.git
cd Docker-Topology-Live

pip install -e .          # no deps — works in sample mode immediately
pip install docker        # optional: required only for live Docker scanning
```

---

## Usage

### Browser UI

```bash
# Sample mode – no Docker needed
python app.py serve --sample

# Live mode – connects to the local Docker socket
python app.py serve

# Custom host / port
python app.py serve --host 0.0.0.0 --port 9090
```

Open **http://127.0.0.1:8080/** in your browser.

### Export topology to JSON

```bash
python app.py sample --output topology.json        # sample data
python app.py scan   --output topology.json        # live Docker
python app.py scan   --output topology.json --sample-on-error  # fallback
```

### Connectivity check

```bash
python app.py doctor
```

---

## Web UI features

- D3 v7 force-directed graph (no build step)
- **Circles** = containers (🟢 running · 🔴 exited · 🟠 paused)
- **Diamonds** = networks
- Hover tooltip · click for detail panel
- Text filter, zoom/pan, drag nodes
- Auto-refresh every 15 seconds
- SAMPLE badge when using built-in data

---

## HTTP API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Browser UI |
| `GET /api/topology` | Full topology JSON (schema v1.0) |
| `GET /api/stats` | Summary statistics |
| `GET /healthz` | `{"status": "ok"}` |

---

## Repository layout

```
.github/workflows/ci.yml        GitHub Actions CI
demo/docker-compose.yml         Multi-tier demo stack
docs/ARCHITECTURE.md            Architecture overview
docs/DATA_CONTRACT.md           API data contract
examples/topology.sample.json   Sample topology document
schemas/topology.schema.json    JSON Schema (draft-07)
src/docker_topology_live/       Python package
  models.py   scanner.py   stats.py   server.py   cli.py
  web/index.html   web/assets/styles.css   web/assets/app.js
tests/                          Unit tests (52 tests)
app.py                          Top-level entry point
pyproject.toml / Makefile
```

---

## Development

```bash
make install   # pip install -e .
make test      # 52 unit tests
make compile   # syntax check
make sample    # generate topology.json
make serve     # start server in sample mode
```

---

## Security

- Default bind: `127.0.0.1` — loopback only
- **Read-only** Docker access (no stop/remove/prune)
- Secret-like label values redacted (`password`, `token`, `secret` …)
- No environment variables or secrets exported

See [SECURITY.md](SECURITY.md) for full policy.

---

## License

MIT
