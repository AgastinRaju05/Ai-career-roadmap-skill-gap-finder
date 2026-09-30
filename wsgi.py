"""Production entry point for WSGI servers (e.g. gunicorn).

Usage:
    gunicorn wsgi:app
"""
import os
import sys

from app import create_app

if not os.environ.get("SECRET_KEY"):
    sys.exit(
        "SECRET_KEY environment variable is not set. Set a persistent, "
        "random SECRET_KEY before starting the app in production."
    )

app = create_app()
