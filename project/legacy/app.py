"""Compatibility entrypoint. No camera threads or external calls run on import."""
from surveillance.api import create_app

app = create_app()
