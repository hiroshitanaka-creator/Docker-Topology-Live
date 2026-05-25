"""Command-line interface for Docker Topology Live."""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
from typing import Optional

from . import __version__
from .scanner import build_sample, scan_live
from .server import serve


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=level,
        stream=sys.stderr,
    )


def _write_output(data: dict, output: Optional[str]) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if output:
        p = pathlib.Path(output)
        p.write_text(text + "\n", encoding="utf-8")
        print(f"Saved topology → {p}", file=sys.stderr)
    else:
        print(text)


def _cmd_scan(args: argparse.Namespace) -> int:
    redact = getattr(args, "redact_host_paths", False)
    try:
        topo = scan_live(redact_host_paths=redact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if getattr(args, "sample_on_error", False):
            print("Falling back to sample data.", file=sys.stderr)
            topo = build_sample(redact_host_paths=redact)
        else:
            return 1
    _write_output(topo.to_dict(), getattr(args, "output", None))
    return 0


def _cmd_sample(args: argparse.Namespace) -> int:
    redact = getattr(args, "redact_host_paths", False)
    topo = build_sample(redact_host_paths=redact)
    _write_output(topo.to_dict(), getattr(args, "output", None))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    serve(
        host=args.host,
        port=args.port,
        use_sample=args.sample,
        allow_cors=getattr(args, "allow_cors", False),
        enable_metrics=getattr(args, "metrics", False),
        metrics_interval=getattr(args, "metrics_interval", 2.0),
        enable_diagnostics=getattr(args, "diagnostics", False),
        diagnostics_interval=getattr(args, "diagnostics_interval", 5.0),
        redact_host_paths=getattr(args, "redact_host_paths", False),
        enable_prometheus=getattr(args, "prometheus", False),
    )
    return 0


def _cmd_diagnose(args: argparse.Namespace) -> int:
    from .diagnostics import analyze_topology, build_sample_diagnostics
    redact = getattr(args, "redact_host_paths", False)
    try:
        if getattr(args, "sample", False):
            from .scanner import build_sample as _build_sample
            topo = _build_sample(redact_host_paths=redact)
            diag = analyze_topology(topo)
        else:
            topo = scan_live(redact_host_paths=redact)
            metrics = None
            warnings: list = []
            if getattr(args, "include_metrics", False):
                try:
                    from .metrics import collect_live_metrics
                    metrics = collect_live_metrics()
                except Exception as exc:
                    print(f"WARNING: Metrics unavailable: {exc}", file=sys.stderr)
                    warnings.append(
                        "Metrics unavailable for diagnostics; resource rules were skipped."
                    )
            diag = analyze_topology(topo, metrics, warnings=warnings)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _write_output(diag, getattr(args, "output", None))
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:  # noqa: ARG001
    try:
        import docker  # type: ignore
        docker.from_env().ping()
        print("Docker daemon: reachable ✓")
    except ImportError:
        print("ERROR: 'docker' package not installed. Run: pip install docker", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Cannot reach Docker daemon: {exc}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dtl",
        description="Docker Topology Live – scanner and visualiser",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    sub = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = sub.add_parser("scan", help="Scan live Docker daemon and print topology JSON")
    p_scan.add_argument("-o", "--output", metavar="FILE", help="Write JSON to FILE")
    p_scan.add_argument("--sample-on-error", action="store_true",
                        help="Fall back to sample data if Docker is unreachable")
    p_scan.add_argument(
        "--redact-host-paths", action="store_true", default=False,
        dest="redact_host_paths",
        help="Replace bind mount source paths with '[redacted]' in the output",
    )
    p_scan.set_defaults(func=_cmd_scan)

    # sample
    p_sample = sub.add_parser("sample", help="Output sample topology (no Docker needed)")
    p_sample.add_argument("-o", "--output", metavar="FILE", help="Write JSON to FILE")
    p_sample.add_argument(
        "--redact-host-paths", action="store_true", default=False,
        dest="redact_host_paths",
        help="Replace bind mount source paths with '[redacted]' in the output",
    )
    p_sample.set_defaults(func=_cmd_sample)

    # diagnose
    p_diagnose = sub.add_parser(
        "diagnose",
        help="Run local rule-based diagnostics on Docker topology",
        description=(
            "Analyse topology (and optionally metrics) using local rules.\n\n"
            "No external API calls are made.  All analysis is local and read-only.\n\n"
            "Examples:\n"
            "  python app.py diagnose --sample\n"
            "  python app.py diagnose\n"
            "  python app.py diagnose --include-metrics\n"
            "  python app.py diagnose --sample --output diag.json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_diagnose.add_argument("--sample", action="store_true",
                            help="Use sample data instead of live Docker")
    p_diagnose.add_argument("-o", "--output", metavar="FILE", help="Write JSON to FILE")
    p_diagnose.add_argument(
        "--include-metrics",
        action="store_true", default=False, dest="include_metrics",
        help="Include live container metrics in analysis (requires Docker)",
    )
    p_diagnose.add_argument(
        "--format", default="json", choices=["json"],
        help="Output format (default: json)",
    )
    p_diagnose.add_argument(
        "--redact-host-paths", action="store_true", default=False,
        dest="redact_host_paths",
        help="Replace bind mount source paths with '[redacted]' before analysis",
    )
    p_diagnose.set_defaults(func=_cmd_diagnose)

    # serve
    p_serve = sub.add_parser(
        "serve",
        help="Start local HTTP server with live Docker topology and SSE stream",
        description=(
            "Start the Docker Topology Live HTTP server.\n\n"
            "Endpoints\n"
            "---------\n"
            "  GET /                  Browser UI (force-directed graph)\n"
            "  GET /api/topology      Full topology JSON snapshot\n"
            "  GET /api/stats         Summary statistics\n"
            "  GET /api/events        Server-Sent Events live stream\n"
            "                         (topology + docker-event + heartbeat\n"
            "                          + metrics when --metrics is set\n"
            "                          + diagnostics when --diagnostics is set)\n"
            "  GET /api/metrics       Point-in-time container metrics snapshot\n"
            "  GET /api/diagnostics   Point-in-time local diagnostics snapshot\n"
            "  GET /metrics           Prometheus text exposition (only with --prometheus)\n"
            "  GET /healthz           Health check\n\n"
            "Examples:\n"
            "  python app.py serve --sample\n"
            "  python app.py serve --metrics\n"
            "  python app.py serve --sample --diagnostics\n"
            "  python app.py serve --metrics --diagnostics\n"
            "  python app.py serve --metrics --diagnostics --diagnostics-interval 5.0\n"
            "  python app.py serve --sample --prometheus\n"
            "  python app.py serve --metrics --prometheus\n\n"
            "The browser UI connects to /api/events for live updates and falls\n"
            "back to 15-second polling if SSE is unavailable.\n"
            "In --sample mode no Docker daemon is required."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    p_serve.add_argument("--port", "-p", type=int, default=8080, help="Port (default: 8080)")
    p_serve.add_argument("--sample", action="store_true",
                         help="Use sample data instead of live Docker")
    p_serve.add_argument(
        "--allow-cors",
        action="store_true",
        default=False,
        dest="allow_cors",
        help=(
            "Emit Access-Control-Allow-Origin: * on every response. "
            "Off by default — enable only when a separate front-end "
            "dev server needs cross-origin access."
        ),
    )
    p_serve.add_argument(
        "--metrics",
        action="store_true",
        default=False,
        dest="metrics",
        help=(
            "Enable container runtime metrics (CPU/memory/network/block-IO) in "
            "the /api/events SSE stream.  Off by default — metrics collection "
            "calls container.stats() once per running container per interval."
        ),
    )
    p_serve.add_argument(
        "--metrics-interval",
        type=float,
        default=2.0,
        dest="metrics_interval",
        metavar="SECONDS",
        help="Metrics collection interval in seconds (default: 2.0, requires --metrics)",
    )
    p_serve.add_argument(
        "--diagnostics",
        action="store_true",
        default=False,
        dest="diagnostics",
        help=(
            "Enable local rule-based diagnostics in the /api/events SSE stream. "
            "Off by default.  Analysis is local and read-only — no external APIs called."
        ),
    )
    p_serve.add_argument(
        "--diagnostics-interval",
        type=float,
        default=5.0,
        dest="diagnostics_interval",
        metavar="SECONDS",
        help="Diagnostics analysis interval in seconds (default: 5.0, requires --diagnostics)",
    )
    p_serve.add_argument(
        "--redact-host-paths",
        action="store_true",
        default=False,
        dest="redact_host_paths",
        help=(
            "Replace bind mount source paths with '[redacted]' in all topology "
            "documents served (including SSE streams and /api/topology).  "
            "sourceCategory is always included so diagnostics remain effective.  "
            "Off by default."
        ),
    )
    p_serve.add_argument(
        "--prometheus",
        action="store_true",
        default=False,
        dest="prometheus",
        help=(
            "Enable the Prometheus text exposition endpoint at GET /metrics.  "
            "Off by default.  Exposes point-in-time container metrics in "
            "Prometheus format; data source is the same as /api/metrics.  "
            "No raw Docker labels, env vars, or host paths are included.  "
            "No data is persisted or sent to external services."
        ),
    )
    p_serve.set_defaults(func=_cmd_serve)

    # doctor
    p_doctor = sub.add_parser("doctor", help="Check Docker daemon connectivity")
    p_doctor.set_defaults(func=_cmd_doctor)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(getattr(args, "verbose", False))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
