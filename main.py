# main.py - Complete EnableBot for Railway
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import asyncio
import logging
from datetime import datetime
import time
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from openai import OpenAI
from supabase import create_client, Client
from typing import Dict, Optional
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="EnableBot Test", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN") 
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize clients
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Simple AI chat memory (in-memory for testing)
chat_history: Dict[str, list] = {}

class SimpleAIAgent:
    def __init__(self):
        self.system_prompt = """You are EnableOps Assistant, a helpful internal AI assistant.

You help employees with topics such as HR, IT, onboarding, tool access, compliance, internal policies, and general support.

Key behaviors:
- Be professional, friendly, and helpful
- Keep responses concise but informative
- If you don't know something, admit it and offer to help find the answer
- Always respond in plain text without special formatting

You are currently in test mode, so respond helpfully to any questions."""

    async def process_message(self, user_id: str, message: str) -> str:
        """Process user message and generate AI response"""
        try:
            # Get or create chat history for user
            if user_id not in chat_history:
                chat_history[user_id] = []
            
            # Add user message to history
            chat_history[user_id].append({"role": "user", "content": message})
            
            # Keep only last 10 messages to avoid token limits
            if len(chat_history[user_id]) > 20:  # 10 back-and-forth
                chat_history[user_id] = chat_history[user_id][-20:]
            
            # Generate AI response
            if not openai_client:
                return "Sorry, AI service is not available right now. Please try again later."
            
            # Prepare messages for OpenAI
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(chat_history[user_id][-10:])  # Last 5 exchanges
            
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            
            # Add AI response to history
            chat_history[user_id].append({"role": "assistant", "content": ai_response})
            
            return ai_response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return "I encountered an error processing your request. Please try again."

class TypingIndicator:
    def __init__(self, client, channel):
        self.client = client
        self.channel = channel
        self.typing_message_ts = None
    
    async def start(self):
        """Show typing indicator"""
        try:
            response = await self.client.chat_postMessage(
                channel=self.channel,
                text="🤔 Thinking..."
            )
            self.typing_message_ts = response["ts"]
            
            # Update after 1 second
            await asyncio.sleep(1)
            await self.client.chat_update(
                channel=self.channel,
                ts=self.typing_message_ts,
                text="⚡ Processing your request..."
            )
            
        except Exception as e:
            logger.error(f"Error showing typing indicator: {e}")
    
    async def stop_and_respond(self, final_message: str):
        """Replace typing indicator with final response"""
        try:
            if self.typing_message_ts:
                await self.client.chat_update(
                    channel=self.channel,
                    ts=self.typing_message_ts,
                    text=final_message
                )
            else:
                # Fallback: send new message
                await self.client.chat_postMessage(
                    channel=self.channel,
                    text=final_message
                )
        except Exception as e:
            logger.error(f"Error updating message: {e}")
            # Fallback: send new message
            await self.client.chat_postMessage(
                channel=self.channel,
                text=final_message
            )

class SimpleSocketBot:
    def __init__(self):
        self.ai_agent = SimpleAIAgent()
        self.slack_app = None
        self.socket_handler = None
        self.is_connected = False
        self.message_count = 0
        self.start_time = time.time()
    
    async def initialize(self):
        """Initialize Slack app and Socket Mode"""
        if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
            raise Exception("SLACK_BOT_TOKEN and SLACK_APP_TOKEN are required")
        
        # Create Slack app
        self.slack_app = AsyncApp(token=SLACK_BOT_TOKEN)
        
        # Set up message handler
        @self.slack_app.event("message")
        async def handle_message_events(body, logger, client):
            event = body["event"]
            
            # Skip bot messages, edited messages, and threaded messages
            if (event.get("bot_id") or 
                event.get("subtype") == "bot_message" or
                event.get("subtype") == "message_changed" or
                event.get("thread_ts")):
                return
            
            channel = event["channel"]
            user = event["user"]
            text = event.get("text", "")
            
            # Skip empty messages
            if not text.strip():
                return
            
            self.message_count += 1
            logger.info(f"Processing message #{self.message_count} from user {user}: {text[:50]}...")
            
            # Show typing indicator
            typing = TypingIndicator(client, channel)
            await typing.start()
            
            try:
                # Process with AI
                ai_response = await self.ai_agent.process_message(user, text)
                
                # Send response (replaces typing indicator)
                await typing.stop_and_respond(ai_response)
                
                logger.info(f"✅ Responded to user {user}")
                
            except Exception as e:
                logger.error(f"❌ Error processing message: {e}")
                await typing.stop_and_respond("Sorry, I encountered an error. Please try again.")
        
        # Error handler
        @self.slack_app.error
        async def custom_error_handler(error, body, logger):
            logger.error(f"Slack error: {error}")
        
        # Create Socket Mode handler
        self.socket_handler = AsyncSocketModeHandler(self.slack_app, SLACK_APP_TOKEN)
        
        logger.info("✅ Bot initialized successfully")
    
    async def connect(self):
        """Connect to Slack via Socket Mode"""
        try:
            logger.info("🔌 Connecting to Slack...")
            await self.socket_handler.start_async()
            self.is_connected = True
            logger.info("🚀 Socket Mode connected successfully!")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from Slack"""
        try:
            if self.socket_handler:
                await self.socket_handler.close_async()
            self.is_connected = False
            logger.info("👋 Disconnected from Slack")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
    
    def get_stats(self):
        """Get bot statistics"""
        uptime = time.time() - self.start_time
        return {
            "connected": self.is_connected,
            "messages_processed": self.message_count,
            "uptime_minutes": round(uptime / 60, 2),
            "chat_sessions": len(chat_history)
        }

# Initialize the bot
bot = SimpleSocketBot()

# API Endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "EnableBot Test API",
        "version": "1.0.0", 
        "status": "ready",
        "bot_connected": bot.is_connected,
        "messages_processed": bot.message_count,
        "endpoints": {
            "connect": "POST /connect",
            "disconnect": "POST /disconnect", 
            "status": "GET /status",
            "health": "GET /health"
        }
    }

@app.post("/connect")
async def connect_bot():
    """Connect bot to Slack"""
    try:
        if bot.is_connected:
            return {"status": "already_connected", "message": "Bot is already connected to Slack"}
        
        await bot.initialize()
        success = await bot.connect()
        
        if success:
            return {"status": "success", "message": "Bot connected to Slack successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to connect to Slack")
    
    except Exception as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/disconnect")
async def disconnect_bot():
    """Disconnect bot from Slack"""
    try:
        await bot.disconnect()
        return {"status": "success", "message": "Bot disconnected from Slack"}
    except Exception as e:
        logger.error(f"Disconnection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def get_status():
    """Get bot status and statistics"""
    stats = bot.get_stats()
    return {
        "bot_status": stats,
        "services": {
            "openai": bool(openai_client),
            "supabase": bool(supabase),
            "slack_tokens": bool(SLACK_BOT_TOKEN and SLACK_APP_TOKEN)
        },
        "environment": {
            "has_bot_token": bool(SLACK_BOT_TOKEN),
            "has_app_token": bool(SLACK_APP_TOKEN),
            "has_openai_key": bool(OPENAI_API_KEY)
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy" if bot.is_connected else "disconnected",
        "timestamp": datetime.now().isoformat(),
        "bot_connected": bot.is_connected,
        "messages_processed": bot.message_count,
        "environment_ok": bool(SLACK_BOT_TOKEN and SLACK_APP_TOKEN and OPENAI_API_KEY)
    }

@app.get("/debug/environment")
async def debug_environment():
    """Debug endpoint to check environment variables"""
    return {
        "slack_bot_token_set": bool(SLACK_BOT_TOKEN),
        "slack_app_token_set": bool(SLACK_APP_TOKEN),
        "openai_key_set": bool(OPENAI_API_KEY),
        "supabase_url_set": bool(SUPABASE_URL),
        "supabase_key_set": bool(SUPABASE_KEY),
        "bot_token_prefix": SLACK_BOT_TOKEN[:10] + "..." if SLACK_BOT_TOKEN else "Not set",
        "app_token_prefix": SLACK_APP_TOKEN[:10] + "..." if SLACK_APP_TOKEN else "Not set"
    }

@app.post("/test-ai")
async def test_ai_directly(message: str, user_id: str = "test_user"):
    """Test AI response without Slack (for debugging)"""
    try:
        response = await bot.ai_agent.process_message(user_id, message)
        return {
            "user_message": message,
            "ai_response": response,
            "user_id": user_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Auto-connect on startup if tokens are available"""
    logger.info("🚀 EnableBot Test starting up...")
    
    if SLACK_BOT_TOKEN and SLACK_APP_TOKEN:
        logger.info("Found Slack tokens, attempting auto-connect...")
        try:
            await bot.initialize()
            await bot.connect()
            logger.info("✅ Auto-connected to Slack successfully")
        except Exception as e:
            logger.error(f"❌ Auto-connect failed: {e}")
    else:
        logger.warning("⚠️ Slack tokens not found, manual connection required")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("👋 EnableBot Test shutting down...")
    await bot.disconnect()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        workers=1,  # Socket Mode requires single worker
        loop="asyncio"
    )