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

# Initialize Supabase client
supabase_client = None
supabase_url = os.getenv("SUPABASE_URL")
supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")

if supabase_url and supabase_service_key:
    supabase_client = httpx.AsyncClient(
        base_url=supabase_url,
        headers={
            "apikey": supabase_service_key,
            "Authorization": f"Bearer {supabase_service_key}",
            "Content-Type": "application/json"
        },
        timeout=30.0
    )
    logger.info("✅ Supabase client initialized")

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
        headers = request.headers
        
        # Verify Slack signature (optional but recommended)
        timestamp = headers.get("x-slack-request-timestamp", "")
        signature = headers.get("x-slack-signature", "")
        
        # Parse event data
        try:
            event_data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Handle URL verification challenge
        if event_data.get("type") == "url_verification":
            return {"challenge": event_data.get("challenge")}
        
        # Handle events
        if event_data.get("type") == "event_callback":
            event = event_data.get("event", {})
            team_id = event_data.get("team_id")
            
            # Skip bot messages
            if event.get("bot_id"):
                return {"status": "ignored"}
            
            # Handle direct messages (message.im events)
            if event.get("type") == "message" and event.get("channel_type") == "im":
                # Extract message details
                user_id = event.get("user")
                text = event.get("text", "").strip()
                channel = event.get("channel")
                thread_ts = event.get("thread_ts")
                
                if not user_id or not text or not team_id:
                    return {"status": "ignored"}
                
                # Process message asynchronously
                asyncio.create_task(process_slack_message(
                    team_id, user_id, text, channel, thread_ts
                ))
        
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def process_slack_message(team_id: str, user_id: str, message: str, channel: str, thread_ts: str = None):
    """Process Slack message and respond with AI"""
    try:
        logger.info(f"Processing message from user {user_id} in team {team_id}: {message[:50]}...")
        
        # Get bot token for this team from database
        bot_token = await get_bot_token_for_team(team_id)
        if not bot_token:
            logger.error(f"No bot token found for team {team_id}")
            return
        
        # Send typing indicator
        typing_sent = await send_slack_message(bot_token, channel, "🤔 Thinking...", thread_ts)
        typing_ts = typing_sent.get("ts") if typing_sent else None
        
        # Process message with AI
        response = await ai_assistant.process_message(team_id, user_id, message)
        
        # Send AI response (update typing message if possible)
        if typing_ts:
            await update_slack_message(bot_token, channel, typing_ts, response)
        else:
            await send_slack_message(bot_token, channel, response, thread_ts)
        
        logger.info(f"✅ Responded to user {user_id} in team {team_id}")
        
    except Exception as e:
        logger.error(f"Error processing Slack message: {e}")
        # Send error message
        if bot_token:
            await send_slack_message(
                bot_token, channel, 
                "I'm sorry, I encountered an error processing your request. Please try again later.",
                thread_ts
            )

async def get_bot_token_for_team(team_id: str) -> Optional[str]:
    """Get decrypted bot token for a specific team"""
    try:
        if not supabase_client:
            logger.error("Supabase client not initialized")
            return None
        
        # Get tenant data from Supabase
        response = await supabase_client.get(
            "/rest/v1/tenants",
            params={
                "team_id": f"eq.{team_id}",
                "active": "eq.true"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data:
                tenant_data = data[0]
                # For now, return the access_token directly (it's encrypted)
                # TODO: Implement proper decryption
                encrypted_token = tenant_data.get("access_token")
                if encrypted_token:
                    # For now, assume it's the bot token (you'll need to decrypt this)
                    logger.info(f"Retrieved bot token for team {team_id}")
                    return encrypted_token
        
        logger.warning(f"No bot token found for team {team_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting bot token for team {team_id}: {e}")
        return None

async def get_user_profile(tenant_id: str, slack_user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile from Supabase"""
    try:
        if not supabase_client:
            # Fallback profile
            return {
                "slack_user_id": slack_user_id,
                "full_name": "Team Member",
                "role": "Employee",
                "department": "General",
                "location": "Remote",
                "tool_access": ["Slack"]
            }
        
        response = await supabase_client.get(
            "/rest/v1/user_profiles",
            params={
                "tenant_id": f"eq.{tenant_id}",
                "slack_user_id": f"eq.{slack_user_id}",
                "active": "eq.true"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data:
                return data[0]
        
        # Create default profile for new users
        default_profile = {
            "tenant_id": tenant_id,
            "slack_user_id": slack_user_id,
            "full_name": "Team Member",
            "role": "Employee",
            "department": "General",
            "location": "Remote",
            "tool_access": ["Slack"],
            "active": True
        }
        
        # Try to create the profile
        await supabase_client.post(
            "/rest/v1/user_profiles",
            json=default_profile
        )
        
        return default_profile
        
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        return {
            "slack_user_id": slack_user_id,
            "full_name": "Team Member",
            "role": "Employee",
            "department": "General",
            "location": "Remote",
            "tool_access": ["Slack"]
        }

async def get_tenant_info(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Get tenant information from Supabase"""
    try:
        if not supabase_client:
            return {
                "team_id": tenant_id,
                "team_name": "Your Company",
                "settings": {}
            }
        
        response = await supabase_client.get(
            "/rest/v1/tenants",
            params={
                "team_id": f"eq.{tenant_id}",
                "active": "eq.true"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data:
                return data[0]
        
        return {
            "team_id": tenant_id,
            "team_name": "Your Company",
            "settings": {}
        }
        
    except Exception as e:
        logger.error(f"Error fetching tenant info: {e}")
        return {
            "team_id": tenant_id,
            "team_name": "Your Company",
            "settings": {}
        }

class TenantAwareAI:
    """AI agent with tenant-specific context"""
    
    def __init__(self):
        self.base_prompt = """You are EnableOps Assistant, a helpful internal AI assistant for {company_name}.

You help employees with topics such as HR, IT, onboarding, tool access, compliance, internal policies, and general support.

USER CONTEXT:
- Name: {user_name}
- Role: {user_role}
- Department: {user_department}
- Location: {user_location}

Key behaviors:
- Be professional, friendly, and helpful
- Keep responses concise but informative (under 500 words)
- If you don't know something, admit it and offer to help find the answer
- Always respond in plain text without markdown formatting
- Focus on being practical and actionable in your advice
- Use the employee's name naturally in conversation

You are designed to help with workplace questions and provide support for {company_name} employees."""

    async def process_message(self, tenant_id: str, user_id: str, message: str) -> str:
        """Process message with tenant-aware context"""
        try:
            if not openai_client:
                return "I'm sorry, but I'm not able to access my AI capabilities right now. Please try again later or contact your IT support."

            # Get user profile and tenant info
            user_profile = await get_user_profile(tenant_id, user_id)
            tenant_info = await get_tenant_info(tenant_id)
            
            if not user_profile:
                return "I couldn't find your profile in our system. Please contact your admin to set up your EnableBot access."
            
            # Build personalized system prompt
            system_prompt = self.base_prompt.format(
                company_name=tenant_info.get("team_name", "your company"),
                user_name=user_profile.get("full_name", "Team Member"),
                user_role=user_profile.get("role", "Employee"),
                user_department=user_profile.get("department", "General"),
                user_location=user_profile.get("location", "Remote")
            )
            
            # Build messages for OpenAI
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]
            
            # Generate response
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            return ai_response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return "I encountered an error while processing your request. Please try again, and if the problem persists, contact your IT support team."

# Global AI assistant
ai_assistant = TenantAwareAI()

async def send_slack_message(bot_token: str, channel: str, text: str, thread_ts: str = None) -> Optional[dict]:
    """Send message to Slack using bot token"""
    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "channel": channel,
                "text": text
            }
            if thread_ts:
                payload["thread_ts"] = thread_ts
            
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {bot_token}"},
                json=payload
            )
            
            result = response.json()
            if result.get("ok"):
                return result
            else:
                logger.error(f"Slack API error: {result.get('error')}")
                return None
                
    except Exception as e:
        logger.error(f"Error sending Slack message: {e}")
        return None

async def update_slack_message(bot_token: str, channel: str, ts: str, text: str) -> bool:
    """Update existing Slack message"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/chat.update",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={
                    "channel": channel,
                    "ts": ts,
                    "text": text
                }
            )
            
            result = response.json()
            return result.get("ok", False)
            
    except Exception as e:
        logger.error(f"Error updating Slack message: {e}")
        return False

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