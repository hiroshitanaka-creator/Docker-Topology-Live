#!/usr/bin/env bash
# scripts/release_check.sh
#
# Local-only release readiness verification for Docker Topology Live.
#
# This script:
#   - compiles all Python source
#   - runs the full unit test suite
#   - runs CLI smoke checks (sample topology, diagnostics, redacted variants)
#   - builds the wheel and sdist with python -m build
#   - inspects the wheel to confirm vendored D3 assets are included
#
# This script does NOT:
#   - upload anything to PyPI or TestPyPI
#   - create a Git tag or GitHub Release
#   - push to any remote branch
#   - start a server or require a Docker daemon
#
# Usage:
#   bash scripts/release_check.sh
#
# Requirements:
#   pip install --upgrade build
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHONPATH="${REPO_ROOT}/src"
export PYTHONPATH

# ── helpers ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; }
info() { echo -e "${YELLOW}→${NC} $*"; }
separator() { echo "──────────────────────────────────────────────────"; }

ERRORS=0
record_fail() { fail "$1"; ERRORS=$(( ERRORS + 1 )); }

# ── 1. Compile check ─────────────────────────────────────────────────────────
separator
info "1/6 Compile check"
if python -m compileall -q app.py src tests; then
    pass "All Python source files compiled without errors"
else
    record_fail "Compile check failed"
fi

# ── 2. Unit tests ────────────────────────────────────────────────────────────
separator
info "2/6 Unit tests"
if python -m unittest discover -s tests -q 2>&1; then
    pass "All unit tests passed"
else
    record_fail "Unit tests failed"
fi

# ── 3. CLI smoke checks ───────────────────────────────────────────────────────
separator
info "3/6 CLI smoke checks"

TOPO_JSON="$(mktemp /tmp/dtl-release-topo.XXXXXX.json)"
TOPO_REDACTED_JSON="$(mktemp /tmp/dtl-release-topo-redacted.XXXXXX.json)"
DIAG_JSON="$(mktemp /tmp/dtl-release-diag.XXXXXX.json)"
DIAG_REDACTED_JSON="$(mktemp /tmp/dtl-release-diag-redacted.XXXXXX.json)"

# sample topology
if python app.py sample --output "$TOPO_JSON" 2>/dev/null; then
    pass "sample topology export: $TOPO_JSON"
else
    record_fail "sample topology export failed"
fi

# sample diagnostics
if python app.py diagnose --sample --format json --output "$DIAG_JSON" 2>/dev/null; then
    pass "sample diagnostics export: $DIAG_JSON"
else
    record_fail "sample diagnostics export failed"
fi

# redacted topology
if python app.py sample --redact-host-paths --output "$TOPO_REDACTED_JSON" 2>/dev/null; then
    # confirm sourceRedacted appears
    if grep -q "sourceRedacted" "$TOPO_REDACTED_JSON"; then
        pass "redacted topology includes sourceRedacted field"
    else
        record_fail "redacted topology missing sourceRedacted field"
    fi
    pass "sample redacted topology export: $TOPO_REDACTED_JSON"
else
    record_fail "sample redacted topology export failed"
fi

# redacted diagnostics
if python app.py diagnose --sample --redact-host-paths --format json --output "$DIAG_REDACTED_JSON" 2>/dev/null; then
    pass "sample redacted diagnostics export: $DIAG_REDACTED_JSON"
else
    record_fail "sample redacted diagnostics export failed"
fi

rm -f "$TOPO_JSON" "$TOPO_REDACTED_JSON" "$DIAG_JSON" "$DIAG_REDACTED_JSON"

# ── 4. Asset integrity checks ─────────────────────────────────────────────────
separator
info "4/6 Asset integrity checks"

VENDOR_D3="src/docker_topology_live/web/vendor/d3.min.js"
VENDOR_LIC="src/docker_topology_live/web/vendor/D3_LICENSE.txt"
INDEX_HTML="src/docker_topology_live/web/index.html"

if [ -f "$VENDOR_D3" ]; then
    pass "Vendored D3 bundle present: $VENDOR_D3"
else
    record_fail "Vendored D3 bundle missing: $VENDOR_D3"
fi

if [ -f "$VENDOR_LIC" ]; then
    pass "D3 licence notice present: $VENDOR_LIC"
else
    record_fail "D3 licence notice missing: $VENDOR_LIC"
fi

if grep -q "vendor/d3.min.js" "$INDEX_HTML"; then
    pass "index.html references /vendor/d3.min.js"
else
    record_fail "index.html does not reference /vendor/d3.min.js"
fi

if ! grep -q "cdn.jsdelivr.net" "$INDEX_HTML"; then
    pass "index.html has no CDN reference"
else
    record_fail "index.html contains a cdn.jsdelivr.net reference"
fi

# Check for innerHTML *assignments* only in authored assets (comments mentioning innerHTML are fine).
# d3.min.js is a vendored third-party file and is excluded from this check.
_INNER_HTML_HITS=0
if grep -Eq '\.innerHTML[[:space:]]*=' src/docker_topology_live/web/index.html 2>/dev/null; then
    _INNER_HTML_HITS=$(( _INNER_HTML_HITS + 1 ))
    record_fail "innerHTML assignment found in index.html"
fi
if grep -Eq '\.innerHTML[[:space:]]*=' src/docker_topology_live/web/assets/app.js 2>/dev/null; then
    _INNER_HTML_HITS=$(( _INNER_HTML_HITS + 1 ))
    record_fail "innerHTML assignment found in app.js"
fi
if [ "$_INNER_HTML_HITS" -eq 0 ]; then
    pass "No innerHTML assignments in index.html or app.js (vendored d3.min.js excluded)"
fi

# ── 5. Package build ──────────────────────────────────────────────────────────
separator
info "5/6 Package build"

# Check python -m build is available
if ! python -m build --version >/dev/null 2>&1; then
    fail "python -m build is not available"
    echo ""
    echo "  Install it with:"
    echo "    python -m pip install --upgrade build"
    echo ""
    record_fail "Package build skipped — 'build' module not installed"
else
    pass "python -m build is available ($(python -m build --version 2>/dev/null | head -1))"

    # Clean previous artifacts
    rm -rf dist/ build/ src/*.egg-info src/docker_topology_live.egg-info
    info "Cleaned previous dist/ build/ artifacts"

    # Build
    if python -m build --quiet 2>&1; then
        pass "python -m build completed"
    else
        record_fail "python -m build failed"
    fi

    # ── 6. Wheel inspection ───────────────────────────────────────────────────
    separator
    info "6/6 Wheel inspection"

    WHEEL="$(ls dist/*.whl 2>/dev/null | head -1)"
    if [ -z "$WHEEL" ]; then
        record_fail "No wheel found in dist/"
    else
        pass "Wheel: $WHEEL"

        # Capture wheel listing once to avoid grep -q + pipefail SIGPIPE issue.
        _WHEEL_LISTING="$(unzip -l "$WHEEL" 2>/dev/null)"

        # List vendor and web entries for reference
        echo ""
        info "Wheel contents (vendor and web entries):"
        echo "$_WHEEL_LISTING" | grep -E "(vendor|web/)" || echo "  (none found)"
        echo ""

        if echo "$_WHEEL_LISTING" | grep -q "web/vendor/d3.min.js"; then
            pass "Wheel includes web/vendor/d3.min.js"
        else
            record_fail "Wheel is missing web/vendor/d3.min.js"
        fi

        if echo "$_WHEEL_LISTING" | grep -q "web/vendor/D3_LICENSE.txt"; then
            pass "Wheel includes web/vendor/D3_LICENSE.txt"
        else
            record_fail "Wheel is missing web/vendor/D3_LICENSE.txt"
        fi

        if echo "$_WHEEL_LISTING" | grep -q "web/index.html"; then
            pass "Wheel includes web/index.html"
        else
            record_fail "Wheel is missing web/index.html"
        fi
    fi

    SDIST="$(ls dist/*.tar.gz 2>/dev/null | head -1)"
    if [ -n "$SDIST" ]; then
        # Capture sdist listing to avoid grep -q + pipefail SIGPIPE issue.
        _SDIST_LISTING="$(tar -tzf "$SDIST" 2>/dev/null)"
        if echo "$_SDIST_LISTING" | grep -q "LICENSE"; then
            pass "sdist includes LICENSE file"
        else
            record_fail "sdist is missing LICENSE file"
        fi
        pass "sdist: $SDIST"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
separator
if [ "$ERRORS" -eq 0 ]; then
    echo -e "\n${GREEN}All release readiness checks passed.${NC}"
    echo ""
    echo "  This script does NOT create a tag, publish a GitHub Release,"
    echo "  or upload to PyPI. Those steps require explicit human approval."
    echo "  See docs/RELEASE.md for the full release checklist."
    echo ""
    exit 0
else
    echo -e "\n${RED}${ERRORS} check(s) failed.${NC}"
    echo "  Fix the issues above before proceeding to release."
    echo ""
    exit 1
fi
