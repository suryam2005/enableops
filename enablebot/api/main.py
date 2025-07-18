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
import PyPDF2
import docx
from datetime import datetime
from typing import Dict, Optional, List, Any
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import shared components
from enablebot.shared.database.config import db, init_database, close_database
from enablebot.shared.encryption.encryption import decrypt_slack_token, initialize_encryption

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

# Multi-tenant Slack client manager
class SlackClientManager:
    """Manages Slack clients for multiple workspaces with encrypted tokens"""
    
    def __init__(self):
        self.clients = {}
        self.base_url = "https://slack.com/api"
    
    async def get_client(self, team_id: str) -> Optional[httpx.AsyncClient]:
        """Get or create Slack client for a specific workspace"""
        if team_id in self.clients:
            return self.clients[team_id]
        
        try:
            # Get tenant data from database
            tenant_data = await db.fetchrow(
                "SELECT encrypted_bot_token, encryption_key_id FROM tenants WHERE team_id = $1 AND status = $2",
                team_id, "active"
            )
            
            if not tenant_data:
                logger.error(f"No active tenant found for team_id: {team_id}")
                return None
            
            # Decrypt the bot token
            bot_token = await decrypt_slack_token(
                tenant_data["encrypted_bot_token"],
                tenant_data["encryption_key_id"],
                team_id
            )
            
            # Create Slack client for this workspace
            client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {bot_token}"},
                timeout=30.0
            )
            
            # Cache the client
            self.clients[team_id] = client
            logger.info(f"✅ Created Slack client for team {team_id}")
            
            return client
            
        except Exception as e:
            logger.error(f"Error creating Slack client for {team_id}: {e}")
            return None
    
    async def send_message(self, team_id: str, channel: str, text: str, thread_ts: str = None) -> bool:
        """Send message to Slack channel using team-specific client"""
        client = await self.get_client(team_id)
        if not client:
            logger.error(f"No Slack client available for team {team_id}")
            return False
        
        try:
            payload = {
                "channel": channel,
                "text": text
            }
            if thread_ts:
                payload["thread_ts"] = thread_ts
            
            response = await client.post(
                f"{self.base_url}/chat.postMessage",
                json=payload
            )
            
            result = response.json()
            if result.get("ok"):
                logger.info(f"✅ Message sent to {channel} in team {team_id}")
                return True
            else:
                logger.error(f"❌ Slack API error for team {team_id}: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Slack message to team {team_id}: {e}")
            return False
    
    async def close_all(self):
        """Close all Slack clients"""
        for client in self.clients.values():
            await client.aclose()
        self.clients.clear()

# Global Slack client manager
slack_manager = SlackClientManager()

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

# Database functions
async def get_user_profile(tenant_id: str, slack_user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile from database"""
    try:
        user_data = await db.fetchrow("""
            SELECT slack_user_id, full_name, role, department, location, tool_access
            FROM user_profiles 
            WHERE tenant_id = $1 AND slack_user_id = $2 AND active = true
        """, tenant_id, slack_user_id)
        
        if user_data:
            return dict(user_data)
        
        # Create default profile for new users
        await db.execute("""
            INSERT INTO user_profiles (tenant_id, slack_user_id, full_name, role, department, location, tool_access, active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, true)
            ON CONFLICT (tenant_id, slack_user_id) DO NOTHING
        """, tenant_id, slack_user_id, "Team Member", "Employee", "General", "Remote", ["Slack"])
        
        return {
            "slack_user_id": slack_user_id,
            "full_name": "Team Member",
            "role": "Employee",
            "department": "General",
            "location": "Remote",
            "tool_access": ["Slack"]
        }
        
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        return None

async def get_tenant_info(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Get tenant information from database"""
    try:
        tenant_data = await db.fetchrow(
            "SELECT team_id, team_name, settings FROM tenants WHERE team_id = $1 AND status = $2",
            tenant_id, "active"
        )
        
        if tenant_data:
            return dict(tenant_data)
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching tenant info: {e}")
        return None

async def search_knowledge_base(tenant_id: str, query: str, limit: int = 3) -> List[Dict]:
    """Search tenant's knowledge base"""
    try:
        results = await db.fetch("""
            SELECT title, content, document_type, metadata
            FROM documents 
            WHERE tenant_id = $1 AND active = true 
            AND (content ILIKE $2 OR title ILIKE $2)
            ORDER BY created_at DESC
            LIMIT $3
        """, tenant_id, f"%{query}%", limit)
        
        return [
            {
                "content": row["content"][:500] + "..." if len(row["content"]) > 500 else row["content"],
                "title": row["title"],
                "similarity": 0.8,
                "metadata": row["metadata"] or {}
            }
            for row in results
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
    """Save chat message to database"""
    try:
        await db.execute("""
            INSERT INTO chat_memory (tenant_id, session_id, message_type, content, created_at)
            VALUES ($1, $2, $3, $4, NOW())
        """, tenant_id, session_id, message_type, content)
    except Exception as e:
        logger.error(f"Error saving chat message: {e}")

async def get_chat_history(tenant_id: str, session_id: str, limit: int = 10) -> List[Dict]:
    """Get chat history from database"""
    try:
        history = await db.fetch("""
            SELECT message_type, content
            FROM chat_memory 
            WHERE tenant_id = $1 AND session_id = $2
            ORDER BY created_at DESC
            LIMIT $3
        """, tenant_id, session_id, limit)
        
        return [
            {
                "role": "user" if row["message_type"] == "human" else "assistant",
                "content": row["content"]
            }
            for row in reversed(history)
        ]
    except Exception as e:
        logger.error(f"Error fetching chat history: {e}")
        return []

class TenantAwareAI:
    """AI agent with tenant-specific context"""
    
    def __init__(self):
        self.base_prompt = """You are EnableBot, a helpful AI assistant for {company_name}.

You help employees with workplace questions including HR, IT, policies, and general support.

USER CONTEXT:
- Name: {user_name}
- Role: {user_role}
- Department: {user_department}
- Location: {user_location}

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

You are designed to help with workplace questions for {company_name} employees."""

    async def process_message(self, tenant_id: str, user_id: str, message: str) -> str:
        """Process message with tenant-aware context"""
        try:
            if not openai_client:
                return "I'm sorry, but I'm not able to access my AI capabilities right now. Please try again later or contact your IT support."

            # Get user profile and tenant info
            user_profile = await get_user_profile(tenant_id, user_id)
            tenant_info = await get_tenant_info(tenant_id)
            
            if not user_profile or not tenant_info:
                return "I'm having trouble accessing your workspace information. Please try again or contact your admin."
            
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
                    title = kb.get('title', 'Company Document')
                    knowledge_parts.append(f"From '{title}': {content}")
                knowledge_context = "\n\n".join(knowledge_parts)
            
            # Build personalized system prompt
            system_prompt = self.base_prompt.format(
                company_name=tenant_info.get("team_name", "your company"),
                user_name=user_profile.get("full_name", "Team Member"),
                user_role=user_profile.get("role", "Employee"),
                user_department=user_profile.get("department", "General"),
                user_location=user_profile.get("location", "Remote"),
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

# Global AI assistant
ai_assistant = TenantAwareAI()

# Slack event verification
def verify_slack_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature"""
    if not SLACK_SIGNING_SECRET:
        logger.warning("SLACK_SIGNING_SECRET not configured - skipping signature verification")
        return True
    
    try:
        basestring = f"v0:{timestamp}:{request_body.decode('utf-8')}"
        expected_signature = "v0=" + hmac.new(
            SLACK_SIGNING_SECRET.encode(),
            basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    except Exception as e:
        logger.error(f"Error verifying Slack signature: {e}")
        return False

# API Endpoints
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("🚀 Starting EnableBot AI Service...")
    
    # Initialize database
    if await init_database():
        logger.info("✅ Database connection initialized")
    else:
        logger.error("❌ Failed to initialize database")
    
    # Initialize encryption
    initialize_encryption()
    
    logger.info("🎉 EnableBot AI Service ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    logger.info("🛑 Shutting down EnableBot AI Service...")
    await slack_manager.close_all()
    await close_database()
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

@app.post("/slack/events")
async def slack_events(request: Request):
    """Handle Slack events from all workspaces"""
    try:
        body = await request.body()
        headers = request.headers
        
        # Verify Slack signature
        timestamp = headers.get("x-slack-request-timestamp", "")
        signature = headers.get("x-slack-signature", "")
        
        if not verify_slack_signature(body, timestamp, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
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
            
            # Handle app mentions and direct messages
            if event.get("type") in ["app_mention", "message"]:
                # Extract message details
                user_id = event.get("user")
                text = event.get("text", "").strip()
                channel = event.get("channel")
                thread_ts = event.get("thread_ts")
                
                if not user_id or not text or not team_id:
                    return {"status": "ignored"}
                
                # Remove bot mention from text
                if event_data.get("api_app_id"):
                    text = text.replace(f"<@{event_data.get('api_app_id')}>", "").strip()
                
                if not text:
                    text = "Hello! How can I help you today?"
                
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
        
        # Send typing indicator
        typing_sent = await slack_manager.send_message(team_id, channel, "🤔 Thinking...", thread_ts)
        
        # Process message with AI
        response = await ai_assistant.process_message(team_id, user_id, message)
        
        # Send AI response
        await slack_manager.send_message(team_id, channel, response, thread_ts)
        
        logger.info(f"✅ Responded to user {user_id} in team {team_id}")
        
    except Exception as e:
        logger.error(f"Error processing Slack message: {e}")
        # Send error message
        await slack_manager.send_message(
            team_id, channel, 
            "I'm sorry, I encountered an error processing your request. Please try again later.",
            thread_ts
        )

@app.post("/api/chat")
async def chat_endpoint(chat_request: ChatRequest):
    """Direct chat API endpoint"""
    try:
        response = await ai_assistant.process_message(
            chat_request.tenant_id,
            chat_request.user_id,
            chat_request.message
        )
        
        return {
            "response": response,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Failed to process message")

@app.post("/api/documents/upload")
async def upload_document(
    tenant_id: str = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...)
):
    """Upload document to knowledge base"""
    try:
        # Extract text from file
        content = await extract_text_from_file(file)
        
        # Generate embedding
        embedding = await get_embedding(content)
        
        # Save to database
        await db.execute("""
            INSERT INTO documents (tenant_id, title, content, embedding, document_type, active, created_at)
            VALUES ($1, $2, $3, $4, $5, true, NOW())
        """, tenant_id, title, content, json.dumps(embedding) if embedding else None, file.content_type or "unknown")
        
        return {
            "status": "success",
            "message": "Document uploaded successfully",
            "title": title
        }
        
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload document")

async def extract_text_from_file(file: UploadFile) -> str:
    """Extract text content from uploaded file"""
    try:
        content = await file.read()
        
        if file.content_type == "application/pdf":
            # PDF extraction
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text.strip()
            
        elif file.content_type in ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]:
            # Word document extraction
            doc = docx.Document(io.BytesIO(content))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
            
        elif file.content_type.startswith("text/"):
            # Plain text files
            return content.decode('utf-8').strip()
            
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
            
    except Exception as e:
        logger.error(f"Error extracting text from file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)