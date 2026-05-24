# Data Contract

`/api/topology` returns a JSON document validated against
`schemas/topology.schema.json`.

## Top-level fields

| Field | Type | Notes |
|-------|------|-------|
| `schemaVersion` | `"1.0"` | Always present |
| `generatedAt` | ISO-8601 string | UTC timestamp of the scan |
| `source.engine` | `"docker"` or `"sample"` | Data source |
| `source.host` | string | Host label |
| `nodes` | array | Containers and networks |
| `links` | array | Edges connecting nodes |
| `summary` | object | Aggregated statistics |
| `warnings` | array | Non-fatal messages |
| `sample` | boolean | `true` when using built-in sample data |

## Node object

| Field | Present when | Description |
|-------|-------------|-------------|
| `id` | always | `"container:<12-char-id>"` or `"network:<12-char-id>"` |
| `label` | always | Human-readable name |
| `kind` | always | `"container"` or `"network"` |
| `status` | container | Docker status (`running`, `exited`, …) |
| `image` | container | Image reference (e.g. `nginx:latest`) |
| `state` | container | State string from Docker API |
| `driver` | network | Network driver (e.g. `bridge`) |
| `scope` | network | `"local"` or `"swarm"` |
| `internal` | network | `true` if the network is internal |

## Link object

| Field | Description |
|-------|-------------|
| `source` | Source node `id` |
| `target` | Target node `id` |
| `kind` | Always `"attached-to"` |
| `label` | IPv4 address of the container endpoint (may be empty) |

## Summary object

| Field | Description |
|-------|-------------|
| `nodes` | Total node count |
| `links` | Total link count |
| `containers` | Container node count |
| `runningContainers` | Containers with status `running` |
| `networks` | Network node count |
| `byKind` | `{ "container": N, "network": M }` |
| `byContainerStatus` | `{ "running": N, "exited": M, … }` |
