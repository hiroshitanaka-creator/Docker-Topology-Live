#!/usr/bin/env bash
set -euo pipefail

# Manual validation helper for Docker Topology Live.
#
# This script intentionally runs only local, read-only checks.
# It does not start the HTTP server, does not require a Docker daemon,
# and does not perform any Docker resource changes.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
export PYTHONPATH="${PYTHONPATH:-src}"

log() {
  printf '\n==> %s\n' "$*"
}

log "Python version"
"$PYTHON_BIN" --version

log "Compile check"
"$PYTHON_BIN" -m compileall app.py src tests

log "Unit tests"
"$PYTHON_BIN" -m unittest discover -s tests -v

log "Sample topology export"
"$PYTHON_BIN" app.py sample --output topology.sample.json

log "Sample topology export with host path redaction"
"$PYTHON_BIN" app.py sample --redact-host-paths --output topology.sample.redacted.json

log "Sample diagnostics"
"$PYTHON_BIN" app.py diagnose --sample > diagnostics.sample.json

log "Sample diagnostics with host path redaction"
"$PYTHON_BIN" app.py diagnose --sample --redact-host-paths > diagnostics.sample.redacted.json

log "Basic JSON sanity checks"
"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
for name in [
    "topology.sample.json",
    "topology.sample.redacted.json",
    "diagnostics.sample.json",
    "diagnostics.sample.redacted.json",
]:
    data = json.loads(Path(name).read_text(encoding="utf-8"))
    print(f"{name}: schemaVersion={data.get('schemaVersion')} keys={','.join(sorted(data.keys()))}")

redacted = Path("topology.sample.redacted.json").read_text(encoding="utf-8")
if "[redacted]" not in redacted:
    raise SystemExit("expected [redacted] marker in topology.sample.redacted.json")
print("redaction marker found")
PY

log "Validation helper completed"
printf '\nGenerated files:\n'
printf '  topology.sample.json\n'
printf '  topology.sample.redacted.json\n'
printf '  diagnostics.sample.json\n'
printf '  diagnostics.sample.redacted.json\n'
printf '\nFor live Docker and browser checks, follow docs/VALIDATION.md.\n'
