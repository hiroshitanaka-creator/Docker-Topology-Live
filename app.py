#!/usr/bin/env python3
"""Docker Topology Live – top-level entry point.

Delegates all logic to the ``docker_topology_live`` package.

Quick start
-----------
    pip install -e .                          # install package
    python app.py sample --output out.json   # export sample JSON
    python app.py scan   --output out.json   # export live topology
    python app.py serve  --sample            # browser UI (sample mode)
    python app.py serve                      # browser UI (live Docker)
    python app.py doctor                     # check Docker connectivity

Without installing, set PYTHONPATH:
    PYTHONPATH=src python app.py serve --sample
"""
import sys


def main() -> int:
    try:
        from docker_topology_live.cli import main as _cli_main
    except ImportError:
        print(
            "Package not found. Install it first:\n"
            "    pip install -e .\n"
            "Or run with PYTHONPATH:\n"
            "    PYTHONPATH=src python app.py …",
            file=sys.stderr,
        )
        return 1
    return _cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
