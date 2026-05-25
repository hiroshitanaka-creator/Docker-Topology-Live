# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | Yes |
| < 0.3   | No  |

## Reporting a Vulnerability

Please report security issues via GitHub Issues (tag: `security`).

## Security Design

- **Read-only Docker access** – no container stop/remove, image remove, volume remove, network remove, or pruning operations are ever called.
- **Loopback bind by default** – the HTTP server binds to `127.0.0.1` unless explicitly overridden.
- **No secret export** – environment variables and secrets are never included in topology output.
- **Label redaction** – label keys containing `password`, `passwd`, `secret`, `token`, `apikey`, `api_key`, `credential`, `auth`, `private_key`, or `access_key` have their values replaced with `***REDACTED***`.
- **No outbound connections** – the package never initiates outbound network connections except to the local Docker socket.  The D3 visualisation library is bundled locally (see below); no CDN request is made at runtime.
- **Vendored D3** – D3 v7 is shipped as `web/vendor/d3.min.js` inside the Python package.  The browser loads it from `http://127.0.0.1:<port>/vendor/d3.min.js`.  No network egress to `cdn.jsdelivr.net` or any other CDN is required.  The ISC licence notice is included at `web/vendor/D3_LICENSE.txt`.  Only the single file `/vendor/d3.min.js` is served via the vendor route; no directory listing or arbitrary file access is possible.
- **Bind mount source redaction** – bind mount source paths can reveal local usernames, project directories, or sensitive host filesystem structure.  Pass `--redact-host-paths` to any subcommand (`scan`, `sample`, `serve`, `diagnose`) to replace all bind mount source paths with `[redacted]` in the output.  A safe `sourceCategory` label (`docker-socket`, `system`, `home`, `root`, `absolute-path`, …) is always included so diagnostics rules remain effective without the raw path.  Redaction does not mutate Docker resources and is off by default to preserve existing behaviour.
- **Prometheus export opt-in** – the `/metrics` endpoint (Prometheus text format) is disabled by default.  It is enabled only when `--prometheus` is explicitly passed to `serve`.  When enabled it exposes only already-normalised metric fields (container id, name, status, and numeric counters from Docker stats).  Raw Docker labels, environment variables, mount paths, and host paths are never included in the Prometheus output.  No data is persisted or sent to external services; the endpoint is a point-in-time scrape target for a local Prometheus instance.

## Host Path Redaction (`--redact-host-paths`)

Bind mount source paths in topology output may expose:
- Usernames (e.g. `/home/alice/project`)
- Client or project names (e.g. `/Users/bob/acme-corp/config`)
- Sensitive host filesystem structure (e.g. `/etc/ssl`, `/var/run/docker.sock`)

### Usage

```bash
# CLI topology scan — redact bind mount sources
python app.py scan --redact-host-paths

# Sample mode — no Docker required
python app.py sample --redact-host-paths

# Server — all topology responses (SSE + HTTP) use redacted paths
python app.py serve --redact-host-paths
python app.py serve --redact-host-paths --diagnostics

# Diagnostics — analysis uses safe category, not raw path
python app.py diagnose --redact-host-paths
python app.py diagnose --sample --redact-host-paths
```

### Data contract

When `--redact-host-paths` is active, each bind mount in topology JSON becomes:

```json
{
  "type": "bind",
  "destination": "/app/certs",
  "mode": "ro",
  "rw": false,
  "source": "[redacted]",
  "sourceRedacted": true,
  "sourceCategory": "system"
}
```

`sourceCategory` values:

| Value | Meaning |
|---|---|
| `docker-socket` | `/var/run/docker.sock` |
| `root` | Exactly `/` |
| `system` | `/etc`, `/proc`, `/sys`, `/var/run`, `/root` |
| `home` | `/home/*` or `/Users/*` |
| `absolute-path` | Any other absolute host path |
| `named-volume` | Docker named volume (not a host path) |
| `unknown` | Empty or unrecognised |

### Diagnostics under redaction

The `broad-bind-mount` diagnostic rule continues to fire when redaction is enabled.  It uses `sourceCategory` to determine severity:

- `docker-socket` → **high** severity
- `root`, `system`, `home` → **medium** severity
- `absolute-path`, `named-volume`, `unknown` → not flagged

Finding evidence when redacted:

```json
{
  "sourceRedacted": true,
  "sourceCategory": "system",
  "destination": "/app/certs",
  "mode": "ro",
  "rw": false
}
```

Raw host paths never appear in finding evidence when redaction is enabled.
