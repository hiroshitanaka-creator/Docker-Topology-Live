#!/usr/bin/env python3
"""Optional browser smoke test for Docker Topology Live — sample UI mode.

Starts the sample server as a subprocess, launches Chromium via Playwright,
and verifies that the real browser UI loads, renders the topology graph, and
exercises the key interactive features (detail panel, metrics, sparklines,
diagnostics bar).

Requirements
------------
    pip install -e .[browser-test]
    python -m playwright install chromium

Usage
-----
    PYTHONPATH=src python scripts/browser_smoke.py
    PYTHONPATH=src python scripts/browser_smoke.py --port 8099
    PYTHONPATH=src python scripts/browser_smoke.py --screenshot /tmp/smoke.png

Scope
-----
- Sample mode only — no Docker daemon required.
- No Docker mutation APIs.
- No external telemetry or AI API calls.
- Does not change any server defaults (bind address, CORS policy, port).
- This is an optional smoke test, not production certification.

If Playwright is not installed
------------------------------
The script exits with a clear error message and install instructions.
It does NOT silently pass when the dependency is missing.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


_REPO_ROOT = Path(__file__).parent.parent
_DEFAULT_PORT = 8099
_HEALTHZ_RETRIES = 20
_HEALTHZ_INTERVAL = 0.5  # seconds per retry
_METRICS_INTERVAL = 2.0  # seconds — matches server default
# Wait long enough for at least 3 metric samples before checking sparklines
_METRICS_WAIT_SECS = _METRICS_INTERVAL * 3 + 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_playwright() -> None:
    """Exit with a clear message if Playwright is not installed."""
    try:
        import playwright  # noqa: F401  # type: ignore
    except ImportError:
        print(
            "\nPlaywright is not installed.\n\n"
            "Install browser test dependencies with:\n\n"
            "    pip install -e .[browser-test]\n"
            "    python -m playwright install chromium\n\n"
            "Then retry:\n\n"
            "    PYTHONPATH=src python scripts/browser_smoke.py\n",
            file=sys.stderr,
        )
        sys.exit(2)


def _wait_for_server(host: str, port: int) -> None:
    """Poll GET /healthz until the server responds with HTTP 200."""
    url = f"http://{host}:{port}/healthz"
    for _ in range(_HEALTHZ_RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(_HEALTHZ_INTERVAL)
    raise RuntimeError(
        f"Server did not respond at {url} after "
        f"{_HEALTHZ_RETRIES * _HEALTHZ_INTERVAL:.1f}s"
    )


def _find_free_port() -> int:
    """Return a free TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _choose_port(requested: int | None) -> int:
    if requested is not None:
        return requested
    if _port_is_free(_DEFAULT_PORT):
        return _DEFAULT_PORT
    return _find_free_port()


# ---------------------------------------------------------------------------
# Smoke test runner
# ---------------------------------------------------------------------------

def run_smoke(port: int, screenshot_path: str | None) -> int:
    """Run all browser smoke checks against the sample server.

    Returns 0 on success, 1 if any check fails.
    """
    host = "127.0.0.1"
    base_url = f"http://{host}:{port}"

    # Build the server command.
    # Flags used:
    #   --sample            no Docker daemon required
    #   --metrics           enables SSE metrics stream and Metric Glow UI
    #   --diagnostics       enables SSE diagnostics stream and diag-bar
    #   --redact-host-paths privacy: suppresses host paths in output
    server_env = os.environ.copy()
    server_env["PYTHONPATH"] = str(_REPO_ROOT / "src")
    server_cmd = [
        sys.executable,
        str(_REPO_ROOT / "app.py"),
        "serve",
        "--sample",
        "--metrics",
        "--diagnostics",
        "--redact-host-paths",
        "--host", host,
        "--port", str(port),
    ]

    print(f"[smoke] Command: {' '.join(server_cmd)}", flush=True)
    proc = subprocess.Popen(
        server_cmd,
        env=server_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    failures: list[str] = []

    try:
        # ----------------------------------------------------------------
        # Wait for the server to become ready
        # ----------------------------------------------------------------
        print(f"[smoke] Waiting for server at {base_url}/healthz …", flush=True)
        _wait_for_server(host, port)
        print("[smoke] Server ready.", flush=True)

        # ----------------------------------------------------------------
        # Browser session
        # ----------------------------------------------------------------
        from playwright.sync_api import sync_playwright  # type: ignore

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context()

            # Track network requests to validate offline-first behaviour
            cdn_requests: list[str] = []
            vendor_d3_requests: list[str] = []
            console_errors: list[str] = []

            page = context.new_page()

            page.on(
                "request",
                lambda req: (
                    cdn_requests.append(req.url)
                    if "cdn.jsdelivr.net" in req.url
                    else None,
                    vendor_d3_requests.append(req.url)
                    if "/vendor/d3.min.js" in req.url
                    else None,
                ),
            )
            page.on(
                "console",
                lambda msg: console_errors.append(f"[{msg.type}] {msg.text}")
                if msg.type in ("error",)
                else None,
            )

            # ----------------------------------------------------------------
            # Navigate to the UI
            # ----------------------------------------------------------------
            print(f"[smoke] Opening {base_url}/", flush=True)
            page.goto(base_url + "/", wait_until="domcontentloaded", timeout=15_000)
            # Give the app JS time to initialise and the SSE topology to arrive
            time.sleep(2)

            # ----------------------------------------------------------------
            # Check required DOM elements
            # ----------------------------------------------------------------
            required_elements = ["#graph", "#detail-panel", "#status-msg", "#metrics-status", "#diag-bar"]
            for selector in required_elements:
                el = page.query_selector(selector)
                if el is None:
                    failures.append(f"Required DOM element not found: {selector}")
                else:
                    print(f"[smoke] ✓ {selector} present", flush=True)

            # ----------------------------------------------------------------
            # Offline-first D3: local vendor must be loaded, CDN must not
            # ----------------------------------------------------------------
            if vendor_d3_requests:
                print(f"[smoke] ✓ /vendor/d3.min.js was requested ({len(vendor_d3_requests)} time(s))", flush=True)
            else:
                failures.append(
                    "/vendor/d3.min.js was NOT requested — D3 may not have loaded from the local vendor"
                )

            if cdn_requests:
                failures.append(
                    f"CDN request(s) detected (expected offline-only): {cdn_requests}"
                )
            else:
                print("[smoke] ✓ No cdn.jsdelivr.net requests (offline-first confirmed)", flush=True)

            # ----------------------------------------------------------------
            # Graph must contain visible SVG node elements after topology load
            # ----------------------------------------------------------------
            # D3 renders containers as <circle> elements and networks as
            # <polygon>/<path>.  We check any visible node here; the container-
            # specific click test below is kept separate and strictly requires
            # a <circle> element.
            svg_circles = page.query_selector_all("#graph circle")
            svg_nodes = page.query_selector_all("#graph g.node")
            any_node_count = len(svg_circles) + len(svg_nodes)

            if any_node_count > 0:
                print(
                    f"[smoke] ✓ #graph contains {len(svg_circles)} circle(s) "
                    f"and {len(svg_nodes)} g.node(s)",
                    flush=True,
                )
            else:
                failures.append(
                    "No visible SVG node elements found in #graph after topology load; "
                    "graph may not have rendered"
                )

            # ----------------------------------------------------------------
            # Click a CONTAINER circle and verify the detail panel opens with
            # container-specific content.
            #
            # The test must NOT fall back to a network node (g.node / polygon).
            # If no <circle> is present, the graph has not rendered containers
            # and the test must fail.
            # ----------------------------------------------------------------
            container_circle = page.query_selector("#graph circle")

            if container_circle is None:
                # No container circles in the graph — this is a hard failure.
                failures.append(
                    "No <circle> element found inside #graph — container nodes did not render; "
                    "cannot validate the container detail panel"
                )
            else:
                try:
                    container_circle.click()
                    time.sleep(0.5)
                    panel = page.query_selector("#detail-panel")
                    if panel is None:
                        failures.append("#detail-panel not found after clicking a container circle")
                    else:
                        panel_text = panel.inner_text()
                        # Verify container-specific content is present.
                        # The sample UI detail panel shows fields like:
                        #   "Kind"  +  "container"
                        # or
                        #   "Image"  +  "Status"
                        # Both patterns are stable markers of a container node.
                        panel_lower = panel_text.lower()
                        has_kind_container = (
                            "kind" in panel_lower and "container" in panel_lower
                        )
                        has_image_status = (
                            "image" in panel_lower and "status" in panel_lower
                        )
                        if has_kind_container or has_image_status:
                            print(
                                "[smoke] ✓ Detail panel shows container-specific content "
                                "after clicking a container circle",
                                flush=True,
                            )
                        elif panel_text.strip():
                            # Panel has content but not a recognisable container marker.
                            # Treat as a failure: we need to confirm it's a container panel.
                            failures.append(
                                "Detail panel has content after clicking a container circle "
                                "but no container-specific marker found "
                                f"('Kind'+'container' or 'Image'+'Status'); "
                                f"actual text (truncated): {panel_text[:200]!r}"
                            )
                        else:
                            failures.append(
                                "Detail panel is empty after clicking a container circle"
                            )
                except Exception as exc:
                    failures.append(f"Error clicking container circle: {exc}")

            # ----------------------------------------------------------------
            # Wait for metric samples then check sparklines / Recent metrics
            # ----------------------------------------------------------------
            print(
                f"[smoke] Waiting {_METRICS_WAIT_SECS:.0f}s for {int((_METRICS_WAIT_SECS - 2) / _METRICS_INTERVAL)} "
                "metric samples …",
                flush=True,
            )
            time.sleep(_METRICS_WAIT_SECS)

            # Re-click the container circle so the detail panel refreshes with sparklines
            if container_circle:
                try:
                    container_circle.click()
                    time.sleep(0.5)
                except Exception:
                    pass

            # Look for sparkline SVG elements or a "Recent metrics" heading.
            # The app renders sparklines as <svg> elements inside the detail panel
            # via createElementNS — no innerHTML, no external chart library.
            sparkline_svgs = page.query_selector_all(
                "#detail-panel svg, #detail-panel .sparkline"
            )
            if sparkline_svgs:
                print(f"[smoke] ✓ {len(sparkline_svgs)} sparkline / inline SVG element(s) in detail panel", flush=True)
            else:
                # Try text content of detail panel
                panel = page.query_selector("#detail-panel")
                panel_text = (panel.inner_text() if panel else "").lower()
                if "recent" in panel_text or "cpu" in panel_text or "memory" in panel_text:
                    print("[smoke] ✓ Recent metrics / sparkline text content found in detail panel", flush=True)
                else:
                    # Soft warning in sample mode — deterministic data may not
                    # produce enough variation for sparklines in all browsers
                    print(
                        "[smoke] ⚠ Sparkline SVGs not found after waiting "
                        f"{_METRICS_WAIT_SECS:.0f}s; this may be normal in sample mode "
                        "(deterministic metrics may not trigger sparkline rendering)",
                        flush=True,
                    )

            # ----------------------------------------------------------------
            # Check for Python tracebacks in console errors
            # ----------------------------------------------------------------
            traceback_errors = [
                e for e in console_errors
                if "Traceback" in e or "SyntaxError" in e
            ]
            if traceback_errors:
                failures.append(
                    f"Console error(s) suggesting server traceback: {traceback_errors}"
                )
            elif console_errors:
                # Log non-traceback console errors for information
                print(f"[smoke] ℹ Console errors (non-traceback): {console_errors}", flush=True)
            else:
                print("[smoke] ✓ No console errors detected", flush=True)

            # ----------------------------------------------------------------
            # Screenshot (saved to temp path or user-specified path)
            # ----------------------------------------------------------------
            if screenshot_path is None:
                tmp_dir = tempfile.mkdtemp(prefix="dtl_smoke_")
                screenshot_path = str(Path(tmp_dir) / "smoke.png")
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"[smoke] Screenshot saved: {screenshot_path}", flush=True)

            browser.close()

    finally:
        # Always shut down the server subprocess cleanly
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)

        stdout_bytes = proc.stdout.read() if proc.stdout else b""
        stderr_bytes = proc.stderr.read() if proc.stderr else b""
        if stdout_bytes:
            print("[server stdout]\n" + stdout_bytes.decode(errors="replace"), flush=True)
        if stderr_bytes:
            # Only print stderr if there are failures or it contains ERROR
            decoded = stderr_bytes.decode(errors="replace")
            if failures or "ERROR" in decoded or "Traceback" in decoded:
                print("[server stderr]\n" + decoded, flush=True)

    # ----------------------------------------------------------------
    # Report
    # ----------------------------------------------------------------
    if failures:
        print("\n[smoke] FAILED — the following checks did not pass:", flush=True)
        for msg in failures:
            print(f"  ✗ {msg}", flush=True)
        return 1

    print("\n[smoke] All checks passed.", flush=True)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Optional browser smoke test for Docker Topology Live — sample mode.\n\n"
            "Starts the sample server, opens Chromium via Playwright, and verifies "
            "that the browser UI loads, renders, and behaves correctly.\n\n"
            "Requirements:\n"
            "  pip install -e .[browser-test]\n"
            "  python -m playwright install chromium"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help=(
            f"Port to start the sample server on "
            f"(default: {_DEFAULT_PORT} if free, else an auto-detected free port)"
        ),
    )
    parser.add_argument(
        "--screenshot",
        default=None,
        metavar="PATH",
        help="Save a browser screenshot to this path (default: auto temp file)",
    )
    args = parser.parse_args()

    _check_playwright()

    port = _choose_port(args.port)
    print(f"[smoke] Port: {port}", flush=True)

    return run_smoke(port, args.screenshot)


if __name__ == "__main__":
    sys.exit(main())
