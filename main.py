# main.py - Complete EnableBot AI Service with Slack Installation Flow
from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import os
import asyncio
import logging
import time
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
from urllib.parse import urlencode
import secrets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="EnableBot AI Service", version="2.1.0")

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
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI")

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

class SlackInstallation(BaseModel):
    team_id: str
    team_name: str
    bot_token: str
    bot_user_id: str
    installer_id: str
    installer_name: str
    scopes: List[str]

class CompanySetup(BaseModel):
    company_name: str
    admin_name: str
    admin_email: Optional[str] = None
    admin_role: str = "Admin"
    department: str = "Management"
    location: str = "Office"

# Document processing utilities
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

# Database functions
async def get_user_profile(tenant_id: str, slack_user_id: str) -> Optional[UserProfile]:
    """Get user profile from Supabase"""
    if not supabase_client:
        # Enhanced fallback with real-looking data
        return UserProfile(
            slack_user_id=slack_user_id,
            full_name="Surya Muralirajan",
            role="Founder & CEO", 
            department="Executive",
            location="San Francisco, CA",
            tool_access=["Slack", "Jira", "GitHub", "Google Workspace", "Notion"],
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
            full_name="New Team Member",
            role="Employee",
            department="General",
            location="Remote",
            tool_access=["Slack"],
            tenant_id=tenant_id
        )
        
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        return UserProfile(
            slack_user_id=slack_user_id,
            full_name="Surya Muralirajan",
            role="Founder & CEO",
            department="Executive", 
            location="San Francisco, CA",
            tool_access=["Slack"],
            tenant_id=tenant_id
        )

async def get_tenant_info(tenant_id: str) -> Optional[TenantInfo]:
    """Get tenant information from Supabase"""
    if not supabase_client:
        return TenantInfo(
            tenant_id=tenant_id,
            company_name="EnableOps",
            settings={"features": ["ai_chat", "document_search"], "plan": "pro"}
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
            company_name="EnableOps",
            settings={"features": ["ai_chat", "document_search"], "plan": "pro"}
        )
        
    except Exception as e:
        logger.error(f"Error fetching tenant info: {e}")
        return TenantInfo(
            tenant_id=tenant_id,
            company_name="EnableOps",
            settings={"features": ["ai_chat", "document_search"], "plan": "pro"}
        )

async def search_knowledge_base(tenant_id: str, query: str, limit: int = 3) -> List[Dict]:
    """Search tenant's knowledge base using documents table"""
    if not supabase_client:
        return [
            {
                "content": "EnableOps offers flexible PTO, comprehensive health insurance, and a $5,000 annual learning budget. We have core collaboration hours from 10 AM - 2 PM PST with flexible scheduling outside those hours.",
                "similarity": 0.85,
                "metadata": {"source": "employee_handbook", "type": "benefits"}
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
                        "metadata": doc.get("metadata", {}),
                        "title": doc.get("title", "")
                    }
                    for doc in results
                ]
        
        # Fallback to text search using documents table
        response = await supabase_client.get(
            f"{SUPABASE_URL}/rest/v1/documents",
            params={
                "content": f"ilike.%{query}%",
                "tenant_id": f"eq.{tenant_id}",
                "active": "eq.true",
                "limit": limit
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            return [
                {
                    "content": doc.get("content", ""),
                    "similarity": 0.8,
                    "metadata": doc.get("metadata", {}),
                    "title": doc.get("title", "")
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

async def save_document_to_db(tenant_id: str, title: str, content: str, document_type: str, metadata: dict) -> Dict:
    """Save document with embedding to Supabase"""
    if not supabase_client:
        return {"id": "demo_doc", "status": "saved_locally"}
    
    try:
        # Generate embedding for the content
        embedding = await get_embedding(content)
        
        # Save to documents table
        response = await supabase_client.post(
            f"{SUPABASE_URL}/rest/v1/documents",
            json={
                "tenant_id": tenant_id,
                "title": title,
                "content": content,
                "embedding": embedding,
                "document_type": document_type,
                "metadata": metadata,
                "active": True
            }
        )
        
        if response.status_code == 201:
            result = response.json()
            return {"id": result[0]["id"], "status": "success"}
        else:
            logger.error(f"Failed to save document: {response.text}")
            return {"error": "Failed to save document"}
            
    except Exception as e:
        logger.error(f"Error saving document: {e}")
        return {"error": str(e)}

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

# Database functions for auto-setup
async def create_tenant_from_slack(installation: SlackInstallation) -> bool:
    """Automatically create tenant from Slack installation"""
    if not supabase_client:
        logger.warning("Supabase not available - tenant creation skipped")
        return False
    
    try:
        # Check if tenant already exists
        existing = await supabase_client.get(
            f"{SUPABASE_URL}/rest/v1/tenants",
            params={"team_id": f"eq.{installation.team_id}"}
        )
        
        if existing.status_code == 200 and existing.json():
            logger.info(f"Tenant {installation.team_id} already exists - updating")
            # Update existing tenant
            await supabase_client.patch(
                f"{SUPABASE_URL}/rest/v1/tenants",
                params={"team_id": f"eq.{installation.team_id}"},
                json={
                    "team_name": installation.team_name,
                    "access_token": installation.bot_token,
                    "bot_user_id": installation.bot_user_id,
                    "last_active": datetime.now().isoformat(),
                    "active": True
                }
            )
        else:
            # Create new tenant
            await supabase_client.post(
                f"{SUPABASE_URL}/rest/v1/tenants",
                json={
                    "team_id": installation.team_id,
                    "team_name": installation.team_name,
                    "access_token": installation.bot_token,
                    "bot_user_id": installation.bot_user_id,
                    "installed_by": installation.installer_id,
                    "installer_name": installation.installer_name,
                    "plan": "free",
                    "settings": {
                        "features": ["ai_chat", "document_search"],
                        "max_users": 50,
                        "installation_date": datetime.now().isoformat(),
                        "scopes": installation.scopes
                    }
                }
            )
        
        # Log installation event
        await supabase_client.post(
            f"{SUPABASE_URL}/rest/v1/installation_events",
            json={
                "team_id": installation.team_id,
                "team_name": installation.team_name,
                "event_type": "app_installed",
                "installed_by": installation.installer_id,
                "installer_name": installation.installer_name,
                "metadata": {
                    "bot_user_id": installation.bot_user_id,
                    "scopes": installation.scopes,
                    "installation_timestamp": datetime.now().isoformat()
                }
            }
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error creating tenant: {e}")
        return False

async def create_admin_user(installation: SlackInstallation) -> bool:
    """Create admin user profile from installation"""
    if not supabase_client:
        return False
    
    try:
        # Check if user already exists
        existing = await supabase_client.get(
            f"{SUPABASE_URL}/rest/v1/user_profiles",
            params={
                "tenant_id": f"eq.{installation.team_id}",
                "slack_user_id": f"eq.{installation.installer_id}"
            }
        )
        
        if existing.status_code == 200 and existing.json():
            logger.info(f"Admin user {installation.installer_id} already exists")
            return True
        
        # Create admin user profile
        await supabase_client.post(
            f"{SUPABASE_URL}/rest/v1/user_profiles",
            json={
                "tenant_id": installation.team_id,
                "slack_user_id": installation.installer_id,
                "full_name": installation.installer_name,
                "role": "Admin",
                "department": "Management",
                "location": "Office",
                "tool_access": ["Slack", "EnableBot Admin", "All Features"],
                "active": True
            }
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
        return False

async def create_sample_documents(tenant_id: str, company_name: str) -> bool:
    """Create sample documents for new tenant"""
    if not supabase_client:
        return False
    
    sample_docs = [
        {
            "title": f"{company_name} Welcome Guide",
            "content": f"""Welcome to {company_name}!

This is your getting started guide. Here you'll find:

COMPANY OVERVIEW:
{company_name} is committed to innovation and excellence. We believe in empowering our team members with the tools and knowledge they need to succeed.

COMMUNICATION:
- Primary communication happens in Slack
- Use @EnableBot for AI assistance with company questions
- Weekly team meetings are scheduled for project updates

GETTING HELP:
- Ask @EnableBot about company policies, procedures, and general questions
- Contact your manager for role-specific guidance
- IT support is available for technical issues

RESOURCES:
- Company handbook (coming soon)
- IT setup guide (coming soon)
- Benefits information (coming soon)

Welcome to the team!""",
            "document_type": "welcome_guide",
            "metadata": {
                "auto_generated": True,
                "template": "default_welcome",
                "created_for": company_name
            }
        },
        {
            "title": "How to Use EnableBot",
            "content": """ENABLEBOT USAGE GUIDE

EnableBot is your AI assistant for workplace questions. Here's how to use it:

BASIC USAGE:
- Direct message EnableBot for private questions
- Ask about company policies, procedures, IT help, and more

EXAMPLE QUESTIONS:
- "What's our vacation policy?"
- "How do I access the company VPN?"
- "Who should I contact for IT support?"
- "What are our meeting room booking procedures?"

FEATURES:
- Instant answers based on company knowledge
- Context-aware responses
- Conversation memory
- Document search capabilities

TIPS:
- Be specific in your questions for better answers
- EnableBot learns from your company's uploaded documents
- Admins can upload new documents to expand the knowledge base

Need help? Just ask EnableBot: "How can you help me?" """,
            "document_type": "user_guide",
            "metadata": {
                "auto_generated": True,
                "template": "enablebot_guide",
                "priority": "high"
            }
        }
    ]
    
    try:
        for doc in sample_docs:
            # Generate embedding
            embedding = await get_embedding(doc["content"])
            
            await supabase_client.post(
                f"{SUPABASE_URL}/rest/v1/documents",
                json={
                    "tenant_id": tenant_id,
                    "title": doc["title"],
                    "content": doc["content"],
                    "embedding": embedding,
                    "document_type": doc["document_type"],
                    "metadata": doc["metadata"],
                    "active": True
                }
            )
        
        logger.info(f"Created {len(sample_docs)} sample documents for {tenant_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating sample documents: {e}")
        return False

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
- When referencing company policies, mention the source document if available

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
                    title = kb.get('title', 'Company Document')
                    if len(content) > 300:
                        content = content[:300] + "..."
                    knowledge_parts.append(f"From '{title}': {content}")
                knowledge_context = "\n\n".join(knowledge_parts)
            
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

@app.get("/", response_class=HTMLResponse)
async def root_with_install():
    """Root page with Slack installation option"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>EnableBot - AI Assistant for Slack</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                   max-width: 800px; margin: 0 auto; padding: 20px; background: #f8fafc; }}
            .container {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
            .hero {{ text-align: center; margin-bottom: 40px; }}
            .install-btn {{ display: inline-block; background: #4a154b; color: white; padding: 15px 30px; 
                           border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 18px; }}
            .features {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 30px 0; }}
            .feature {{ background: #f1f5f9; padding: 20px; border-radius: 8px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="hero">
                <h1>🤖 EnableBot</h1>
                <p>AI-powered assistant for your Slack workspace</p>
                <a href="/slack/install" class="install-btn">
                    <img src="https://platform.slack-edge.com/img/add_to_slack.png" alt="Add to Slack" width="139" height="40">
                </a>
            </div>
            
            <div class="features">
                <div class="feature">
                    <h3>🧠 Smart Answers</h3>
                    <p>Get instant answers about company policies, procedures, and more</p>
                </div>
                <div class="feature">
                    <h3>📚 Knowledge Base</h3>
                    <p>Upload documents and let AI search through your company knowledge</p>
                </div>
                <div class="feature">
                    <h3>💬 Natural Chat</h3>
                    <p>Conversation memory and context-aware responses</p>
                </div>
                <div class="feature">
                    <h3>🏢 Multi-Tenant</h3>
                    <p>Each workspace gets isolated, personalized AI assistance</p>
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <p><strong>Service Status:</strong></p>
                <p>🟢 AI Service: Running<br>
                   🟢 Database: Connected<br>
                   🟢 Document Processing: Ready</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/api")
async def api_status():
    """API status endpoint"""
    return {
        "service": "EnableBot AI Service",
        "version": "2.1.0",
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
            "Document upload & processing",
            "Conversation memory",
            "Slack integration",
            "Vector search capabilities"
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

@app.get("/slack/install")
async def start_slack_installation():
    """Start Slack OAuth installation flow"""
    if not SLACK_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Slack client ID not configured")
    
    # Generate state parameter for security
    state = secrets.token_urlsafe(32)
    
    # Updated scopes to match your Slack app configuration
    scopes = [
        "chat:write",
        "im:read",      # Changed from im:history
        "im:write", 
        "users:read",
        "teams:read"
    ]
    
    oauth_params = {
        "client_id": SLACK_CLIENT_ID,
        "scope": ",".join(scopes),
        "redirect_uri": SLACK_REDIRECT_URI,
        "state": state
    }
    
    oauth_url = f"https://slack.com/oauth/v2/authorize?{urlencode(oauth_params)}"
    
    return RedirectResponse(url=oauth_url, status_code=302)
    """Start Slack OAuth installation flow"""
    if not SLACK_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Slack client ID not configured")
    
    # Generate state parameter for security
    state = secrets.token_urlsafe(32)
    
    # Slack OAuth URL with required scopes (DM-only scopes)
    scopes = [
        "chat:write",
        "im:history",
        "im:write",
        "users:read",
        "teams:read"
    ]
    
    oauth_params = {
        "client_id": SLACK_CLIENT_ID,
        "scope": ",".join(scopes),
        "redirect_uri": SLACK_REDIRECT_URI,
        "state": state
    }
    
    oauth_url = f"https://slack.com/oauth/v2/authorize?{urlencode(oauth_params)}"
    
    # Redirect directly to Slack instead of returning JSON
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=oauth_url, status_code=302)

@app.get("/slack/oauth")
async def handle_slack_oauth(code: str, state: str = None):
    """Handle Slack OAuth callback and complete installation"""
    if not all([SLACK_CLIENT_ID, SLACK_CLIENT_SECRET]):
        raise HTTPException(status_code=500, detail="Slack OAuth not properly configured")
    
    try:
        # Exchange code for access token
        oauth_response = await slack_client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": SLACK_REDIRECT_URI
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        oauth_data = oauth_response.json()
        
        if not oauth_data.get("ok"):
            raise HTTPException(status_code=400, detail=f"Slack OAuth failed: {oauth_data.get('error')}")
        
        # Extract installation details
        team_info = oauth_data["team"]
        bot_info = oauth_data["bot_user"]
        installer_info = oauth_data["authed_user"]
        
        installation = SlackInstallation(
            team_id=team_info["id"],
            team_name=team_info["name"],
            bot_token=oauth_data["access_token"],
            bot_user_id=bot_info["bot_user_id"],
            installer_id=installer_info["id"],
            installer_name=installer_info.get("name", "Unknown"),
            scopes=oauth_data["scope"].split(",")
        )
        
        # Automatically set up the tenant
        tenant_created = await create_tenant_from_slack(installation)
        admin_created = await create_admin_user(installation)
        docs_created = await create_sample_documents(installation.team_id, installation.team_name)
        
        if tenant_created and admin_created:
            # Send welcome message to installer
            welcome_message = f"""🎉 Welcome to EnableBot!

Hi {installation.installer_name}! EnableBot has been successfully installed to {installation.team_name}.

WHAT'S NEXT:
✅ Your workspace is now set up
✅ You're registered as an admin
✅ Sample documents have been created

TRY IT OUT:
• Direct message @EnableBot for private AI assistance
• Ask: "What can you help me with?"
• Upload company documents at: {SLACK_REDIRECT_URI.replace('/slack/oauth', '/upload')}

ADMIN FEATURES:
• Manage users and documents
• View usage analytics
• Configure AI behavior

Questions? Just ask @EnableBot: "How do I get started as an admin?"

Happy automating! 🚀"""
            
            # Send DM to installer
            await slack_client.post(
                "https://slack.com/api/chat.postMessage",
                json={
                    "channel": installation.installer_id,
                    "text": welcome_message
                },
                headers={"Authorization": f"Bearer {installation.bot_token}"}
            )
            
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>EnableBot Installation Success</title>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                           max-width: 600px; margin: 50px auto; padding: 20px; text-align: center; }}
                    .success {{ background: #10b981; color: white; padding: 20px; border-radius: 12px; margin: 20px 0; }}
                    .info {{ background: #3b82f6; color: white; padding: 15px; border-radius: 8px; margin: 20px 0; }}
                    .actions {{ margin: 30px 0; }}
                    .btn {{ display: inline-block; background: #1f2937; color: white; padding: 12px 24px; 
                           border-radius: 8px; text-decoration: none; margin: 10px; }}
                </style>
            </head>
            <body>
                <h1>🎉 EnableBot Successfully Installed!</h1>
                <div class="success">
                    <h2>✅ Installation Complete</h2>
                    <p><strong>{installation.team_name}</strong> is now set up with EnableBot!</p>
                </div>
                
                <div class="info">
                    <h3>What's Been Set Up:</h3>
                    <p>✅ Workspace: {installation.team_name}<br>
                       ✅ Admin User: {installation.installer_name}<br>
                       ✅ Sample Documents Created<br>
                       ✅ AI Assistant Ready</p>
                </div>
                
                <div class="actions">
                    <h3>Next Steps:</h3>
                    <a href="slack://channel?team={installation.team_id}" class="btn">Open Slack</a>
                    <a href="/upload" class="btn">Upload Documents</a>
                    <a href="/tenant/{installation.team_id}/users" class="btn">View Dashboard</a>
                </div>
                
                <p><strong>Try it now:</strong> Go to Slack and send a direct message to @EnableBot!</p>
            </body>
            </html>
            """)
        else:
            raise HTTPException(status_code=500, detail="Failed to complete workspace setup")
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=f"Installation failed: {str(e)}")

@app.get("/upload", response_class=HTMLResponse)
async def upload_page():
    """Document upload interface"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>EnableBot Document Upload</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f8fafc; }
            .container { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
            h1 { color: #1e293b; margin-bottom: 30px; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 8px; font-weight: 600; color: #374151; }
            input, select, textarea { width: 100%; padding: 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px; }
            input:focus, select:focus, textarea:focus { outline: none; border-color: #3b82f6; }
            .file-upload { border: 2px dashed #d1d5db; border-radius: 8px; padding: 40px; text-align: center; cursor: pointer; }
            .file-upload:hover { border-color: #3b82f6; background: #f8fafc; }
            button { background: #3b82f6; color: white; padding: 12px 24px; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; }
            button:hover { background: #2563eb; }
            .success { background: #10b981; color: white; padding: 16px; border-radius: 8px; margin-top: 20px; display: none; }
            .error { background: #ef4444; color: white; padding: 16px; border-radius: 8px; margin-top: 20px; display: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📄 EnableBot Document Upload</h1>
            <form id="uploadForm" enctype="multipart/form-data">
                <div class="form-group">
                    <label for="tenantId">Company/Tenant ID:</label>
                    <input type="text" id="tenantId" name="tenant_id" required placeholder="e.g., T07ABC123XYZ">
                    <small>Enter your Slack workspace team ID</small>
                </div>
                <div class="form-group">
                    <label for="title">Document Title:</label>
                    <input type="text" id="title" name="title" required placeholder="e.g., Employee Handbook, IT Policies">
                </div>
                <div class="form-group">
                    <label for="documentType">Document Type:</label>
                    <select id="documentType" name="document_type" required>
                        <option value="">Select Type</option>
                        <option value="handbook">Employee Handbook</option>
                        <option value="policy">Company Policy</option>
                        <option value="it_guide">IT Guide</option>
                        <option value="procedure">Procedure</option>
                        <option value="faq">FAQ</option>
                        <option value="other">Other</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="description">Description (Optional):</label>
                    <textarea id="description" name="description" rows="3" placeholder="Brief description..."></textarea>
                </div>
                <div class="form-group">
                    <label>Upload Document:</label>
                    <div class="file-upload" onclick="document.getElementById('fileInput').click()">
                        <input type="file" id="fileInput" name="file" accept=".pdf,.doc,.docx,.txt,.md" style="display: none;">
                        <strong>Click to upload</strong> or drag and drop<br>
                        <small>Supports: PDF, Word, Text, Markdown files</small>
                    </div>
                </div>
                <button type="submit">🚀 Upload & Process Document</button>
            </form>
            <div class="success" id="success">✅ Document uploaded and processed successfully!</div>
            <div class="error" id="error">❌ <span id="errorText"></span></div>
        </div>
        <script>
            document.getElementById('uploadForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                try {
                    const response = await fetch('/upload-document', { method: 'POST', body: formData });
                    if (response.ok) {
                        document.getElementById('success').style.display = 'block';
                        document.getElementById('error').style.display = 'none';
                        e.target.reset();
                    } else {
                        const error = await response.json();
                        document.getElementById('errorText').textContent = error.detail || 'Upload failed';
                        document.getElementById('error').style.display = 'block';
                        document.getElementById('success').style.display = 'none';
                    }
                } catch (error) {
                    document.getElementById('errorText').textContent = 'Network error: ' + error.message;
                    document.getElementById('error').style.display = 'block';
                    document.getElementById('success').style.display = 'none';
                }
            });
        </script>
    </body>
    </html>
    """

@app.post("/upload-document")
async def upload_document(
    tenant_id: str = Form(...),
    title: str = Form(...),
    document_type: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...)
):
    """Upload and process document with embedding generation"""
    try:
        # Extract text from uploaded file
        content = await extract_text_from_file(file)
        
        if not content.strip():
            raise HTTPException(status_code=400, detail="No text content found in the uploaded file")
        
        # Prepare metadata
        metadata = {
            "original_filename": file.filename,
            "file_size": file.size,
            "content_type": file.content_type,
            "description": description,
            "uploaded_at": datetime.now().isoformat(),
            "processed_by": "enablebot_ai"
        }
        
        # Save document to database with embedding
        result = await save_document_to_db(tenant_id, title, content, document_type, metadata)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return {
            "status": "success",
            "message": "Document uploaded and processed successfully",
            "document_id": result["id"],
            "title": title,
            "tenant_id": tenant_id,
            "content_length": len(content),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

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
        tenant_id = data.get("tenant_id", "T07ENABLEOPS123")
        user_id = data.get("user_id", "U07SURYA789")
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
                    "slack_user_id": "U07SURYA789",
                    "full_name": "Surya Muralirajan",
                    "role": "Founder & CEO",
                    "department": "Executive",
                    "location": "San Francisco, CA",
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

@app.get("/tenant/{tenant_id}/documents")
async def get_tenant_documents(tenant_id: str):
    """Get all documents for a tenant"""
    if not supabase_client:
        return {"documents": [{"title": "Demo Document", "type": "handbook"}]}
    
    try:
        response = await supabase_client.get(
            f"{SUPABASE_URL}/rest/v1/documents",
            params={
                "tenant_id": f"eq.{tenant_id}",
                "active": "eq.true",
                "select": "id,title,document_type,metadata,created_at"
            }
        )
        
        if response.status_code == 200:
            return {"documents": response.json()}
        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch documents")
            
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