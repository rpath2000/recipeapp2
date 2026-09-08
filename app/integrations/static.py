"""Static file serving integration.

Exposes `static_files` (a Starlette StaticFiles app) and `mount_static`,
a helper the shared entrypoint can call to mount static assets at /static.
No filesystem writes and no network I/O occur at import time; StaticFiles
only records the directory path lazily.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

# app/integrations/static.py -> parents[1] == app/
_APP_DIR = Path(__file__).resolve().parents[1]
_STATIC_DIR = _APP_DIR / "web" / "static"

static_files = StaticFiles(directory=str(_STATIC_DIR), check_dir=False)


def mount_static(app: FastAPI, path: str = "/static") -> None:
    """Mount the static files app onto the given FastAPI application.

    Idempotent-friendly: safe to call once during application startup wiring
    in app/main.py. Does not touch any route paths owned by other
    components (mounts only under `/static`).
    """
    app.mount(path, static_files, name="static")


__all__ = ["static_files", "mount_static"]
