"""
Package initialization for config.
Imports and exposes Celery app instance so tasks are discovered on Django startup.
"""

from .celery import app as celery_app

__all__ = ('celery_app',)
