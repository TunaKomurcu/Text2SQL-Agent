"""
SMART TEXT-TO-SQL SERVER - Backwards Compatible Wrapper
====================================================

This file maintains backwards compatibility with the original monolithic Text2SQL_Agent.py
while using the new modular architecture underneath.

NEW MODULAR ARCHITECTURE:
- utils/: GPU detection, database connections, Qdrant client, ML model manager
- search/: Semantic, lexical, keyword, data values, hybrid search
- schema/: FK graph loading, column scoring, path finding, schema building
- sql/: SQL parsing, auto-fixing, execution
- core/: LLM manager, prompt builder, error analyzer, SQL generator
- api/: FastAPI routes and WebSocket handlers

MIGRATION GUIDE:
Old imports still work but point to new modules:
  from Text2SQL_Agent import InteractiveSQLGenerator  # Still works!
  from Text2SQL_Agent import app  # FastAPI app still accessible

New recommended imports:
  from core import InteractiveSQLGenerator
  from api import app

For backward compatibility, this wrapper re-exports all original functions and classes.
"""

# ==================== PRINT CONFIG INFO ====================
from config import settings

print(f"🔍 [CONFIG] SEMANTIC_THRESHOLD: {settings.SEMANTIC_THRESHOLD}")
print(f"🔍 [CONFIG] LEXICAL_THRESHOLD: {settings.LEXICAL_THRESHOLD}")
print(f"🔍 [CONFIG] KEYWORD_THRESHOLD: {settings.KEYWORD_THRESHOLD}")
print(f"🔍 [CONFIG] DATA_VALUES_THRESHOLD: {settings.DATA_VALUES_THRESHOLD}")

# ==================== GPU DETECTION (Re-exported from utils) ====================
from utils import GPU_INFO, DEVICE, detect_gpu_availability

# ==================== DATABASE (Re-exported from utils) ====================
from utils import get_connection, get_qdrant_client

# ==================== MODEL MANAGER (Re-exported from utils) ====================
from utils import ModelManager

# ==================== SEARCH MODULES (Re-exported from search) ====================
from search import (
    semantic_search,
    lexical_search,
    keyword_search,
    data_values_search,
    hybrid_search_with_separate_results,
    select_top_tables_balanced
)

# ==================== SCHEMA MODULES (Re-exported from schema) ====================
from schema import (
    load_fk_graph,
    fetch_all_columns_for_table,
    score_columns_by_relevance_separate,
    find_minimal_connecting_paths,
    build_compact_schema_pool,
    format_compact_schema_prompt_with_keywords
)
# Import normalize_table_name explicitly from builder
from schema.builder import normalize_table_name

# ==================== SQL MODULES (Re-exported from sql) ====================
from sql import (
    extract_sql_from_response,
    auto_fix_sql_identifiers,
    clean_meaningless_where_clauses,
    run_sql,
    results_to_html
)

# ==================== CORE MODULES (Re-exported from core) ====================
from core import (
    get_llm_instance,
    create_fallback_llm,
    prime_static_prompt_once,
    STATIC_PROMPT,
    generate_strict_prompt_dynamic_only,
    ensure_static_session,
    SQLErrorAnalyzer,
    InteractiveSQLGenerator
)

# ==================== API (Re-exported from api) ====================
from api import app, router
from api.routes import ChatRequest, get_or_create_generator

# ==================== BACKWARDS COMPATIBLE SESSION CACHE ====================
# The old code used a global session_cache dict
# The new code has it in api.main, so we re-export it here
from api.main import session_cache

# ==================== TYPE HINTS & IMPORTS ====================
import os
import re
import time
import json
import asyncio
from typing import List, Dict, Set, Tuple, Optional
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

# ==================== MAIN ENTRY POINT ====================
if __name__ == "__main__":
    """
    Run the FastAPI server using Uvicorn
    
    Usage:
        python Text2SQL_Agent.py
    
    Or with Uvicorn directly:
        uvicorn Text2SQL_Agent:app --host 0.0.0.0 --port 8001 --reload
    """
    import uvicorn
    
    print("=" * 70)
    print("🚀 Starting Text2SQL API Server (Modular Architecture)")
    print("=" * 70)
    print(f"📍 Host: {settings.API_HOST}")
    print(f"📍 Port: {settings.API_PORT}")
    print(f"📍 GPU: {GPU_INFO['device_name'] if GPU_INFO['available'] else 'CPU Only'}")
    print(f"📍 Device: {DEVICE.upper()}")
    print("=" * 70)
    print("📖 API Documentation: http://localhost:8001/docs")
    print("🌐 Chat Interface: http://localhost:8001/")
    print("=" * 70)
    
    uvicorn.run(
        "Text2SQL_Agent:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
