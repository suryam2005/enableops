# main.py - Working EnableBot for Railway
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import asyncio
import logging
import time
import json
import hmac
import hashlib
from datetime import datetime
from typing import Dict, Optional, List
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="EnableBot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
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

# Slack HTTP client
slack_client = None
if SLACK_BOT_TOKEN:
    import httpx
    slack_client = httpx.AsyncClient(
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        timeout=30.0
    )
    logger.info("✅ Slack HTTP client initialized")

# In-memory storage (replace with database later)
chat_memory = {}
typing_tasks = {}

# Pydantic models
class SlackEvent(BaseModel):
    type: str
    user: Optional[str] = None
    text: Optional[str] = None
    channel: Optional[str] = None
    ts: Optional[str] = None
    bot_id: Optional[str] = None
    thread_ts: Optional[str] = None

class SlackChallenge(BaseModel):
    token: str
    challenge: str
    type: str

class SlackEventWrapper(BaseModel):
    token: Optional[str] = None
    team_id: Optional[str] = None
    api_app_id: Optional[str] = None
    event: Optional[SlackEvent] = None
    type: str
    event_id: Optional[str] = None
    event_time: Optional[int] = None
    challenge: Optional[str] = None

class EnableBotAI:
    def __init__(self):
        self.system_prompt = """You are EnableOps Assistant, a helpful internal AI assistant.

You help employees with topics such as HR, IT, onboarding, tool access, compliance, internal policies, and general support.

Key behaviors:
- Be professional, friendly, and helpful
- Keep responses concise but informative (under 500 words)
- If you don't know something, admit it and offer to help find the answer
- Always respond in plain text without markdown formatting
- Focus on being practical and actionable in your advice

You are designed to help with workplace questions and provide support for common business needs."""

    async def process_message(self, user_id: str, message: str) -> str:
        """Process message and generate AI response"""
        try:
            if not openai_client:
                return "I'm sorry, but I'm not able to access my AI capabilities right now. Please try again later or contact your IT support."

            # Get conversation history
            history = chat_memory.get(user_id, [])
            
            # Add current message to history
            history.append({"role": "user", "content": message})
            
            # Keep only last 10 messages to avoid token limits
            if len(history) > 20:
                history = history[-20:]
            
            # Build messages for OpenAI
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(history[-10:])  # Last 5 exchanges
            
            # Generate response
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            
            # Add AI response to history
            history.append({"role": "assistant", "content": ai_response})
            chat_memory[user_id] = history
            
            return ai_response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return "I encountered an error while processing your request. Please try again, and if the problem persists, contact your IT support team."

class SlackAPI:
    def __init__(self):
        self.base_url = "https://slack.com/api"
    
    async def send_message(self, channel: str, text: str, thread_ts: str = None) -> bool:
        """Send message to Slack channel"""
        if not slack_client:
            logger.error("Slack client not initialized")
            return False
        
        try:
            payload = {
                "channel": channel,
                "text": text
            }
            if thread_ts:
                payload["thread_ts"] = thread_ts
            
            response = await slack_client.post(
                f"{self.base_url}/chat.postMessage",
                json=payload
            )
            
            result = response.json()
            if result.get("ok"):
                logger.info(f"✅ Message sent to {channel}")
                return True
            else:
                logger.error(f"❌ Slack API error: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Slack message: {e}")
            return False
    
    async def update_message(self, channel: str, ts: str, text: str) -> bool:
        """Update existing message"""
        if not slack_client:
            return False
        
        try:
            response = await slack_client.post(
                f"{self.base_url}/chat.update",
                json={
                    "channel": channel,
                    "ts": ts,
                    "text": text
                }
            )
            
            result = response.json()
            return result.get("ok", False)
            
        except Exception as e:
            logger.error(f"Error updating message: {e}")
            return False

class TypingIndicator:
    def __init__(self, slack_api: SlackAPI, channel: str):
        self.slack_api = slack_api
        self.channel = channel
        self.message_ts = None
        self.is_active = False
    
    async def start(self):
        """Start typing indicator"""
        try:
            # Send initial thinking message
            response = await slack_client.post(
                "https://slack.com/api/chat.postMessage",
                json={
                    "channel": self.channel,
                    "text": "🤔 Thinking..."
                }
            )
            
            result = response.json()
            if result.get("ok"):
                self.message_ts = result["ts"]
                self.is_active = True
                
                # Update after 1 second
                await asyncio.sleep(1)
                if self.is_active:
                    await self.slack_api.update_message(
                        self.channel, 
                        self.message_ts, 
                        "⚡ Processing your request..."
                    )
                
        except Exception as e:
            logger.error(f"Error starting typing indicator: {e}")
    
    async def stop_and_respond(self, final_message: str):
        """Replace typing indicator with final response"""
        self.is_active = False
        try:
            if self.message_ts:
                await self.slack_api.update_message(
                    self.channel,
                    self.message_ts,
                    final_message
                )
            else:
                await self.slack_api.send_message(self.channel, final_message)
        except Exception as e:
            logger.error(f"Error updating final message: {e}")
            # Fallback: send new message
            await self.slack_api.send_message(self.channel, final_message)

# Initialize components
ai_agent = EnableBotAI()
slack_api = SlackAPI()

def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature"""
    if not SLACK_SIGNING_SECRET:
        return True  # Skip verification if no secret set
    
    try:
        request_hash = f"v0:{timestamp}:{body.decode()}"
        expected_signature = "v0=" + hmac.new(
            SLACK_SIGNING_SECRET.encode(),
            request_hash.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        logger.error(f"Error verifying signature: {e}")
        return False

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "EnableBot API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": bool(openai_client),
            "slack": bool(slack_client)
        },
        "endpoints": {
            "slack_events": "POST /slack/events",
            "health": "GET /health",
            "test": "POST /test-ai"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": bool(openai_client),
            "slack": bool(slack_client)
        },
        "memory": {
            "active_conversations": len(chat_memory),
            "typing_indicators": len(typing_tasks)
        }
    }

@app.post("/slack/events")
async def handle_slack_events(request: Request):
    """Handle Slack events via HTTP webhooks"""
    try:
        # Get request body and headers
        body = await request.body()
        headers = request.headers
        
        # Parse request first
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Handle URL verification FIRST (before signature check)
        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            logger.info(f"URL verification challenge: {challenge}")
            return JSONResponse({"challenge": challenge})
        
        # Verify signature for other requests
        if SLACK_SIGNING_SECRET:
            timestamp = headers.get("x-slack-request-timestamp")
            signature = headers.get("x-slack-signature")
            
            if not verify_slack_signature(body, timestamp, signature):
                raise HTTPException(status_code=401, detail="Invalid signature")
        
@app.post("/slack/events")
async def handle_slack_events(request: Request):
    """Handle Slack events via HTTP webhooks"""
    try:
        # Get request body and headers
        body = await request.body()
        headers = request.headers
        
        # Parse request first
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Log all incoming requests for debugging
        logger.info(f"📩 Received Slack event: {data.get('type', 'unknown')}")
        
        # Handle URL verification FIRST (before signature check)
        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            logger.info(f"URL verification challenge: {challenge}")
            return JSONResponse({"challenge": challenge})
        
        # Verify signature for other requests
        if SLACK_SIGNING_SECRET:
            timestamp = headers.get("x-slack-request-timestamp")
            signature = headers.get("x-slack-signature")
            
            if not verify_slack_signature(body, timestamp, signature):
                logger.error("❌ Invalid Slack signature")
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Handle events
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            event_type = event.get("type", "unknown")
            channel_type = event.get("channel_type", "unknown")
            
            logger.info(f"📨 Event: {event_type}, Channel type: {channel_type}, User: {event.get('user', 'unknown')}")
            
            # Skip bot messages and file shares
            if (event.get("bot_id") or 
                event.get("subtype") in ["bot_message", "file_share", "message_changed"] or
                event.get("thread_ts")):
                logger.info("⏭️ Skipping bot/system message")
                return JSONResponse({"status": "ignored"})
            
            # Handle both channel messages and DMs
            if event_type == "message":
                channel = event.get("channel")
                user = event.get("user")
                text = event.get("text", "").strip()
                
                logger.info(f"📝 Message in {channel_type}: '{text[:50]}...' from {user} in {channel}")
                
                if not all([channel, user, text]):
                    logger.warning(f"⚠️ Missing required fields: channel={bool(channel)}, user={bool(user)}, text={bool(text)}")
                    return JSONResponse({"status": "ignored"})
                
                # Process message asynchronously
                asyncio.create_task(process_slack_message(channel, user, text))
                logger.info("🚀 Message queued for processing")
            
            # Handle app mentions
            elif event_type == "app_mention":
                channel = event.get("channel")
                user = event.get("user")
                text = event.get("text", "").strip()
                
                logger.info(f"📢 App mention: '{text[:50]}...' from {user} in {channel}")
                
                if all([channel, user, text]):
                    asyncio.create_task(process_slack_message(channel, user, text))
                    logger.info("🚀 Mention queued for processing")
        
        return JSONResponse({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def process_slack_message(channel: str, user: str, text: str):
    """Process Slack message with typing indicator"""
    try:
        # Start typing indicator
        typing = TypingIndicator(slack_api, channel)
        typing_tasks[f"{channel}_{user}"] = typing
        
        await typing.start()
        
        # Generate AI response
        ai_response = await ai_agent.process_message(user, text)
        
        # Send final response
        await typing.stop_and_respond(ai_response)
        
        # Clean up
        if f"{channel}_{user}" in typing_tasks:
            del typing_tasks[f"{channel}_{user}"]
        
        logger.info(f"✅ Processed message from {user} in {channel}")
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        # Send error message
        await slack_api.send_message(
            channel, 
            "I'm sorry, I encountered an error processing your message. Please try again."
        )

@app.post("/test-ai")
async def test_ai(message: str, user_id: str = "test_user"):
    """Test AI functionality directly"""
    try:
        if not openai_client:
            raise HTTPException(
                status_code=503, 
                detail="OpenAI service not available. Please check API key."
            )
        
        response = await ai_agent.process_message(user_id, message)
        return {
            "user_input": message,
            "ai_response": response,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/debug")
async def debug_info():
    """Debug endpoint"""
    return {
        "environment": {
            "openai_key_set": bool(OPENAI_API_KEY),
            "slack_token_set": bool(SLACK_BOT_TOKEN),
            "slack_secret_set": bool(SLACK_SIGNING_SECRET)
        },
        "services": {
            "openai_client": bool(openai_client),
            "slack_client": bool(slack_client)
        },
        "memory": {
            "chat_sessions": len(chat_memory),
            "active_typing": len(typing_tasks)
        }
    }

@app.delete("/reset")
async def reset_memory():
    """Reset chat memory (for testing)"""
    global chat_memory, typing_tasks
    chat_memory.clear()
    typing_tasks.clear()
    return {"status": "memory_reset", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting EnableBot on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)