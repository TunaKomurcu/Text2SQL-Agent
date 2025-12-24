"""
API Package - FastAPI Routes and WebSocket Handlers
Contains REST endpoints and WebSocket connections for the Text2SQL system.
"""

from .main import app
from .routes import router

__all__ = ['app', 'router']
