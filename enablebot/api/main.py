"""
EnableBot AI Service - Multi-Tenant Backend
Production API service for handling Slack events from all workspaces
"""

from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import asyncio
import logging
import json
import hmac
import hashlib
import httpx
import io
from datetime import datetime
from typing import Dict, Optional, List, Any
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="EnableBot AI Service",
    description="Multi-tenant AI backend for Slack workspaces",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# Initialize OpenAI client
openai_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("✅ OpenAI client initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize OpenAI: {e}")

# Pydantic models
class SlackEvent(BaseModel):
    type: str
    user: Optional[str] = None
    text: Optional[str] = None
    channel: Optional[str] = None
    ts: Optional[str] = None
    bot_id: Optional[str] = None
    thread_ts: Optional[str] = None

class SlackEventWrapper(BaseModel):
    token: Optional[str] = None
    team_id: Optional[str] = None
    api_app_id: Optional[str] = None
    event: Optional[SlackEvent] = None
    type: str
    event_id: Optional[str] = None
    event_time: Optional[int] = None
    challenge: Optional[str] = None

class ChatRequest(BaseModel):
    tenant_id: str
    user_id: str
    message: str
    context: Optional[Dict[str, Any]] = None

# API Endpoints
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("🚀 Starting EnableBot AI Service...")
    logger.info("🎉 EnableBot AI Service ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    logger.info("🛑 Shutting down EnableBot AI Service...")
    logger.info("✅ Cleanup completed")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "EnableBot AI Service",
        "version": "3.0.0"
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "EnableBot AI Service is running",
        "version": "3.0.0",
        "status": "healthy"
    }

@app.post("/slack/events")
async def slack_events(request: Request):
    """Handle Slack events from all workspaces"""
    try:
        body = await request.body()
        
        # Parse event data
        try:
            event_data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Handle URL verification challenge
        if event_data.get("type") == "url_verification":
            return {"challenge": event_data.get("challenge")}
        
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/chat")
async def chat_endpoint(chat_request: ChatRequest):
    """Direct chat API endpoint"""
    try:
        response = "Hello! I'm EnableBot. I'm currently in setup mode."
        
        return {
            "response": response,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Failed to process message")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)