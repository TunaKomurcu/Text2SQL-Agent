"""
API Routes - REST Endpoints and WebSocket Handlers
Defines all HTTP and WebSocket endpoints for the Text2SQL system.
"""

import os
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
import asyncio

from core import InteractiveSQLGenerator
from sql import results_to_html

# Create API router
router = APIRouter()

# ==================== REQUEST MODELS ====================
class ChatRequest(BaseModel):
    """Request model for /chat endpoint"""
    question: str
    user_feedback: Optional[Dict] = None
    session_id: Optional[str] = None


# ==================== HELPER FUNCTIONS ====================
def get_session_cache():
    """Get the global session cache from main.py"""
    from .main import session_cache
    return session_cache


def get_or_create_generator(session_id: str) -> InteractiveSQLGenerator:
    """Get existing or create new InteractiveSQLGenerator for session"""
    session_cache = get_session_cache()
    
    if session_id not in session_cache:
        session_cache[session_id] = InteractiveSQLGenerator()
    
    return session_cache[session_id]


# ==================== ROOT ENDPOINT ====================
@router.get("/")
def read_root():
    """Root page - serves chat.html"""
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chat_html_path = os.path.join(current_dir, "static", "chat.html")
    
    if os.path.exists(chat_html_path):
        return FileResponse(chat_html_path)
    else:
        raise HTTPException(
            status_code=404,
            detail=f"chat.html not found at {chat_html_path}. Ensure ./static/chat.html exists."
        )


# ==================== CHAT REST ENDPOINT ====================
@router.post("/chat")
def chat(req: ChatRequest):
    """
    Process a natural language query and return SQL + results
    
    Args:
        req: ChatRequest with question, optional user_feedback, and session_id
    
    Returns:
        JSON response with success status, SQL, HTML results, or error details
    """
    try:
        session_id = req.session_id or "default"
        generator = get_or_create_generator(session_id)
        
        # Generate SQL with feedback handling
        result = generator.generate_with_feedback(req.question, req.user_feedback)
        
        attempts = result.get("attempts", 1)
        
        if result["success"]:
            # Success: return SQL and HTML results
            html = results_to_html(result["columns"], result["rows"])
            return {
                "success": True,
                "sql": result["sql"],
                "html": html,
                "attempts": attempts,
                "session_id": session_id
            }
        else:
            # Error: check if clarification is needed
            if result.get("needs_clarification"):
                return {
                    "success": False,
                    "error": result.get("error", ""),
                    "needs_clarification": True,
                    "clarification_question": result.get("clarification_question", ""),
                    "suggestions": result.get("suggestions", []),
                    "sql": result.get("sql", ""),
                    "attempts": attempts,
                    "session_id": session_id,
                    "error_type": result.get("error_type", "unknown"),
                    "has_hybrid_suggestions": result.get("has_hybrid_suggestions", False)
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", ""),
                    "attempts": attempts,
                    "session_id": session_id
                }
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# ==================== WEBSOCKET ENDPOINT ====================
@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for streaming SQL generation responses
    
    Accepts JSON with:
        - question: str (natural language query)
        - session_id: str (optional, defaults to "default")
    
    Sends JSON messages with:
        - type: "token" | "done" | "error"
        - content_type: "explanation" | "sql" | "results" (for type="token")
        - content: str (message content)
    """
    await websocket.accept()
    
    try:
        # Receive question and session_id
        data = await websocket.receive_json()
        question = data.get("question")
        session_id = data.get("session_id", "default")
        
        if not question:
            await websocket.send_json({
                "type": "error",
                "content": "Question is required"
            })
            return
        
        # Get or create generator for this session
        generator = get_or_create_generator(session_id)
        
        # Generate SQL (non-streaming for now, but sent in chunks)
        result = generator.generate_with_feedback(question, None)
        
        if result["success"]:
            # Send explanation
            await websocket.send_json({
                "type": "token",
                "content_type": "explanation",
                "content": "Sorgunuz başarıyla SQL'e dönüştürüldü. Aşağıda oluşturulan SQL sorgusunu ve sonuçları görebilirsiniz."
            })
            
            # Send SQL in chunks (simulate streaming)
            sql = result["sql"]
            chunk_size = 50
            for i in range(0, len(sql), chunk_size):
                await websocket.send_json({
                    "type": "token",
                    "content_type": "sql",
                    "content": sql[i:i+chunk_size]
                })
                await asyncio.sleep(0.05)  # Small delay for streaming effect
            
            # Send results as HTML table
            html = results_to_html(result["columns"], result["rows"])
            await websocket.send_json({
                "type": "token",
                "content_type": "results",
                "content": html
            })
            
            # Send done signal
            await websocket.send_json({"type": "done"})
        else:
            # Send error message
            error_msg = result.get("error", "Bilinmeyen hata")
            if result.get("needs_clarification"):
                error_msg = result.get("clarification_question", error_msg)
            
            await websocket.send_json({
                "type": "token",
                "content_type": "explanation",
                "content": f"Hata oluştu: {error_msg}"
            })
            await websocket.send_json({"type": "done"})
            
    except WebSocketDisconnect:
        print("WebSocket: Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "content": str(e)
            })
        except:
            pass


# ==================== SESSION MANAGEMENT ====================
@router.delete("/session/{session_id}")
def clear_session(session_id: str):
    """Clear a specific session's cache"""
    session_cache = get_session_cache()
    
    if session_id in session_cache:
        del session_cache[session_id]
        return {"success": True, "message": f"Session '{session_id}' cleared"}
    else:
        return {"success": False, "message": f"Session '{session_id}' not found"}


# ==================== UTILITY ENDPOINTS ====================
@router.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "Text2SQL API is running",
        "version": "1.0.0"
    }


@router.get("/check-chat-html")
def check_chat_html():
    """Check if chat.html exists"""
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chat_html_path = os.path.join(current_dir, "static", "chat.html")
    
    return {
        "exists": os.path.exists(chat_html_path),
        "path": chat_html_path
    }
