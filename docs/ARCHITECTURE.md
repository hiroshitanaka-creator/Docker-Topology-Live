# Architecture

## Overview

Docker Topology Live scans the local Docker daemon and exposes the topology as
JSON and as a live browser visualisation.

```
┌──────────────────────────────────────────────────────────┐
│                       app.py                             │
│                  (top-level entry point)                 │
│          delegates to docker_topology_live.cli           │
└───────────────────────┬──────────────────────────────────┘
                        │  PYTHONPATH=src
          src/docker_topology_live/
          ┌─────────────┼───────────────────────────────────┐
          │             │                                   │
       cli.py      scanner.py                          server.py
          │             │                                   │
          │         models.py                      web/index.html
          │         stats.py                       web/assets/app.js
          └─────────────┴───────────────────────────────────┘
```

## Module responsibilities

| Module | Role |
|--------|------|
| `cli.py` | `argparse` CLI: `scan`, `sample`, `serve`, `doctor` |
| `scanner.py` | Read-only Docker inspection; `build_sample()` needs no daemon |
| `models.py` | `@dataclass` types: `TopologyNode`, `TopologyLink`, `TopologySummary`, `Topology` |
| `stats.py` | Derives `TopologySummary` from `Topology` |
| `server.py` | stdlib `http.server`; routes `/`, `/api/topology`, `/api/stats`, `/healthz` |
| `web/` | D3 v7 force-directed browser UI (no build step) |

## Data flow

```
Docker socket (read-only)
        │
   scanner.scan_live()
        │   OR
   scanner.build_sample()
        │
   Topology  ──► .to_json()  ──► file (scan / sample command)
        │
   server.py ──► /api/topology ──► browser
                                      │
                               D3 force graph
```

## HTTP endpoints

| Path | Description |
|------|-------------|
| `GET /` | Browser UI (served from `web/index.html`) |
| `GET /api/topology` | Full topology JSON |
| `GET /api/stats` | Summary statistics JSON |
| `GET /healthz` | `{"status": "ok"}` — liveness probe |
| `GET /assets/styles.css` | CSS |
| `GET /assets/app.js` | JavaScript |

## Security boundaries

* Default bind address: `127.0.0.1` (loopback only).
* No Docker write APIs are called — no stop/remove/prune/rename operations.
* Secrets in container labels are redacted before serialisation.
* No environment variables or host filesystem secrets are included in output.
