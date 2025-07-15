# main.py - EnableBot with Optional Dependencies
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import os
import asyncio
import logging
import time
import json
import hmac
import hashlib
import httpx
import base64
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from pydantic import BaseModel

# Optional imports with fallbacks
try:
    import asyncpg
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    asyncpg = None

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    SentenceTransformer = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="EnableBot SaaS", version="2.0.0")

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
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
POSTGRES_URL = os.getenv("POSTGRES_URL")
JIRA_URL = os.getenv("JIRA_URL", "https://surya-ai.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

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
if SUPABASE_URL and SUPABASE_KEY:
    supabase_client = httpx.AsyncClient(
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        },
        timeout=30.0
    )
    logger.info("✅ Supabase HTTP client initialized")

# Initialize PostgreSQL connection pool
postgres_pool = None

# Initialize Jira client
jira_client = None
if JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN:
    try:
        auth_string = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        
        jira_client = httpx.AsyncClient(
            headers={
                "Authorization": f"Basic {encoded_auth}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=30.0
        )
        logger.info("✅ Jira HTTP client initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Jira: {e}")

# Initialize sentence transformer for embeddings (optional)
embedding_model = None
if EMBEDDINGS_AVAILABLE:
    try:
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("✅ Sentence transformer initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize embedding model: {e}")
else:
    logger.warning("⚠️ Sentence transformers not available - vector search disabled")

# In-memory storage for sessions and fallback
chat_sessions = {}
user_profiles_cache = {}
jira_tickets_cache = {}
usage_stats = {
    "total_messages": 0,
    "total_tokens": 0,
    "total_cost": 0.0,
    "daily_usage": {},
    "start_time": datetime.now()
}

# Pydantic models
class SlackEvent(BaseModel):
    type: str
    user: Optional[str] = None
    text: Optional[str] = None
    channel: Optional[str] = None
    ts: Optional[str] = None
    bot_id: Optional[str] = None
    blocks: Optional[List[Dict]] = None

class SlackEventWrapper(BaseModel):
    token: Optional[str] = None
    team_id: Optional[str] = None
    event: Optional[SlackEvent] = None
    type: str
    challenge: Optional[str] = None

class UserProfile(BaseModel):
    slack_user_id: str
    full_name: str
    role: str
    department: str
    location: str
    tool_access: List[str]

class JiraTicketRequest(BaseModel):
    summary: str
    description: Optional[str] = ""
    issue_type: str = "Task"
    priority: str = "Medium"

class DatabaseManager:
    """Handle all database operations with fallbacks"""
    
    @staticmethod
    async def init_postgres():
        """Initialize PostgreSQL connection pool"""
        global postgres_pool
        if POSTGRES_URL and POSTGRES_AVAILABLE and not postgres_pool:
            try:
                postgres_pool = await asyncpg.create_pool(POSTGRES_URL, min_size=1, max_size=5)
                await DatabaseManager.create_tables()
                logger.info("✅ PostgreSQL pool initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize PostgreSQL: {e}")
        elif not POSTGRES_AVAILABLE:
            logger.warning("⚠️ PostgreSQL not available - using in-memory storage")
    
    @staticmethod
    async def create_tables():
        """Create necessary tables"""
        if not postgres_pool:
            return
        
        try:
            async with postgres_pool.acquire() as conn:
                # Chat memory table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS chat_memory (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(255) NOT NULL,
                        message_type VARCHAR(20) NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Jira tickets memory
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS jira_tickets (
                        id SERIAL PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL,
                        ticket_key VARCHAR(50) NOT NULL,
                        summary TEXT NOT NULL,
                        status VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                logger.info("✅ Database tables created/verified")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
    
    @staticmethod
    async def get_user_profile(slack_user_id: str) -> Optional[UserProfile]:
        """Get user profile from Supabase or cache"""
        # Try cache first
        if slack_user_id in user_profiles_cache:
            return user_profiles_cache[slack_user_id]
        
        if not supabase_client:
            return None
        
        try:
            response = await supabase_client.get(
                f"{SUPABASE_URL}/rest/v1/user_profiles",
                params={"slack_user_id": f"eq.{slack_user_id}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data:
                    user_data = data[0]
                    profile = UserProfile(
                        slack_user_id=user_data["slack_user_id"],
                        full_name=user_data["full_name"],
                        role=user_data["role"],
                        department=user_data["department"],
                        location=user_data["location"],
                        tool_access=user_data["tool_access"] or []
                    )
                    # Cache the profile
                    user_profiles_cache[slack_user_id] = profile
                    return profile
        except Exception as e:
            logger.error(f"Error fetching user profile: {e}")
        
        return None
    
    @staticmethod
    async def get_chat_history(session_id: str, limit: int = 10) -> List[Dict]:
        """Get chat history from PostgreSQL or memory"""
        if postgres_pool:
            try:
                async with postgres_pool.acquire() as conn:
                    rows = await conn.fetch("""
                        SELECT message_type, content FROM chat_memory 
                        WHERE session_id = $1 
                        ORDER BY created_at DESC 
                        LIMIT $2
                    """, session_id, limit)
                    
                    history = []
                    for row in reversed(rows):
                        history.append({
                            "role": "user" if row["message_type"] == "human" else "assistant",
                            "content": row["content"]
                        })
                    
                    return history
            except Exception as e:
                logger.error(f"Error fetching chat history: {e}")
        
        # Fallback to in-memory storage
        return chat_sessions.get(session_id, [])
    
    @staticmethod
    async def save_chat_message(session_id: str, message_type: str, content: str):
        """Save chat message to PostgreSQL or memory"""
        if postgres_pool:
            try:
                async with postgres_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO chat_memory (session_id, message_type, content)
                        VALUES ($1, $2, $3)
                    """, session_id, message_type, content)
                    return
            except Exception as e:
                logger.error(f"Error saving chat message: {e}")
        
        # Fallback to in-memory storage
        if session_id not in chat_sessions:
            chat_sessions[session_id] = []
        
        chat_sessions[session_id].append({
            "role": "user" if message_type == "human" else "assistant",
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 20 messages in memory
        if len(chat_sessions[session_id]) > 20:
            chat_sessions[session_id] = chat_sessions[session_id][-20:]
    
    @staticmethod
    async def save_jira_ticket(user_id: str, ticket_key: str, summary: str, status: str = "Open"):
        """Save Jira ticket to memory"""
        if postgres_pool:
            try:
                async with postgres_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO jira_tickets (user_id, ticket_key, summary, status)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (ticket_key) DO UPDATE SET
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    """, user_id, ticket_key, summary, status)
                    return
            except Exception as e:
                logger.error(f"Error saving Jira ticket: {e}")
        
        # Fallback to in-memory storage
        jira_tickets_cache[user_id] = {
            "ticket_key": ticket_key,
            "summary": summary,
            "status": status,
            "created_at": datetime.now().isoformat()
        }
    
    @staticmethod
    async def get_last_jira_ticket(user_id: str) -> Optional[Dict]:
        """Get user's last Jira ticket"""
        if postgres_pool:
            try:
                async with postgres_pool.acquire() as conn:
                    row = await conn.fetchrow("""
                        SELECT ticket_key, summary, status FROM jira_tickets 
                        WHERE user_id = $1 
                        ORDER BY created_at DESC 
                        LIMIT 1
                    """, user_id)
                    
                    if row:
                        return {
                            "ticket_key": row["ticket_key"],
                            "summary": row["summary"],
                            "status": row["status"]
                        }
            except Exception as e:
                logger.error(f"Error fetching last Jira ticket: {e}")
        
        # Fallback to in-memory storage
        return jira_tickets_cache.get(user_id)

class VectorSearch:
    """Handle vector search operations"""
    
    @staticmethod
    async def search_knowledge_base(query: str, limit: int = 3) -> List[Dict]:
        """Search knowledge base using vector similarity"""
        if not supabase_client:
            logger.warning("Supabase not available for vector search")
            return []
        
        if not EMBEDDINGS_AVAILABLE:
            logger.warning("Embeddings not available - using text search fallback")
            # Simple text search fallback
            try:
                response = await supabase_client.get(
                    f"{SUPABASE_URL}/rest/v1/documents",
                    params={"content": f"ilike.%{query}%", "limit": limit}
                )
                
                if response.status_code == 200:
                    results = response.json()
                    return [
                        {
                            "content": doc["content"],
                            "metadata": doc.get("metadata", {}),
                            "similarity": 0.8  # Mock similarity
                        }
                        for doc in results
                    ]
            except Exception as e:
                logger.error(f"Error in text search: {e}")
            return []
        
        try:
            # Generate embedding for query
            query_embedding = embedding_model.encode(query).tolist()
            
            # Search in Supabase vector store
            response = await supabase_client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/match_documents",
                json={
                    "query_embedding": query_embedding,
                    "match_threshold": 0.7,
                    "match_count": limit
                }
            )
            
            if response.status_code == 200:
                results = response.json()
                return [
                    {
                        "content": doc["content"],
                        "metadata": doc["metadata"],
                        "similarity": doc["similarity"]
                    }
                    for doc in results
                ]
        except Exception as e:
            logger.error(f"Error in vector search: {e}")
        
        return []

class JiraManager:
    """Handle Jira operations"""
    
    @staticmethod
    async def create_ticket(summary: str, description: str = "", issue_type: str = "Task") -> Dict[str, Any]:
        """Create Jira ticket"""
        if not jira_client:
            return {"success": False, "error": "Jira not connected"}
        
        try:
            ticket_payload = {
                "fields": {
                    "project": {"id": "10000"},  # TEST BOARD from n8n workflow
                    "summary": summary,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": description or summary
                                    }
                                ]
                            }
                        ]
                    },
                    "issuetype": {"id": "10003"},  # Task from n8n workflow
                }
            }
            
            response = await jira_client.post(
                f"{JIRA_URL}/rest/api/3/issue",
                json=ticket_payload
            )
            
            if response.status_code == 201:
                ticket = response.json()
                ticket_key = ticket["key"]
                
                return {
                    "success": True,
                    "ticket_key": ticket_key,
                    "ticket_url": f"{JIRA_URL}/browse/{ticket_key}",
                    "summary": summary
                }
            else:
                error_details = response.json() if response.status_code != 500 else {"error": "Server error"}
                return {"success": False, "error": f"Failed to create ticket: {error_details}"}
                
        except Exception as e:
            logger.error(f"Error creating Jira ticket: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def get_ticket_status(ticket_key: str) -> Dict[str, Any]:
        """Get Jira ticket status"""
        if not jira_client:
            return {"success": False, "error": "Jira not connected"}
        
        try:
            response = await jira_client.get(f"{JIRA_URL}/rest/api/3/issue/{ticket_key}")
            
            if response.status_code == 200:
                issue = response.json()
                return {
                    "success": True,
                    "ticket_key": ticket_key,
                    "summary": issue["fields"]["summary"],
                    "status": issue["fields"]["status"]["name"],
                    "assignee": issue["fields"]["assignee"]["displayName"] if issue["fields"]["assignee"] else "Unassigned",
                    "url": f"{JIRA_URL}/browse/{ticket_key}"
                }
            else:
                return {"success": False, "error": "Ticket not found"}
                
        except Exception as e:
            logger.error(f"Error getting Jira ticket: {e}")
            return {"success": False, "error": str(e)}

class EnableBotAI:
    """Main AI agent that processes messages"""
    
    def __init__(self):
        self.system_prompt = """You are EnableOps Assistant, a helpful internal AI assistant.

You help employees with topics such as HR, IT, onboarding, tool access, compliance, internal policies, and Jira support.

You have access to an internal knowledge base. When users ask questions:
1. If relevant context is found, include the most accurate, useful, and concise answer based on that information.
2. If no relevant information is found, say so honestly and offer to help further.
3. If the answer is not in the knowledge base, use your own understanding to assist.

You can also create Jira tickets for users. When a user reports an issue or requests support, create a Jira ticket and return:
- A short confirmation message.
- The Jira ticket ID (e.g. KAN-123).
- A summary of what the ticket is about.

When responding with Jira ticket links, always use the format:
https://surya-ai.atlassian.net/browse/{ticket_id}

Always respond in clear and plain text without any special formatting, markdown, emojis, or symbols.

Rules:
- Only greet with "Hi {user_name}" if this is the first message in the session.
- Keep answers professional, short, and easy to understand."""

    async def process_message(self, user_profile: UserProfile, message: str, session_id: str) -> str:
        """Process user message with context and tools"""
        try:
            if not openai_client:
                return "I'm sorry, but I'm not able to access my AI capabilities right now. Please try again later or contact your IT support."

            # Get chat history
            chat_history = await DatabaseManager.get_chat_history(session_id)
            
            # Search knowledge base
            knowledge_results = await VectorSearch.search_knowledge_base(message)
            
            # Check for ticket-related queries
            last_ticket = await DatabaseManager.get_last_jira_ticket(user_profile.slack_user_id)
            
            # Build context
            context_parts = []
            
            # Add user context
            context_parts.append(f"""
Here's who you're speaking with:
- Name: {user_profile.full_name}
- Role: {user_profile.role}
- Department: {user_profile.department}
- Location: {user_profile.location}
- Tool Access: {', '.join(user_profile.tool_access)}
""")
            
            # Add knowledge base results
            if knowledge_results:
                context_parts.append("Knowledge Base Results:")
                for i, result in enumerate(knowledge_results, 1):
                    context_parts.append(f"{i}. {result['content']}")
            
            # Add last ticket info
            if last_ticket:
                context_parts.append(f"User's last Jira ticket: {last_ticket['ticket_key']} - {last_ticket['summary']} (Status: {last_ticket['status']})")
            
            # Build messages
            messages = [{"role": "system", "content": self.system_prompt}]
            
            # Add context
            if context_parts:
                messages.append({"role": "system", "content": "\n\n".join(context_parts)})
            
            # Add chat history
            messages.extend(chat_history[-10:])  # Last 10 messages
            
            # Add current message
            messages.append({"role": "user", "content": message})
            
            # Check if user wants to create a ticket
            if await self._should_create_ticket(message):
                ticket_result = await JiraManager.create_ticket(
                    summary=f"Support request from {user_profile.full_name}",
                    description=message
                )
                
                if ticket_result["success"]:
                    # Save ticket to memory
                    await DatabaseManager.save_jira_ticket(
                        user_profile.slack_user_id,
                        ticket_result["ticket_key"],
                        ticket_result["summary"]
                    )
                    
                    response = f"I've created a Jira ticket for you: {ticket_result['ticket_key']}. You can track it here: {ticket_result['ticket_url']}"
                else:
                    response = f"I tried to create a Jira ticket but encountered an error: {ticket_result['error']}"
            
            # Check if user wants ticket status
            elif await self._wants_ticket_status(message) and last_ticket:
                status_result = await JiraManager.get_ticket_status(last_ticket["ticket_key"])
                if status_result["success"]:
                    response = f"Your ticket {status_result['ticket_key']} is currently {status_result['status']}. Assignee: {status_result['assignee']}. Link: {status_result['url']}"
                else:
                    response = f"I couldn't retrieve the status for ticket {last_ticket['ticket_key']}. Please check manually."
            
            else:
                # Generate AI response
                completion = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    max_tokens=500,
                    temperature=0.7
                )
                
                response = completion.choices[0].message.content
                
                # Update usage stats
                usage_stats["total_messages"] += 1
                usage_stats["total_tokens"] += completion.usage.total_tokens
                usage_stats["total_cost"] += completion.usage.total_tokens * 0.000075  # GPT-4o-mini pricing
            
            # Save conversation to memory
            await DatabaseManager.save_chat_message(session_id, "human", message)
            await DatabaseManager.save_chat_message(session_id, "ai", response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return "I encountered an error while processing your request. Please try again, and if the problem persists, contact your IT support team."
    
    async def _should_create_ticket(self, message: str) -> bool:
        """Determine if message requires ticket creation"""
        ticket_keywords = [
            "create ticket", "create jira", "log ticket", "report issue", "submit request",
            "need help", "broken", "not working", "error", "problem", "issue"
        ]
        return any(keyword in message.lower() for keyword in ticket_keywords)
    
    async def _wants_ticket_status(self, message: str) -> bool:
        """Determine if user wants ticket status"""
        status_keywords = [
            "ticket status", "my ticket", "ticket update", "check ticket",
            "jira status", "my request", "last ticket"
        ]
        return any(keyword in message.lower() for keyword in status_keywords)

# Initialize components
ai_agent = EnableBotAI()

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

async def get_slack_user_info(user_id: str) -> Dict[str, Any]:
    """Get Slack user information"""
    if not slack_client:
        return {}
    
    try:
        response = await slack_client.get(f"https://slack.com/api/users.info?user={user_id}")
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                return data.get("user", {})
    except Exception as e:
        logger.error(f"Error fetching Slack user info: {e}")
    
    return {}

# Simple Dashboard HTML
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>EnableBot Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 2rem; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: white; padding: 2rem; border-radius: 8px; margin-bottom: 2rem; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; }
        .card { background: white; padding: 1.5rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .status-ok { color: #22c55e; font-weight: bold; }
        .status-error { color: #ef4444; font-weight: bold; }
        .metric { display: flex; justify-content: space-between; margin: 0.5rem 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 EnableBot Dashboard</h1>
            <p>AI Assistant with Slack, Jira & Knowledge Base Integration</p>
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>System Status</h3>
                <div class="metric">
                    <span>OpenAI:</span>
                    <span id="openai-status" class="status-error">Loading...</span>
                </div>
                <div class="metric">
                    <span>Slack:</span>
                    <span id="slack-status" class="status-error">Loading...</span>
                </div>
                <div class="metric">
                    <span>Jira:</span>
                    <span id="jira-status" class="status-error">Loading...</span>
                </div>
                <div class="metric">
                    <span>PostgreSQL:</span>
                    <span id="postgres-status" class="status-error">Loading...</span>
                </div>
                <div class="metric">
                    <span>Supabase:</span>
                    <span id="supabase-status" class="status-error">Loading...</span>
                </div>
            </div>
            
            <div class="card">
                <h3>Usage Statistics</h3>
                <div class="metric">
                    <span>Total Messages:</span>
                    <span id="total-messages">0</span>
                </div>
                <div class="metric">
                    <span>Total Tokens:</span>
                    <span id="total-tokens">0</span>
                </div>
                <div class="metric">
                    <span>Total Cost:</span>
                    <span id="total-cost">$0.00</span>
                </div>
            </div>
            
            <div class="card">
                <h3>Features Available</h3>
                <div class="metric">
                    <span>Vector Search:</span>
                    <span id="vector-status" class="status-error">Loading...</span>
                </div>
                <div class="metric">
                    <span>Chat Memory:</span>
                    <span id="memory-status" class="status-ok">Available</span>
                </div>
                <div class="metric">
                    <span>User Profiles:</span>
                    <span id="profiles-status" class="status-error">Loading...</span>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        async function updateStatus() {
            try {
                const response = await fetch('/health');
                const data = await response.json();
                
                // Update service status
                document.getElementById('openai-status').textContent = data.services.openai ? 'Connected' : 'Disconnected';
                document.getElementById('openai-status').className = data.services.openai ? 'status-ok' : 'status-error';
                
                document.getElementById('slack-status').textContent = data.services.slack ? 'Connected' : 'Disconnected';
                document.getElementById('slack-status').className = data.services.slack ? 'status-ok' : 'status-error';
                
                document.getElementById('jira-status').textContent = data.services.jira ? 'Connected' : 'Disconnected';
                document.getElementById('jira-status').className = data.services.jira ? 'status-ok' : 'status-error';
                
                document.getElementById('postgres-status').textContent = data.services.postgres ? 'Connected' : 'In-Memory';
                document.getElementById('postgres-status').className = data.services.postgres ? 'status-ok' : 'status-error';
                
                document.getElementById('supabase-status').textContent = data.services.supabase ? 'Connected' : 'Disconnected';
                document.getElementById('supabase-status').className = data.services.supabase ? 'status-ok' : 'status-error';
                
                document.getElementById('vector-status').textContent = data.services.embedding ? 'Available' : 'Text Search Only';
                document.getElementById('vector-status').className = data.services.embedding ? 'status-ok' : 'status-error';
                
                document.getElementById('profiles-status').textContent = data.services.supabase ? 'Available' : 'Cache Only';
                document.getElementById('profiles-status').className = data.services.supabase ? 'status-ok' : 'status-error';
                
                // Update usage stats
                document.getElementById('total-messages').textContent = data.usage.total_messages;
                document.getElementById('total-tokens').textContent = data.usage.total_tokens;
                document.getElementById('total-cost').textContent = ' + data.usage.total_cost.toFixed(2);
                
            } catch (error) {
                console.error('Error updating status:', error);
            }
        }
        
        // Update every 30 seconds
        setInterval(updateStatus, 30000);
        updateStatus();
    </script>
</body>
</html>
"""

# API Routes

@app.on_event("startup")
async def startup_event():
    """Initialize database connections on startup"""
    if POSTGRES_AVAILABLE:
        await DatabaseManager.init_postgres()
    else:
        logger.info("🟡 Starting with in-memory storage only")

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard"""
    return DASHBOARD_HTML

@app.get("/health")
async def health_check():
    """Enhanced health check with all services"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": bool(openai_client),
            "slack": bool(slack_client),
            "supabase": bool(supabase_client),
            "postgres": bool(postgres_pool),
            "jira": bool(jira_client),
            "embedding": bool(embedding_model)
        },
        "usage": usage_stats,
        "memory": {
            "active_sessions": len(chat_sessions)
        },
        "capabilities": {
            "postgres_available": POSTGRES_AVAILABLE,
            "embeddings_available": EMBEDDINGS_AVAILABLE
        }
    }

@app.post("/enable-bot")
async def handle_slack_webhook(request: Request):
    """Main webhook endpoint that mirrors n8n workflow"""
    try:
        body = await request.body()
        headers = request.headers
        
        # Parse JSON
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Handle URL verification (Code4 + Respond to Webhook in n8n)
        if data.get("type") == "url_verification":
            return JSONResponse({"challenge": data.get("challenge")})
        
        # Verify Slack signature
        if SLACK_SIGNING_SECRET:
            timestamp = headers.get("x-slack-request-timestamp")
            signature = headers.get("x-slack-signature")
            if not verify_slack_signature(body, timestamp, signature):
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Process event (Code2 - Bot loop detection)
        event = data.get("event", {})
        if event.get("bot_id") or event.get("user") == "U093TKM24AH":
            return JSONResponse({"status": "ignored"})  # Stop workflow for bot messages
        
        # Extract data (Code1)
        slack_user_id = event.get("user")
        channel = event.get("channel")
        
        # Handle different text extraction methods
        text = ""
        if event.get("text"):
            text = event.get("text", "")
        elif event.get("blocks"):
            # Extract text from blocks structure (from n8n workflow)
            try:
                blocks = event.get("blocks", [])
                if blocks and len(blocks) > 0:
                    elements = blocks[0].get("elements", [])
                    if elements and len(elements) > 0:
                        sub_elements = elements[0].get("elements", [])
                        if sub_elements and len(sub_elements) > 0:
                            text = sub_elements[0].get("text", "")
            except (IndexError, KeyError):
                text = ""
        
        if not all([slack_user_id, channel, text]):
            return JSONResponse({"status": "ignored"})
        
        # Get Slack user info (HTTP Request)
        slack_user_info = await get_slack_user_info(slack_user_id)
        
        # Get user profile from Supabase
        user_profile = await DatabaseManager.get_user_profile(slack_user_id)
        
        if not user_profile:
            # Create default profile if not found
            user_profile = UserProfile(
                slack_user_id=slack_user_id,
                full_name=slack_user_info.get("real_name", "Unknown User"),
                role="Employee",
                department="General",
                location="Remote",
                tool_access=["Slack"]
            )
        
        # Generate session ID (Code)
        session_id = f"slack-{slack_user_id}"
        
        # Process with AI Agent
        ai_response = await ai_agent.process_message(user_profile, text, session_id)
        
        # Send response to Slack (Code3 + Send a message)
        if slack_client:
            await slack_client.post(
                "https://slack.com/api/chat.postMessage",
                json={
                    "channel": channel,
                    "text": ai_response
                }
            )
        
        return JSONResponse({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/jira/test-connection")
async def test_jira_connection():
    """Test Jira connection"""
    if not jira_client:
        return {"success": False, "error": "Jira not configured"}
    
    try:
        response = await jira_client.get(f"{JIRA_URL}/rest/api/3/myself")
        if response.status_code == 200:
            user_info = response.json()
            return {
                "success": True,
                "user": user_info.get("displayName", "Unknown"),
                "email": user_info.get("emailAddress", "")
            }
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/jira/create-ticket")
async def create_jira_ticket_api(ticket_data: JiraTicketRequest):
    """Create Jira ticket via API"""
    result = await JiraManager.create_ticket(
        ticket_data.summary,
        ticket_data.description,
        ticket_data.issue_type
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@app.get("/jira/ticket/{ticket_key}")
async def get_jira_ticket_api(ticket_key: str):
    """Get Jira ticket status via API"""
    result = await JiraManager.get_ticket_status(ticket_key)
    
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result

@app.post("/vector-search")
async def vector_search_api(query: str, limit: int = 5):
    """Search knowledge base via API"""
    results = await VectorSearch.search_knowledge_base(query, limit)
    return {"results": results}

@app.post("/chat/test")
async def test_chat_api(message: str, user_id: str = "test_user"):
    """Test chat functionality"""
    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI not available")
    
    # Create test user profile
    test_profile = UserProfile(
        slack_user_id=user_id,
        full_name="Test User",
        role="Developer",
        department="Engineering",
        location="Remote",
        tool_access=["Slack", "Jira", "GitHub"]
    )
    
    session_id = f"test-{user_id}"
    response = await ai_agent.process_message(test_profile, message, session_id)
    
    return {
        "user_input": message,
        "ai_response": response,
        "session_id": session_id,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/chat/history/{session_id}")
async def get_chat_history_api(session_id: str, limit: int = 20):
    """Get chat history for a session"""
    history = await DatabaseManager.get_chat_history(session_id, limit)
    return {"session_id": session_id, "history": history}

@app.delete("/chat/reset/{session_id}")
async def reset_chat_session(session_id: str):
    """Reset chat session"""
    if postgres_pool:
        try:
            async with postgres_pool.acquire() as conn:
                await conn.execute("DELETE FROM chat_memory WHERE session_id = $1", session_id)
            return {"status": "reset", "session_id": session_id}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # Reset in-memory storage
        if session_id in chat_sessions:
            del chat_sessions[session_id]
        return {"status": "reset", "session_id": session_id}

@app.get("/stats/usage")
async def get_usage_stats():
    """Get detailed usage statistics"""
    stats = {
        "usage_stats": usage_stats,
        "total_tickets": len(jira_tickets_cache),
        "capabilities": {
            "postgres_available": POSTGRES_AVAILABLE,
            "embeddings_available": EMBEDDINGS_AVAILABLE,
            "services_connected": {
                "openai": bool(openai_client),
                "slack": bool(slack_client),
                "jira": bool(jira_client),
                "supabase": bool(supabase_client)
            }
        }
    }
    
    if postgres_pool:
        try:
            async with postgres_pool.acquire() as conn:
                # Get message counts by day
                daily_stats = await conn.fetch("""
                    SELECT DATE(created_at) as date, COUNT(*) as messages
                    FROM chat_memory 
                    WHERE message_type = 'human'
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                    LIMIT 30
                """)
                
                # Get total tickets created
                ticket_count = await conn.fetchval("SELECT COUNT(*) FROM jira_tickets")
                
                stats["daily_stats"] = [dict(row) for row in daily_stats]
                stats["total_tickets"] = ticket_count or 0
        except Exception as e:
            logger.error(f"Error fetching database stats: {e}")
    
    return stats

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting EnableBot SaaS (Minimal) on port {port}")
    logger.info(f"📦 PostgreSQL: {'Available' if POSTGRES_AVAILABLE else 'Not Available (using in-memory)'}")
    logger.info(f"🔍 Embeddings: {'Available' if EMBEDDINGS_AVAILABLE else 'Not Available (using text search)'}")
    uvicorn.run(app, host="0.0.0.0", port=port)