"""
SPA front-end router.

Serves the static frontend bundle from app/web/static and provides
the single-page-application entrypoint for any non-API route.
"""
import os

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter(tags=["frontend"])

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_STATIC_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, "..", "web", "static"))
_INDEX_FILE = os.path.join(_STATIC_DIR, "index.html")

if os.path.isdir(_STATIC_DIR):
    router.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@router.get("/", include_in_schema=False)
def serve_spa_root() -> FileResponse:
    if not os.path.isfile(_INDEX_FILE):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": "Frontend entrypoint is not available."},
        )
    return FileResponse(_INDEX_FILE)


@router.get("/{full_path:path}", include_in_schema=False)
def serve_spa_catch_all(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": "Resource not found."},
        )

    candidate = os.path.abspath(os.path.join(_STATIC_DIR, full_path))
    if candidate.startswith(_STATIC_DIR) and os.path.isfile(candidate):
        return FileResponse(candidate)

    if not os.path.isfile(_INDEX_FILE):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": "Frontend entrypoint is not available."},
        )
    return FileResponse(_INDEX_FILE)
