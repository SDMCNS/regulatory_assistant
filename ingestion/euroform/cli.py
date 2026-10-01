"""Command-line interface for Formex conversion and running the API server."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .parser import parse_formex
from .render import render_text
from .schema import build_schema


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    ap = argparse.ArgumentParser(
        prog="euroform",
        description="Turn Formex 4 XML (EU Publications Office) into clean JSON/dicts, or serve via FastAPI.",
    )
    ap.add_argument("input", nargs="?", help="Formex XML file to parse")
    ap.add_argument("-o", "--output", help="Write to file instead of stdout")
    ap.add_argument("--text", action="store_true", help="Emit readable plain text instead of JSON")
    ap.add_argument("--keep-toc", action="store_true", help="Keep table of contents")
    ap.add_argument("--no-metadata", action="store_true", help="Omit metadata block")
    ap.add_argument("--no-nest", action="store_true", help="Do not nest points and lists")
    ap.add_argument("--schema", action="store_true", help="Print the JSON Schema and exit")
    ap.add_argument("--serve", action="store_true", help="Start the FastAPI HTTP server")
    ap.add_argument("--host", default="127.0.0.1", help="Host to bind server to (default: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8000, help="Port to bind server to (default: 8000)")
    ap.add_argument("--reload", action="store_true", help="Enable auto-reload for development server")
    ap.add_argument("--version", action="store_true", help="Show euroform version and exit")
    return ap


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    ap = build_parser()
    a = ap.parse_args(argv)

    if a.version:
        from . import __version__
        sys.stdout.write(f"euroform {__version__}\n")
        return 0

    if a.serve:
        try:
            import uvicorn
            from .api.app import app
        except ImportError as err:
            sys.stderr.write(f"Error starting server: {err}. Please ensure uvicorn and fastapi are installed.\n")
            return 1
        sys.stdout.write(f"Starting EuroForm API server on http://{a.host}:{a.port} (Docs: http://{a.host}:{a.port}/docs)\n")
        uvicorn.run(app, host=a.host, port=a.port, reload=a.reload)
        return 0

    if a.schema:
        out = json.dumps(build_schema(), indent=2, ensure_ascii=False)
    else:
        if not a.input:
            ap.error("Input file required (or use --schema or --serve)")
        doc = parse_formex(
            a.input,
            keep_toc=a.keep_toc,
            include_metadata=not a.no_metadata,
            nest_points=not a.no_nest,
        )
        out = render_text(doc) if a.text else json.dumps(doc, indent=2, ensure_ascii=False)

    if a.output:
        Path(a.output).write_text(out + "\n", encoding="utf-8")
    else:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
