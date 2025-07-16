# main.py - Production-Ready EnableBot AI Service
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
import httpx
from datetime import datetime
from typing import Dict, Optional, List, Any
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="EnableBot AI Service", version="2.0.0")

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
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Initialize OpenAI client
openai_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("✅ OpenAI client initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize OpenAI: {e}")

# Initialize Slack client
slack_client = None
if SLACK_BOT_TOKEN:
    slack_client = httpx.AsyncClient(
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        timeout=30.0
    )
    logger.info("✅ Slack HTTP client initialized")

# Initialize Supabase client
supabase_client = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    supabase_client = httpx.AsyncClient(
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json"
        },
        timeout=30.0
    )
    logger.info("✅ Supabase client initialized")

# In-memory storage for chat sessions
chat_memory = {}
typing_tasks = {}

# Pydantic models
class UserProfile(BaseModel):
    slack_user_id: str
    full_name: str
    role: str
    department: str
    location: str
    tool_access: List[str]
    tenant_id: str

class TenantInfo(BaseModel):
    tenant_id: str
    company_name: str
    settings: Dict[str, Any]

class ChatRequest(BaseModel):
    tenant_id: str
    user_id: str
    message: str
    context: Optional[Dict[str, Any]] = None

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

# Database functions
async def get_user_profile(tenant_id: str, slack_user_id: str) -> Optional[UserProfile]:
    """Get user profile from Supabase"""
    if not supabase_client:
        # Fallback for demo/testing
        return UserProfile(
            slack_user_id=slack_user_id,
            full_name="Demo User",
            role="Employee", 
            department="Engineering",
            location="Remote",
            tool_access=["Slack", "Jira", "GitHub"],
            tenant_id=tenant_id
        )
    
    try:
        response = await supabase_client.get(
            f"{SUPABASE_URL}/rest/v1/user_profiles",
            params={
                "tenant_id": f"eq.{tenant_id}",
                "slack_user_id": f"eq.{slack_user_id}",
                "active": "eq.true"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data:
                user_data = data[0]
                return UserProfile(
                    slack_user_id=user_data["slack_user_id"],
                    full_name=user_data["full_name"],
                    role=user_data["role"],
                    department=user_data["department"],
                    location=user_data["location"],
                    tool_access=user_data["tool_access"] or [],
                    tenant_id=user_data["tenant_id"]
                )
        
        # Fallback profile if not found
        return UserProfile(
            slack_user_id=slack_user_id,
            full_name="New User",
            role="Employee",
            department="General",
            location="Office",
            tool_access=["Slack"],
            tenant_id=tenant_id
        )
        
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        return UserProfile(
            slack_user_id=slack_user_id,
            full_name="Demo User",
            role="Employee",
            department="Engineering", 
            location="Remote",
            tool_access=["Slack"],
            tenant_id=tenant_id
        )

async def get_tenant_info(tenant_id: str) -> Optional[TenantInfo]:
    """Get tenant information from Supabase"""
    if not supabase_client:
        return TenantInfo(
            tenant_id=tenant_id,
            company_name="Demo Company",
            settings={}
        )
    
    try:
        response = await supabase_client.get(
            f"{SUPABASE_URL}/rest/v1/tenants",
            params={
                "team_id": f"eq.{tenant_id}",
                "active": "eq.true"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data:
                tenant_data = data[0]
                return TenantInfo(
                    tenant_id=tenant_data["team_id"],
                    company_name=tenant_data["team_name"],
                    settings=tenant_data.get("settings", {})
                )
        
        return TenantInfo(
            tenant_id=tenant_id,
            company_name="Demo Company",
            settings={}
        )
        
    except Exception as e:
        logger.error(f"Error fetching tenant info: {e}")
        return TenantInfo(
            tenant_id=tenant_id,
            company_name="Demo Company",
            settings={}
        )

async def search_knowledge_base(tenant_id: str, query: str, limit: int = 3) -> List[Dict]:
    """Search tenant's knowledge base"""
    if not supabase_client:
        return [
            {
                "content": "Welcome to your demo company! Here's some sample information about our onboarding process and policies.",
                "similarity": 0.85,
                "metadata": {"source": "demo_docs", "type": "onboarding"}
            }
        ]
    
    try:
        # First try vector search
        query_embedding = await get_embedding(query)
        if query_embedding:
            response = await supabase_client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/search_documents",
                json={
                    "query_embedding": query_embedding,
                    "similarity_threshold": 0.7,
                    "result_limit": limit,
                    "tenant_filter": tenant_id
                }
            )
            
            if response.status_code == 200:
                results = response.json()
                return [
                    {
                        "content": doc.get("content", ""),
                        "similarity": doc.get("similarity", 0),
                        "metadata": doc.get("metadata", {})
                    }
                    for doc in results
                ]
        
        # Fallback to text search
        response = await supabase_client.get(
            f"{SUPABASE_URL}/rest/v1/documents",
            params={
                "content": f"ilike.%{query}%",
                "tenant_id": f"eq.{tenant_id}",
                "limit": limit
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            return [
                {
                    "content": doc.get("content", ""),
                    "similarity": 0.8,
                    "metadata": doc.get("metadata", {})
                }
                for doc in data
            ]
    
    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}")
    
    return []

async def get_embedding(text: str) -> List[float]:
    """Get OpenAI embedding for text"""
    if not openai_client:
        return []
    
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text.strip()
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return []

async def save_chat_message(tenant_id: str, session_id: str, message_type: str, content: str):
    """Save chat message to Supabase"""
    if not supabase_client:
        # Store in memory as fallback
        key = f"{tenant_id}_{session_id}"
        if key not in chat_memory:
            chat_memory[key] = []
        chat_memory[key].append({
            "role": "user" if message_type == "human" else "assistant",
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # Keep only last 20 messages
        chat_memory[key] = chat_memory[key][-20:]
        return
    
    try:
        await supabase_client.post(
            f"{SUPABASE_URL}/rest/v1/chat_memory",
            json={
                "tenant_id": tenant_id,
                "session_id": session_id,
                "message_type": message_type,
                "content": content
            }
        )
    except Exception as e:
        logger.error(f"Error saving chat message: {e}")

async def get_chat_history(tenant_id: str, session_id: str, limit: int = 10) -> List[Dict]:
    """Get chat history from Supabase"""
    if not supabase_client:
        # Fallback to in-memory storage
        key = f"{tenant_id}_{session_id}"
        return chat_memory.get(key, [])[-limit:]
    
    try:
        response = await supabase_client.get(
            f"{SUPABASE_URL}/rest/v1/chat_memory",
            params={
                "tenant_id": f"eq.{tenant_id}",
                "session_id": f"eq.{session_id}",
                "order": "created_at.desc",
                "limit": limit
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            history = []
            for row in reversed(data):
                history.append({
                    "role": "user" if row["message_type"] == "human" else "assistant",
                    "content": row["content"]
                })
            return history
    except Exception as e:
        logger.error(f"Error fetching chat history: {e}")
    
    return []

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
- Tools Access: {user_tools}

COMPANY KNOWLEDGE:
{knowledge_context}

Key behaviors:
- Be professional, friendly, and helpful
- Keep responses concise but informative (under 500 words)
- Reference company-specific information when available
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
            
            # Get conversation history
            session_id = f"{tenant_id}-{user_id}"
            history = await get_chat_history(tenant_id, session_id)
            
            # Search knowledge base for relevant information
            knowledge_results = await search_knowledge_base(tenant_id, message)
            
            # Build knowledge context
            knowledge_context = "No specific company documentation found for this query."
            if knowledge_results:
                knowledge_parts = []
                for kb in knowledge_results:
                    content = kb.get('content', '').replace('\n', ' ')
                    if len(content) > 200:
                        content = content[:200] + "..."
                    knowledge_parts.append(f"- {content}")
                knowledge_context = "\n".join(knowledge_parts)
            
            # Build personalized system prompt
            system_prompt = self.base_prompt.format(
                company_name=tenant_info.company_name if tenant_info else "your company",
                user_name=user_profile.full_name,
                user_role=user_profile.role,
                user_department=user_profile.department,
                user_location=user_profile.location,
                user_tools=", ".join(user_profile.tool_access),
                knowledge_context=knowledge_context
            )
            
            # Build messages for OpenAI
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history[-10:])  # Last 10 messages for context
            messages.append({"role": "user", "content": message})
            
            # Generate response
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            
            # Save conversation
            await save_chat_message(tenant_id, session_id, "human", message)
            await save_chat_message(tenant_id, session_id, "ai", ai_response)
            
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
            if not slack_client:
                return
                
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
ai_agent = TenantAwareAI()
slack_api = SlackAPI()

def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature"""
    if not SLACK_SIGNING_SECRET:
        return True  # Skip verification if no secret provided
    
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

# API Routes

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "EnableBot AI Service",
        "version": "2.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": bool(openai_client),
            "slack": bool(slack_client),
            "supabase": bool(supabase_client)
        },
        "features": [
            "Tenant-aware AI responses",
            "Knowledge base integration",
            "Conversation memory",
            "Slack integration",
            "Fallback support for demo mode"
        ]
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": bool(openai_client),
            "slack": bool(slack_client),
            "supabase": bool(supabase_client)
        },
        "memory": {
            "active_conversations": len(chat_memory),
            "typing_indicators": len(typing_tasks)
        }
    }

@app.post("/chat")
async def chat_endpoint(chat_request: ChatRequest):
    """Main AI chat endpoint for frontend integration"""
    try:
        response = await ai_agent.process_message(
            chat_request.tenant_id,
            chat_request.user_id,
            chat_request.message
        )
        
        return {
            "response": response,
            "tenant_id": chat_request.tenant_id,
            "user_id": chat_request.user_id,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/slack/events")
async def handle_slack_events(request: Request):
    """Handle Slack events via HTTP webhooks"""
    try:
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
        
        # Verify signature
        if SLACK_SIGNING_SECRET:
            timestamp = headers.get("x-slack-request-timestamp")
            signature = headers.get("x-slack-signature")
            
            if timestamp and signature and not verify_slack_signature(body, timestamp, signature):
                logger.error("❌ Invalid Slack signature")
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Handle events
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            
            # Skip bot messages
            if event.get("bot_id") or event.get("subtype"):
                return JSONResponse({"status": "ignored"})
            
            if event.get("type") == "message":
                team_id = data.get("team_id")  # This is our tenant_id
                channel = event.get("channel")
                user = event.get("user")
                text = event.get("text", "").strip()
                
                if all([team_id, channel, user, text]):
                    # Process message asynchronously
                    asyncio.create_task(process_slack_message(team_id, channel, user, text))
        
        return JSONResponse({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def process_slack_message(tenant_id: str, channel: str, user: str, text: str):
    """Process Slack message with tenant context"""
    try:
        # Start typing indicator
        typing = TypingIndicator(slack_api, channel)
        typing_tasks[f"{channel}_{user}"] = typing
        
        await typing.start()
        
        # Generate AI response with tenant context
        ai_response = await ai_agent.process_message(tenant_id, user, text)
        
        # Send final response
        await typing.stop_and_respond(ai_response)
        
        # Clean up
        if f"{channel}_{user}" in typing_tasks:
            del typing_tasks[f"{channel}_{user}"]
        
        logger.info(f"✅ Processed message from {user} in tenant {tenant_id}")
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await slack_api.send_message(
            channel, 
            "I'm sorry, I encountered an error processing your message. Please try again."
        )

@app.get("/test")
async def test_endpoint():
    """Simple test endpoint"""
    return {
        "status": "test_passed",
        "timestamp": datetime.now().isoformat(),
        "message": "EnableBot AI Service is running!"
    }

@app.post("/test")
async def test_ai_with_tenant(request: Request):
    """Test AI functionality with tenant context"""
    try:
        data = await request.json()
        tenant_id = data.get("tenant_id", "demo")
        user_id = data.get("user_id", "test_user")
        message = data.get("message", "Hello!")
        
        response = await ai_agent.process_message(tenant_id, user_id, message)
        return {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "message": message,
            "response": response,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tenant/{tenant_id}/users")
async def get_tenant_users(tenant_id: str):
    """Get all users for a tenant"""
    if not supabase_client:
        return {
            "users": [
                {
                    "slack_user_id": "demo_user",
                    "full_name": "Demo User",
                    "role": "Employee",
                    "department": "Engineering",
                    "location": "Remote",
                    "tenant_id": tenant_id
                }
            ]
        }
    
    try:
        response = await supabase_client.get(
            f"{SUPABASE_URL}/rest/v1/user_profiles",
            params={
                "tenant_id": f"eq.{tenant_id}",
                "active": "eq.true"
            }
        )
        
        if response.status_code == 200:
            return {"users": response.json()}
        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch users")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/reset/{tenant_id}")
async def reset_tenant_memory(tenant_id: str):
    """Reset chat memory for a tenant"""
    global chat_memory
    
    # Clear in-memory storage for this tenant
    keys_to_remove = [key for key in chat_memory.keys() if key.startswith(f"{tenant_id}_")]
    for key in keys_to_remove:
        del chat_memory[key]
    
    return {
        "status": "memory_reset",
        "tenant_id": tenant_id,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/stats")
async def get_stats():
    """Get service statistics"""
    return {
        "active_conversations": len(chat_memory),
        "active_typing_indicators": len(typing_tasks),
        "total_memory_keys": len(chat_memory),
        "uptime": datetime.now().isoformat(),
        "services_status": {
            "openai": bool(openai_client),
            "slack": bool(slack_client), 
            "supabase": bool(supabase_client)
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8001))
    logger.info(f"🚀 Starting EnableBot AI Service on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)