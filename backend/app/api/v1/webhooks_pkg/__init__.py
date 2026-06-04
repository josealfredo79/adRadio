"""
Webhooks package — split from webhooks.py for maintainability.
"""
from app.api.v1.webhooks_pkg.router import router

__all__ = ["router"]
