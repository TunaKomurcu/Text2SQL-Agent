"""
FastAPI Application Initialization
Creates the FastAPI app instance with CORS middleware and static file serving.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Create FastAPI app
app = FastAPI(
    title="Text2SQL API",
    description="Turkish Text-to-SQL conversion API with interactive error handling",
    version="1.0.0"
)

# CORS middleware - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (chat.html and assets)
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_dir = os.path.join(current_dir, "static")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Global session cache for managing user sessions and LLM instances
# Key: session_id (str) -> Value: InteractiveSQLGenerator instance
session_cache = {}

# Import and include routers
from .routes import router
app.include_router(router)
