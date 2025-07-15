# main.py - Complete EnableBot with OAuth for Slack Marketplace
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
import os
import asyncio
import logging
import time
import json
import hmac
import hashlib
import secrets
import urllib.parse
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
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# OAuth environment variables
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://enableops-backend.madrasco.space")

# Initialize OpenAI client
openai_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("✅ OpenAI client initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize OpenAI: {e}")

# Initialize Supabase
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client, Client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Supabase client initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Supabase: {e}")

# Global variables
chat_memory = {}
typing_tasks = {}
oauth_states = {}  # For OAuth state management

# Initialize HTTP client
import httpx
slack_client = None

# Pydantic models
class SlackEvent(BaseModel):
    type: str
    user: Optional[str] = None
    text: Optional[str] = None
    channel: Optional[str] = None
    ts: Optional[str] = None
    bot_id: Optional[str] = None
    thread_ts: Optional[str] = None

class TenantManager:
    """Manage multiple tenant installations"""
    
    def __init__(self):
        self.tenants = {}
    
    async def create_tenant(self, team_id: str, team_name: str, access_token: str, 
                           bot_user_id: str, authed_user: dict) -> dict:
        """Create a new tenant from OAuth installation"""
        tenant_data = {
            "team_id": team_id,
            "team_name": team_name,
            "access_token": access_token,
            "bot_user_id": bot_user_id,
            "installed_by": authed_user.get("id"),
            "installer_name": authed_user.get("name"),
            "installed_at": datetime.now().isoformat(),
            "active": True,
            "plan": "free"
        }
        
        # Store in database (Supabase)
        if supabase:
            try:
                result = supabase.table('tenants').upsert(tenant_data).execute()
                logger.info(f"✅ Created tenant for team {team_name} ({team_id})")
                self.tenants[team_id] = tenant_data
                
                # Track installation event
                supabase.table('installation_events').insert({
                    'team_id': team_id,
                    'team_name': team_name,
                    'event_type': 'install',
                    'installed_by': authed_user.get("id"),
                    'installer_name': authed_user.get("name")
                }).execute()
                
                return tenant_data
            except Exception as e:
                logger.error(f"❌ Failed to create tenant: {e}")
                raise
        else:
            # Fallback to in-memory storage
            self.tenants[team_id] = tenant_data
            return tenant_data
    
    async def get_tenant(self, team_id: str) -> Optional[dict]:
        """Get tenant by team ID"""
        if team_id in self.tenants:
            return self.tenants[team_id]
        
        # Try to load from database
        if supabase:
            try:
                result = supabase.table('tenants').select('*').eq('team_id', team_id).eq('active', True).execute()
                if result.data:
                    tenant_data = result.data[0]
                    self.tenants[team_id] = tenant_data
                    return tenant_data
            except Exception as e:
                logger.error(f"Error loading tenant {team_id}: {e}")
        
        return None
    
    async def deactivate_tenant(self, team_id: str):
        """Deactivate tenant (when app is uninstalled)"""
        if supabase:
            try:
                supabase.table('tenants').update({'active': False}).eq('team_id', team_id).execute()
                supabase.table('installation_events').insert({
                    'team_id': team_id,
                    'event_type': 'uninstall'
                }).execute()
                logger.info(f"🗑️ Deactivated tenant {team_id}")
            except Exception as e:
                logger.error(f"Error deactivating tenant: {e}")
        
        if team_id in self.tenants:
            self.tenants[team_id]['active'] = False

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

    async def process_message(self, user_id: str, message: str, tenant_id: str = None) -> str:
        """Process message and generate AI response"""
        try:
            if not openai_client:
                return "I'm sorry, but I'm not able to access my AI capabilities right now. Please try again later or contact your IT support."

            # Create session ID with tenant context
            session_key = f"{tenant_id}_{user_id}" if tenant_id else user_id
            
            # Get conversation history
            history = chat_memory.get(session_key, [])
            
            # Add current message to history
            history.append({"role": "user", "content": message})
            
            # Keep only last 10 messages to avoid token limits
            if len(history) > 20:
                history = history[-20:]
            
            # Build messages for OpenAI
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(history[-10:])
            
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
            chat_memory[session_key] = history
            
            # Track usage if tenant provided
            if tenant_id and supabase:
                try:
                    # Call the usage tracking function
                    supabase.rpc('track_tenant_usage', {
                        'tenant_id_param': tenant_id,
                        'user_id_param': user_id,
                        'message_increment': 1,
                        'ai_increment': 1
                    }).execute()
                except Exception as e:
                    logger.error(f"Failed to track usage: {e}")
            
            return ai_response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return "I encountered an error while processing your request. Please try again, and if the problem persists, contact your IT support team."

class SlackAPI:
    def __init__(self, access_token: str = None):
        self.base_url = "https://slack.com/api"
        self.access_token = access_token
    
    async def send_message(self, channel: str, text: str, thread_ts: str = None) -> bool:
        """Send message to Slack channel"""
        if not self.access_token:
            logger.error("No access token for Slack API")
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "channel": channel,
                    "text": text
                }
                if thread_ts:
                    payload["thread_ts"] = thread_ts
                
                response = await client.post(
                    f"{self.base_url}/chat.postMessage",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.access_token}"}
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
        if not self.access_token:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat.update",
                    json={
                        "channel": channel,
                        "ts": ts,
                        "text": text
                    },
                    headers={"Authorization": f"Bearer {self.access_token}"}
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
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    json={
                        "channel": self.channel,
                        "text": "🤔 Thinking..."
                    },
                    headers={"Authorization": f"Bearer {self.slack_api.access_token}"}
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
            await self.slack_api.send_message(self.channel, final_message)

# Initialize components
ai_agent = EnableBotAI()
tenant_manager = TenantManager()

def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature"""
    if not SLACK_SIGNING_SECRET:
        return True
    
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

# OAuth Installation Endpoints
@app.get("/slack/install")
async def slack_install(state: Optional[str] = None):
    """Initiate Slack OAuth installation"""
    if not SLACK_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Slack client ID not configured")
    
    # Generate random state for CSRF protection
    oauth_state = secrets.token_urlsafe(32)
    oauth_states[oauth_state] = {
        "created_at": datetime.now(),
        "original_state": state
    }
    
    # Clean up old states
    cutoff = datetime.now().timestamp() - 600
    global oauth_states
    oauth_states = {k: v for k, v in oauth_states.items() 
                   if v["created_at"].timestamp() > cutoff}
    
    # Required scopes
    scopes = [
        "chat:write",
        "im:read", 
        "im:write",
        "im:history",
        "users:read"
    ]
    
    # Build OAuth URL
    params = {
        "client_id": SLACK_CLIENT_ID,
        "scope": ",".join(scopes),
        "redirect_uri": f"{APP_BASE_URL}/slack/oauth",
        "state": oauth_state,
        "user_scope": ""
    }
    
    auth_url = f"https://slack.com/oauth/v2/authorize?{urllib.parse.urlencode(params)}"
    
    logger.info(f"🔗 OAuth installation started with state: {oauth_state}")
    return RedirectResponse(auth_url)

@app.get("/slack/oauth")
async def slack_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None)
):
    """Handle OAuth callback from Slack"""
    
    if error:
        logger.error(f"❌ OAuth error: {error}")
        return HTMLResponse(f"""
        <html>
        <head><title>Installation Failed</title></head>
        <body>
            <h1>❌ Installation Failed</h1>
            <p>Error: {error}</p>
            <p>Please try installing again.</p>
        </body>
        </html>
        """, status_code=400)
    
    if state not in oauth_states:
        logger.error(f"❌ Invalid OAuth state: {state}")
        return HTMLResponse("""
        <html>
        <head><title>Invalid Request</title></head>
        <body>
            <h1>❌ Invalid Request</h1>
            <p>The installation request has expired or is invalid.</p>
            <p>Please try installing again.</p>
        </body>
        </html>
        """, status_code=400)
    
    del oauth_states[state]
    
    try:
        # Exchange code for access token
        token_response = await exchange_oauth_code(code)
        
        if not token_response.get("ok"):
            raise Exception(f"OAuth exchange failed: {token_response.get('error')}")
        
        # Extract data
        team_id = token_response["team"]["id"]
        team_name = token_response["team"]["name"]
        access_token = token_response["access_token"]
        bot_user_id = token_response["bot_user_id"]
        authed_user = token_response["authed_user"]
        
        # Create tenant
        tenant_data = await tenant_manager.create_tenant(
            team_id=team_id,
            team_name=team_name,
            access_token=access_token,
            bot_user_id=bot_user_id,
            authed_user=authed_user
        )
        
        logger.info(f"✅ Successfully installed for team: {team_name} ({team_id})")
        
        return HTMLResponse(f"""
        <html>
        <head>
            <title>EnableOps Installed Successfully!</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
                .success {{ color: #28a745; }}
                .info {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .button {{ background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1 class="success">🎉 EnableOps Installed Successfully!</h1>
            <p>EnableOps has been installed to <strong>{team_name}</strong> workspace.</p>
            
            <div class="info">
                <h3>🚀 Getting Started:</h3>
                <ol>
                    <li>Open Slack and find the "EnableOps" app in your Apps section</li>
                    <li>Click on EnableOps and go to the "Messages" tab</li>
                    <li>Send a message like "Hello EnableOps!" to start chatting</li>
                    <li>Ask questions about HR, IT, compliance, or general workplace topics</li>
                </ol>
            </div>
            
            <div class="info">
                <h3>💡 Tips:</h3>
                <ul>
                    <li>EnableOps works in direct messages for privacy</li>
                    <li>It remembers conversation context for natural interactions</li>
                    <li>You can ask follow-up questions and it will understand</li>
                    <li>For support, contact us at support@enableops.com</li>
                </ul>
            </div>
            
            <p><a href="slack://app?team={team_id}&id={token_response.get('app_id', '')}" class="button">Open in Slack</a></p>
            
            <p><small>Installation completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</small></p>
        </body>
        </html>
        """)
        
    except Exception as e:
        logger.error(f"❌ OAuth callback error: {e}")
        return HTMLResponse(f"""
        <html>
        <head><title>Installation Error</title></head>
        <body>
            <h1>❌ Installation Error</h1>
            <p>An error occurred during installation: {str(e)}</p>
            <p>Please try installing again or contact support.</p>
        </body>
        </html>
        """, status_code=500)

async def exchange_oauth_code(code: str) -> dict:
    """Exchange OAuth code for access token"""
    if not SLACK_CLIENT_SECRET:
        raise Exception("Slack client secret not configured")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": f"{APP_BASE_URL}/slack/oauth"
            }
        )
        
        result = response.json()
        logger.info(f"📝 OAuth exchange response: {result}")
        return result

# Main event handler with multi-tenant support
@app.post("/slack/events")
async def handle_slack_events(request: Request):
    """Handle Slack events with multi-tenant support"""
    try:
        logger.info("🎯 SLACK EVENT ENDPOINT HIT!")
        
        body = await request.body()
        headers = request.headers
        
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Handle URL verification
        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            logger.info(f"✅ URL verification challenge: {challenge}")
            return JSONResponse({"challenge": challenge})
        
        # Get team ID for tenant lookup
        team_id = data.get("team_id")
        if not team_id:
            logger.error("❌ No team_id in request")
            raise HTTPException(status_code=400, detail="No team_id provided")
        
        # Get tenant configuration
        tenant = await tenant_manager.get_tenant(team_id)
        if not tenant:
            logger.error(f"❌ Tenant not found for team: {team_id}")
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        if not tenant.get("active", False):
            logger.warning(f"⚠️ Inactive tenant: {team_id}")
            return JSONResponse({"status": "ignored"})
        
        # Handle events
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            event_type = event.get("type", "unknown")
            
            logger.info(f"📨 Event from {tenant['team_name']}: {event_type}")
            
            # Skip bot messages
            if (event.get("bot_id") or 
                event.get("subtype") in ["bot_message", "file_share", "message_changed"] or
                event.get("thread_ts")):
                logger.info("⏭️ Skipping bot/system message")
                return JSONResponse({"status": "ignored"})
            
            # Handle DM messages
            if event_type == "message":
                channel = event.get("channel")
                user = event.get("user")
                text = event.get("text", "").strip()
                
                if not all([channel, user, text]):
                    return JSONResponse({"status": "ignored"})
                
                # Process message with tenant context
                asyncio.create_task(process_tenant_message(tenant, channel, user, text))
                logger.info("🚀 Message queued for processing")
        
        return JSONResponse({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def process_tenant_message(tenant: dict, channel: str, user: str, text: str):
    """Process message with tenant-specific configuration"""
    try:
        # Create tenant-specific Slack API
        slack_api = SlackAPI(tenant['access_token'])
        
        # Start typing indicator
        typing = TypingIndicator(slack_api, channel)
        typing_key = f"{tenant['team_id']}_{channel}_{user}"
        typing_tasks[typing_key] = typing
        
        await typing.start()
        
        # Generate AI response with tenant context
        ai_response = await ai_agent.process_message(user, text, tenant['team_id'])
        
        # Send final response
        await typing.stop_and_respond(ai_response)
        
        # Clean up
        if typing_key in typing_tasks:
            del typing_tasks[typing_key]
        
        logger.info(f"✅ Processed message for {tenant['team_name']} from {user}")
        
    except Exception as e:
        logger.error(f"Error processing tenant message: {e}")
        # Send error message
        slack_api = SlackAPI(tenant['access_token'])
        await slack_api.send_message(
            channel, 
            "I'm sorry, I encountered an error processing your message. Please try again."
        )

# Root endpoint
@app.get("/")
async def root():
    """Enhanced root endpoint"""
    return {
        "message": "EnableOps - AI Workplace Assistant",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": bool(openai_client),
            "supabase": bool(supabase),
            "oauth": bool(SLACK_CLIENT_ID and SLACK_CLIENT_SECRET)
        },
        "installation": {
            "install_url": f"{APP_BASE_URL}/slack/install",
            "support_url": f"{APP_BASE_URL}/support",
            "privacy_url": f"{APP_BASE_URL}/privacy"
        },
        "endpoints": {
            "install": "GET /slack/install",
            "oauth": "GET /slack/oauth", 
            "events": "POST /slack/events",
            "health": "GET /health"
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
            "supabase": bool(supabase),
            "oauth": bool(SLACK_CLIENT_ID and SLACK_CLIENT_SECRET)
        },
        "memory": {
            "active_conversations": len(chat_memory),
            "typing_indicators": len(typing_tasks),
            "active_tenants": len(tenant_manager.tenants)
        }
    }

# Legal and support pages
@app.get("/support")
async def support_page():
    """Support documentation page"""
    return HTMLResponse("""
    <html>
    <head><title>EnableOps Support</title></head>
    <body>
        <h1>EnableOps Support</h1>
        <h2>Getting Started</h2>
        <p>After installation, find EnableOps in your Slack apps and start a direct message conversation.</p>
        
        <h2>Common Questions</h2>
        <ul>
            <li><strong>How do I talk to EnableOps?</strong> Send a direct message to the EnableOps app.</li>
            <li><strong>What can I ask?</strong> HR policies, IT help, compliance questions, and general workplace topics.</li>
            <li><strong>Is it private?</strong> Yes, all conversations are private direct messages.</li>
        </ul>
        
        <h2>Contact Support</h2>
        <p>Email: support@enableops.com</p>
    </body>
    </html>
    """)

@app.get("/privacy")
async def privacy_page():
    """Privacy policy page"""
    return HTMLResponse("""
    <html>
    <head><title>EnableOps Privacy Policy</title></head>
    <body>
        <h1>EnableOps Privacy Policy</h1>
        <h2>Data Collection</h2>
        <p>EnableOps collects only the information necessary to provide AI assistance:</p>
        <ul>
            <li>Slack user IDs (for conversation context)</li>
            <li>Message content (to generate responses)</li>
            <li>Basic workspace information</li>
        </ul>
        
        <h2>Data Usage</h2>
        <ul>
            <li>Messages are processed by OpenAI to generate responses</li>
            <li>Conversation history is stored temporarily for context</li>
            <li>No personal data is shared with third parties</li>
        </ul>
        
        <h2>Contact</h2>
        <p>privacy@enableops.com</p>
    </body>
    </html>
    """)

@app.post("/test-ai")
async def test_ai(message: str, user_id: str = "test_user"):
    """Test AI functionality directly"""
    try:
        if not openai_client:
            raise HTTPException(status_code=503, detail="OpenAI service not available")
        
        response = await ai_agent.process_message(user_id, message)
        return {
            "user_input": message,
            "ai_response": response,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting EnableBot with OAuth support on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)