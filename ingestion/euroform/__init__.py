"""EuroForm - High-performance Formex 4 XML to structured JSON/dicts converter.

Includes modular parsing library, CLI, and FastAPI web service.
"""
from __future__ import annotations

from .api.app import app, create_app
from .nesting import group_points
from .parser import FormexParser, formex_to_json, formex_to_text, parse_formex
from .render import render_block, render_blocks, render_text
from .schema import build_schema

__version__ = "0.1.0"

__all__ = [
    "FormexParser",
    "parse_formex",
    "formex_to_json",
    "formex_to_text",
    "render_text",
    "render_block",
    "render_blocks",
    "group_points",
    "build_schema",
    "create_app",
    "app",
    "__version__",
]
