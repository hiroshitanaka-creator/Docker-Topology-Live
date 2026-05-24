# Docker Topology Live

Real-time Docker container topology scanner and browser visualiser. Connects to your local Docker daemon, maps every container and network relationship, and renders an interactive force-directed graph in the browser — refreshing automatically every 15 seconds.

## Requirements

- Python 3.9+
- `docker` Python SDK (`pip install docker`) for live scanning
- Docker daemon running (for live mode; sample mode works without Docker)
- A modern browser

## Installation

```bash
pip install -e .
```

Or run without installing:

```bash
PYTHONPATH=src python app.py <command>
```

## Usage

### Start the browser UI

```bash
# Sample data (no Docker needed)
python app.py serve --sample

# Live Docker data
python app.py serve
```

Then open http://127.0.0.1:8080/ in your browser.

### Export topology JSON

```bash
# From live Docker
python app.py scan --output topology.json

# Sample data
python app.py sample --output topology.json
```

### Check Docker connectivity

```bash
python app.py doctor
```

## Web UI

The browser UI features:
- Force-directed graph with zoom, pan, and drag
- Containers shown as circles, networks as diamonds
- Color-coded status (running=green, exited=red, paused=orange)
- Node detail panel (click any node)
- Text filter to highlight matching nodes
- Fit-to-view button
- Auto-refresh every 15 seconds

## Architecture

```
app.py  →  cli.py  →  scanner.py  →  Docker API (read-only)
                   →  server.py   →  /api/topology
                                  →  web/ (D3.js UI)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full details.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Browser UI |
| `GET /api/topology` | Full topology JSON |
| `GET /api/stats` | Summary statistics |
| `GET /healthz` | Health check |

See [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) for the JSON schema.

## Security

- Binds to `127.0.0.1` by default (loopback only)
- Read-only Docker access — no destructive operations
- Label values matching secret patterns (password, token, etc.) are redacted

See [SECURITY.md](SECURITY.md) for details.

## Testing

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Or with make:

```bash
make test
```

## Demo Stack

To try live mode with a realistic multi-container topology:

```bash
docker compose -f demo/docker-compose.yml up -d
python app.py serve
```

## License

MIT
