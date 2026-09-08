"""Jinja2 template rendering integration.

Configures a single Jinja2Templates instance pointing at app/web/templates/
and exports it as the `templates` seam used by page-rendering components.

No database access and no network I/O occurs at import time.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

# app/integrations/templates.py -> parents[1] == app/
_APP_DIR = Path(__file__).resolve().parents[1]
_TEMPLATES_DIR = _APP_DIR / "web" / "templates"

# Jinja2Templates only configures a loader/environment; it performs no I/O
# beyond directory existence checks handled lazily by Jinja2 at render time.
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

__all__ = ["templates"]
