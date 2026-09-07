"""Compatibility seam: re-export the pages router as `router`.

The dashboard/recipe form UI lives in pages.py. This module exists so
`app.web.routes` also exposes the same router, satisfying any import
path (`from app.web.pages import router` or `from app.web.routes import
router`) without duplicating logic or templates.
"""
from app.web.pages import router  # noqa: F401
