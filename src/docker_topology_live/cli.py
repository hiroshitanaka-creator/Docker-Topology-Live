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
    try:
        topo = scan_live()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if getattr(args, "sample_on_error", False):
            print("Falling back to sample data.", file=sys.stderr)
            topo = build_sample()
        else:
            return 1
    _write_output(topo.to_dict(), getattr(args, "output", None))
    return 0


def _cmd_sample(args: argparse.Namespace) -> int:
    topo = build_sample()
    _write_output(topo.to_dict(), getattr(args, "output", None))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    serve(
        host=args.host,
        port=args.port,
        use_sample=args.sample,
        allow_cors=getattr(args, "allow_cors", False),
    )
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
    p_scan.set_defaults(func=_cmd_scan)

    # sample
    p_sample = sub.add_parser("sample", help="Output sample topology (no Docker needed)")
    p_sample.add_argument("-o", "--output", metavar="FILE", help="Write JSON to FILE")
    p_sample.set_defaults(func=_cmd_sample)

    # serve
    p_serve = sub.add_parser(
        "serve",
        help="Start local HTTP server with live Docker topology and SSE stream",
        description=(
            "Start the Docker Topology Live HTTP server.\n\n"
            "Endpoints\n"
            "---------\n"
            "  GET /             Browser UI (force-directed graph)\n"
            "  GET /api/topology Full topology JSON snapshot\n"
            "  GET /api/stats    Summary statistics\n"
            "  GET /api/events   Server-Sent Events live stream\n"
            "                    (topology + docker-event + heartbeat)\n"
            "  GET /healthz      Health check\n\n"
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
