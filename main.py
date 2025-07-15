# main.py - EnableBot with Jira Integration
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
JIRA_URL = os.getenv("JIRA_URL")
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

# Slack HTTP client
slack_client = None
if SLACK_BOT_TOKEN:
    slack_client = httpx.AsyncClient(
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        timeout=30.0
    )
    logger.info("✅ Slack HTTP client initialized")

# Jira HTTP client
jira_client = None
jira_projects = []
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

# In-memory storage
chat_memory = {}
typing_tasks = {}
usage_stats = {
    "total_messages": 0,
    "total_tokens": 847000,
    "total_cost": 12.45,
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
    thread_ts: Optional[str] = None

class JiraConnectionRequest(BaseModel):
    jira_url: str
    email: str
    api_token: str

class JiraTicketRequest(BaseModel):
    project_key: str
    summary: str
    description: str
    issue_type: str = "Task"
    priority: str = "Medium"

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
- When users mention issues or problems, suggest creating a Jira ticket for tracking

You can now help create Jira tickets for:
- IT support requests
- Bug reports
- Feature requests
- Access requests
- General tasks and issues

You are designed to help with workplace questions and provide support for common business needs."""

    async def process_message(self, user_id: str, message: str) -> str:
        """Process message and generate AI response"""
        try:
            if not openai_client:
                return "I'm sorry, but I'm not able to access my AI capabilities right now. Please try again later or contact your IT support."

            # Check if message is about creating tickets
            ticket_keywords = ["ticket", "issue", "bug", "problem", "request", "help", "support", "broken", "not working"]
            if any(keyword in message.lower() for keyword in ticket_keywords) and jira_client:
                message += "\n\nNote: I can help you create a Jira ticket for this issue if needed. Just let me know!"

            # Get conversation history
            history = chat_memory.get(user_id, [])
            
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
            chat_memory[user_id] = history
            
            # Update usage stats
            update_usage_stats(response.usage.total_tokens, 0.003)
            
            return ai_response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return "I encountered an error while processing your request. Please try again, and if the problem persists, contact your IT support team."

class JiraIntegration:
    @staticmethod
    async def test_connection(jira_url: str, email: str, api_token: str) -> Dict[str, Any]:
        """Test Jira connection"""
        try:
            auth_string = f"{email}:{api_token}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{jira_url}/rest/api/3/myself",
                    headers={
                        "Authorization": f"Basic {encoded_auth}",
                        "Accept": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    user_info = response.json()
                    return {
                        "success": True,
                        "user": user_info.get("displayName", "Unknown"),
                        "email": user_info.get("emailAddress", email)
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Authentication failed: {response.status_code}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    async def get_projects() -> List[Dict[str, Any]]:
        """Get available Jira projects"""
        if not jira_client:
            return []
        
        try:
            response = await jira_client.get(f"{JIRA_URL}/rest/api/3/project")
            if response.status_code == 200:
                projects = response.json()
                return [
                    {
                        "key": project["key"],
                        "name": project["name"],
                        "id": project["id"]
                    }
                    for project in projects
                ]
            return []
        except Exception as e:
            logger.error(f"Error fetching projects: {e}")
            return []
    
    @staticmethod
    async def create_ticket(ticket_data: JiraTicketRequest) -> Dict[str, Any]:
        """Create a Jira ticket"""
        if not jira_client:
            return {"success": False, "error": "Jira not connected"}
        
        try:
            # Get project details first
            project_response = await jira_client.get(
                f"{JIRA_URL}/rest/api/3/project/{ticket_data.project_key}"
            )
            
            if project_response.status_code != 200:
                return {"success": False, "error": "Project not found"}
            
            # Create ticket payload
            ticket_payload = {
                "fields": {
                    "project": {"key": ticket_data.project_key},
                    "summary": ticket_data.summary,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": ticket_data.description
                                    }
                                ]
                            }
                        ]
                    },
                    "issuetype": {"name": ticket_data.issue_type},
                    "priority": {"name": ticket_data.priority}
                }
            }
            
            # Create the ticket
            response = await jira_client.post(
                f"{JIRA_URL}/rest/api/3/issue",
                json=ticket_payload
            )
            
            if response.status_code == 201:
                ticket = response.json()
                return {
                    "success": True,
                    "ticket_key": ticket["key"],
                    "ticket_url": f"{JIRA_URL}/browse/{ticket['key']}"
                }
            else:
                error_details = response.json() if response.status_code != 500 else {"error": "Server error"}
                return {
                    "success": False,
                    "error": f"Failed to create ticket: {error_details}"
                }
                
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def get_issue_types(project_key: str) -> List[Dict[str, Any]]:
        """Get available issue types for a project"""
        if not jira_client:
            return []
        
        try:
            response = await jira_client.get(
                f"{JIRA_URL}/rest/api/3/issue/createmeta?projectKeys={project_key}&expand=projects.issuetypes"
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("projects"):
                    issue_types = data["projects"][0].get("issuetypes", [])
                    return [
                        {
                            "id": issue_type["id"],
                            "name": issue_type["name"],
                            "description": issue_type.get("description", "")
                        }
                        for issue_type in issue_types
                    ]
            return []
        except Exception as e:
            logger.error(f"Error fetching issue types: {e}")
            return []

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
ai_agent = EnableBotAI()
slack_api = SlackAPI()

def update_usage_stats(tokens_used: int, cost: float):
    """Update usage statistics"""
    global usage_stats
    today = datetime.now().strftime("%Y-%m-%d")
    
    usage_stats["total_messages"] += 1
    usage_stats["total_tokens"] += tokens_used
    usage_stats["total_cost"] += cost
    
    if today not in usage_stats["daily_usage"]:
        usage_stats["daily_usage"][today] = {
            "messages": 0,
            "tokens": 0,
            "cost": 0.0
        }
    
    usage_stats["daily_usage"][today]["messages"] += 1
    usage_stats["daily_usage"][today]["tokens"] += tokens_used
    usage_stats["daily_usage"][today]["cost"] += cost

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

# Dashboard HTML with Jira Integration
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EnableBot Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #F8FAFC;
            color: #1E293B;
            line-height: 1.5;
        }

        .dashboard-layout {
            display: flex;
            min-height: 100vh;
        }

        .sidebar {
            width: 280px;
            background: #FFFFFF;
            border-right: 1px solid #E2E8F0;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
            position: fixed;
            height: 100vh;
            overflow-y: auto;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 1.5rem 1.5rem 2rem;
            font-size: 1.25rem;
            font-weight: 600;
            color: #1E293B;
            border-bottom: 1px solid #F1F5F9;
        }

        .logo-icon {
            width: 2rem;
            height: 2rem;
            background: linear-gradient(135deg, #3B82F6, #10B981);
            border-radius: 0.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 1rem;
        }

        .nav-menu {
            padding: 1rem 0;
        }

        .nav-section {
            margin-bottom: 2rem;
        }

        .nav-section-title {
            padding: 0 1.5rem 0.5rem;
            font-size: 0.75rem;
            font-weight: 600;
            color: #94A3B8;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .nav-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1.5rem;
            font-size: 0.875rem;
            font-weight: 500;
            color: #64748B;
            text-decoration: none;
            transition: all 0.2s ease;
            border-right: 3px solid transparent;
            cursor: pointer;
        }

        .nav-item:hover {
            background: #F8FAFC;
            color: #1E293B;
        }

        .nav-item.active {
            background: #F1F5F9;
            color: #3B82F6;
            border-right-color: #3B82F6;
        }

        .main-content {
            flex: 1;
            margin-left: 280px;
            padding: 2rem;
            max-width: calc(100vw - 280px);
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #E2E8F0;
        }

        .header-title {
            font-size: 2rem;
            font-weight: 600;
            color: #1E293B;
        }

        .header-subtitle {
            font-size: 0.875rem;
            color: #64748B;
            margin-top: 0.25rem;
        }

        .btn {
            padding: 0.75rem 1.5rem;
            border-radius: 0.5rem;
            font-size: 0.875rem;
            font-weight: 500;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }

        .btn-primary {
            background: #3B82F6;
            color: #FFFFFF;
        }

        .btn-primary:hover {
            background: #2563EB;
        }

        .btn-success {
            background: #10B981;
            color: #FFFFFF;
        }

        .btn-success:hover {
            background: #059669;
        }

        .btn-secondary {
            background: transparent;
            color: #64748B;
            border: 1px solid #E2E8F0;
        }

        .btn-secondary:hover {
            background: #F8FAFC;
            border-color: #CBD5E1;
        }

        .card {
            background: #FFFFFF;
            border-radius: 0.75rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
            border: 1px solid #E2E8F0;
            overflow: hidden;
            margin-bottom: 1.5rem;
        }

        .card-header {
            padding: 1.5rem 1.5rem 1rem;
            border-bottom: 1px solid #F1F5F9;
        }

        .card-title {
            font-size: 1.125rem;
            font-weight: 600;
            color: #1E293B;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .card-content {
            padding: 1.5rem;
        }

        .form-group {
            margin-bottom: 1rem;
        }

        .form-label {
            display: block;
            font-size: 0.875rem;
            font-weight: 500;
            color: #1E293B;
            margin-bottom: 0.5rem;
        }

        .form-input {
            width: 100%;
            padding: 0.75rem 1rem;
            border: 1px solid #E2E8F0;
            border-radius: 0.5rem;
            font-size: 0.875rem;
            transition: border-color 0.2s ease;
        }

        .form-input:focus {
            outline: none;
            border-color: #3B82F6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }

        .status-connected {
            color: #10B981;
            font-weight: 500;
        }

        .status-disconnected {
            color: #EF4444;
            font-weight: 500;
        }

        .section {
            display: none;
        }

        .section.active {
            display: block;
        }

        .grid {
            display: grid;
            gap: 1.5rem;
        }

        .grid-cols-2 {
            grid-template-columns: repeat(2, 1fr);
        }

        .grid-cols-3 {
            grid-template-columns: repeat(3, 1fr);
        }

        .alert {
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }

        .alert-success {
            background: #D1FAE5;
            color: #065F46;
            border: 1px solid #A7F3D0;
        }

        .alert-error {
            background: #FEE2E2;
            color: #991B1B;
            border: 1px solid #FECACA;
        }

        .hidden {
            display: none !important;
        }

        .modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }

        .modal-content {
            background: white;
            padding: 2rem;
            border-radius: 0.75rem;
            max-width: 500px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }

        .select {
            width: 100%;
            padding: 0.75rem 1rem;
            border: 1px solid #E2E8F0;
            border-radius: 0.5rem;
            font-size: 0.875rem;
            background: white;
        }

        .textarea {
            width: 100%;
            padding: 0.75rem 1rem;
            border: 1px solid #E2E8F0;
            border-radius: 0.5rem;
            font-size: 0.875rem;
            resize: vertical;
            min-height: 100px;
        }

        @media (max-width: 768px) {
            .main-content {
                margin-left: 0;
                max-width: 100vw;
            }
            
            .sidebar {
                transform: translateX(-100%);
            }
            
            .grid-cols-2,
            .grid-cols-3 {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="dashboard-layout">
        <!-- Sidebar -->
        <nav class="sidebar">
            <div class="logo">
                <div class="logo-icon">🤖</div>
                <span>EnableBot</span>
            </div>
            
            <div class="nav-menu">
                <div class="nav-section">
                    <div class="nav-section-title">Overview</div>
                    <div class="nav-item active" onclick="showSection('dashboard')">
                        <span>📊</span>
                        Dashboard
                    </div>
                </div>
                
                <div class="nav-section">
                    <div class="nav-section-title">Operations</div>
                    <div class="nav-item" onclick="showSection('conversations')">
                        <span>💬</span>
                        Test Chat
                    </div>
                    <div class="nav-item" onclick="showSection('jira')">
                        <span>🎫</span>
                        Jira Tickets
                    </div>
                </div>
                
                <div class="nav-section">
                    <div class="nav-section-title">Configuration</div>
                    <div class="nav-item" onclick="showSection('integrations')">
                        <span>🔗</span>
                        Integrations
                    </div>
                </div>
            </div>
        </nav>

        <!-- Main Content -->
        <main class="main-content">
            <div class="header">
                <div>
                    <h1 class="header-title" id="pageTitle">Dashboard</h1>
                    <p class="header-subtitle">Monitor and manage your AI assistant</p>
                </div>
                <div>
                    <button class="btn btn-secondary" onclick="refreshStats()">
                        <span>🔄</span> Refresh
                    </button>
                </div>
            </div>

            <!-- Dashboard Section -->
            <div id="dashboard" class="section active">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">🔧 System Status</h3>
                    </div>
                    <div class="card-content">
                        <div class="grid grid-cols-3">
                            <div>
                                <strong>OpenAI:</strong>
                                <span id="openaiStatus" class="status-disconnected">Loading...</span>
                            </div>
                            <div>
                                <strong>Slack:</strong>
                                <span id="slackStatus" class="status-disconnected">Loading...</span>
                            </div>
                            <div>
                                <strong>Jira:</strong>
                                <span id="jiraStatus" class="status-disconnected">Loading...</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Conversations Section -->
            <div id="conversations" class="section">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">💬 Test Conversation</h3>
                    </div>
                    <div class="card-content">
                        <div id="chatMessages" style="height: 400px; overflow-y: auto; border: 1px solid #E2E8F0; padding: 1rem; margin-bottom: 1rem; border-radius: 0.5rem;">
                            <div style="margin-bottom: 1rem;">
                                <strong>EnableBot:</strong> Hello! I'm your EnableOps Assistant. How can I help you today?
                            </div>
                        </div>
                        <div style="display: flex; gap: 0.75rem;">
                            <input type="text" id="messageInput" class="form-input" style="flex: 1;" 
                                   placeholder="Type your message..." onkeypress="handleKeyPress(event)">
                            <button class="btn btn-primary" onclick="sendMessage()">Send</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Jira Section -->
            <div id="jira" class="section">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">🎫 Jira Integration</h3>
                    </div>
                    <div class="card-content">
                        <div id="jiraConnectionStatus">
                            <p>Jira Status: <span id="jiraConnectionText" class="status-disconnected">Not Connected</span></p>
                            <button id="connectJiraBtn" class="btn btn-primary" onclick="showJiraConnectionModal()">
                                <span>🔗</span> Connect to Jira
                            </button>
                        </div>

                        <div id="jiraConnectedContent" class="hidden">
                            <div class="grid grid-cols-2">
                                <div>
                                    <h4>Create New Ticket</h4>
                                    <button class="btn btn-success" onclick="showCreateTicketModal()">
                                        <span>➕</span> Create Ticket
                                    </button>
                                </div>
                                <div>
                                    <h4>Projects Available</h4>
                                    <div id="projectsList"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Integrations Section -->
            <div id="integrations" class="section">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">🔗 Service Integrations</h3>
                    </div>
                    <div class="card-content">
                        <div class="grid grid-cols-2">
                            <div class="card">
                                <div class="card-content">
                                    <h4>🤖 OpenAI</h4>
                                    <p>Status: <span id="openaiIntegrationStatus">Loading...</span></p>
                                    <p style="font-size: 0.875rem; color: #64748B;">AI language model for responses</p>
                                </div>
                            </div>

                            <div class="card">
                                <div class="card-content">
                                    <h4>💬 Slack</h4>
                                    <p>Status: <span id="slackIntegrationStatus">Loading...</span></p>
                                    <p style="font-size: 0.875rem; color: #64748B;">Team communication platform</p>
                                </div>
                            </div>

                            <div class="card">
                                <div class="card-content">
                                    <h4>🎫 Jira</h4>
                                    <p>Status: <span id="jiraIntegrationStatus">Not Connected</span></p>
                                    <p style="font-size: 0.875rem; color: #64748B;">Issue tracking and project management</p>
                                    <button class="btn btn-primary" onclick="showJiraConnectionModal()" style="margin-top: 1rem;">
                                        Connect Jira
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <!-- Jira Connection Modal -->
    <div id="jiraConnectionModal" class="modal hidden">
        <div class="modal-content">
            <h3 style="margin-bottom: 1rem;">Connect to Jira</h3>
            
            <div id="connectionAlert" class="hidden"></div>
            
            <form id="jiraConnectionForm">
                <div class="form-group">
                    <label class="form-label">Jira URL</label>
                    <input type="url" id="jiraUrlInput" class="form-input" 
                           placeholder="https://your-company.atlassian.net" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Email Address</label>
                    <input type="email" id="jiraEmailInput" class="form-input" 
                           placeholder="your-email@company.com" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">API Token</label>
                    <input type="password" id="jiraTokenInput" class="form-input" 
                           placeholder="Your Jira API token" required>
                    <small style="color: #64748B; font-size: 0.75rem;">
                        Generate an API token in your Jira account settings
                    </small>
                </div>
                
                <div style="display: flex; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="submit" class="btn btn-primary">
                        <span id="connectButtonText">Connect</span>
                    </button>
                    <button type="button" class="btn btn-secondary" onclick="hideJiraConnectionModal()">
                        Cancel
                    </button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Ticket Modal -->
    <div id="createTicketModal" class="modal hidden">
        <div class="modal-content">
            <h3 style="margin-bottom: 1rem;">Create Jira Ticket</h3>
            
            <div id="ticketAlert" class="hidden"></div>
            
            <form id="createTicketForm">
                <div class="form-group">
                    <label class="form-label">Project</label>
                    <select id="projectSelect" class="select" required>
                        <option value="">Select a project...</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Issue Type</label>
                    <select id="issueTypeSelect" class="select" required>
                        <option value="Task">Task</option>
                        <option value="Bug">Bug</option>
                        <option value="Story">Story</option>
                        <option value="Epic">Epic</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Summary</label>
                    <input type="text" id="ticketSummary" class="form-input" 
                           placeholder="Brief description of the issue" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Description</label>
                    <textarea id="ticketDescription" class="textarea" 
                              placeholder="Detailed description of the issue" required></textarea>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Priority</label>
                    <select id="prioritySelect" class="select">
                        <option value="Low">Low</option>
                        <option value="Medium" selected>Medium</option>
                        <option value="High">High</option>
                        <option value="Highest">Highest</option>
                    </select>
                </div>
                
                <div style="display: flex; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="submit" class="btn btn-success">
                        <span id="createButtonText">Create Ticket</span>
                    </button>
                    <button type="button" class="btn btn-secondary" onclick="hideCreateTicketModal()">
                        Cancel
                    </button>
                </div>
            </form>
        </div>
    </div>

    <script>
        let jiraConnected = false;

        function showSection(sectionName) {
            // Hide all sections
            document.querySelectorAll('.section').forEach(section => {
                section.classList.remove('active');
            });
            
            // Remove active class from all nav items
            document.querySelectorAll('.nav-item').forEach(item => {
                item.classList.remove('active');
            });
            
            // Show selected section
            const section = document.getElementById(sectionName);
            if (section) {
                section.classList.add('active');
            }
            
            // Add active class to clicked nav item
            event.target.classList.add('active');
            
            // Update header title
            const pageTitle = document.getElementById('pageTitle');
            pageTitle.textContent = sectionName.charAt(0).toUpperCase() + sectionName.slice(1);
        }

        async function refreshStats() {
            try {
                const response = await fetch('/health');
                const data = await response.json();
                
                // Update status indicators
                updateStatusIndicator('openaiStatus', data.services.openai);
                updateStatusIndicator('slackStatus', data.services.slack);
                updateStatusIndicator('jiraStatus', data.services.jira || jiraConnected);
                
                // Update integration status
                updateStatusIndicator('openaiIntegrationStatus', data.services.openai);
                updateStatusIndicator('slackIntegrationStatus', data.services.slack);
                updateStatusIndicator('jiraIntegrationStatus', data.services.jira || jiraConnected);
                
            } catch (error) {
                console.error('Failed to refresh stats:', error);
            }
        }

        function updateStatusIndicator(elementId, isConnected) {
            const element = document.getElementById(elementId);
            if (element) {
                element.textContent = isConnected ? 'Connected' : 'Disconnected';
                element.className = isConnected ? 'status-connected' : 'status-disconnected';
            }
        }

        function showJiraConnectionModal() {
            document.getElementById('jiraConnectionModal').classList.remove('hidden');
        }

        function hideJiraConnectionModal() {
            document.getElementById('jiraConnectionModal').classList.add('hidden');
            document.getElementById('connectionAlert').classList.add('hidden');
        }

        function showCreateTicketModal() {
            document.getElementById('createTicketModal').classList.remove('hidden');
            loadProjects();
        }

        function hideCreateTicketModal() {
            document.getElementById('createTicketModal').classList.add('hidden');
            document.getElementById('ticketAlert').classList.add('hidden');
        }

        async function loadProjects() {
            try {
                const response = await fetch('/jira/projects');
                const projects = await response.json();
                
                const projectSelect = document.getElementById('projectSelect');
                projectSelect.innerHTML = '<option value="">Select a project...</option>';
                
                projects.forEach(project => {
                    const option = document.createElement('option');
                    option.value = project.key;
                    option.textContent = `${project.key} - ${project.name}`;
                    projectSelect.appendChild(option);
                });
            } catch (error) {
                console.error('Failed to load projects:', error);
            }
        }

        // Jira Connection Form Handler
        document.getElementById('jiraConnectionForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const connectButton = document.getElementById('connectButtonText');
            const originalText = connectButton.textContent;
            connectButton.textContent = 'Connecting...';
            
            const formData = {
                jira_url: document.getElementById('jiraUrlInput').value,
                email: document.getElementById('jiraEmailInput').value,
                api_token: document.getElementById('jiraTokenInput').value
            };
            
            try {
                const response = await fetch('/jira/connect', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(formData)
                });
                
                const result = await response.json();
                const alertDiv = document.getElementById('connectionAlert');
                
                if (result.success) {
                    alertDiv.className = 'alert alert-success';
                    alertDiv.textContent = `Successfully connected as ${result.user}`;
                    alertDiv.classList.remove('hidden');
                    
                    // Update UI
                    jiraConnected = true;
                    document.getElementById('jiraConnectionText').textContent = 'Connected';
                    document.getElementById('jiraConnectionText').className = 'status-connected';
                    document.getElementById('connectJiraBtn').textContent = '✅ Connected to Jira';
                    document.getElementById('jiraConnectedContent').classList.remove('hidden');
                    
                    // Hide modal after delay
                    setTimeout(() => {
                        hideJiraConnectionModal();
                        refreshStats();
                    }, 2000);
                } else {
                    alertDiv.className = 'alert alert-error';
                    alertDiv.textContent = `Connection failed: ${result.error}`;
                    alertDiv.classList.remove('hidden');
                }
            } catch (error) {
                const alertDiv = document.getElementById('connectionAlert');
                alertDiv.className = 'alert alert-error';
                alertDiv.textContent = `Connection error: ${error.message}`;
                alertDiv.classList.remove('hidden');
            }
            
            connectButton.textContent = originalText;
        });

        // Create Ticket Form Handler
        document.getElementById('createTicketForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const createButton = document.getElementById('createButtonText');
            const originalText = createButton.textContent;
            createButton.textContent = 'Creating...';
            
            const ticketData = {
                project_key: document.getElementById('projectSelect').value,
                issue_type: document.getElementById('issueTypeSelect').value,
                summary: document.getElementById('ticketSummary').value,
                description: document.getElementById('ticketDescription').value,
                priority: document.getElementById('prioritySelect').value
            };
            
            try {
                const response = await fetch('/jira/create-ticket', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(ticketData)
                });
                
                const result = await response.json();
                const alertDiv = document.getElementById('ticketAlert');
                
                if (result.success) {
                    alertDiv.className = 'alert alert-success';
                    alertDiv.innerHTML = `Ticket created successfully! <a href="${result.ticket_url}" target="_blank">${result.ticket_key}</a>`;
                    alertDiv.classList.remove('hidden');
                    
                    // Reset form
                    document.getElementById('createTicketForm').reset();
                    
                    setTimeout(() => {
                        hideCreateTicketModal();
                    }, 3000);
                } else {
                    alertDiv.className = 'alert alert-error';
                    alertDiv.textContent = `Failed to create ticket: ${result.error}`;
                    alertDiv.classList.remove('hidden');
                }
            } catch (error) {
                const alertDiv = document.getElementById('ticketAlert');
                alertDiv.className = 'alert alert-error';
                alertDiv.textContent = `Error creating ticket: ${error.message}`;
                alertDiv.classList.remove('hidden');
            }
            
            createButton.textContent = originalText;
        });

        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            
            if (!message) return;
            
            const chatMessages = document.getElementById('chatMessages');
            
            // Add user message
            const userDiv = document.createElement('div');
            userDiv.style.marginBottom = '1rem';
            userDiv.innerHTML = `<strong>You:</strong> ${message}`;
            chatMessages.appendChild(userDiv);
            
            input.value = '';
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            try {
                const response = await fetch('/test-ai', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message, user_id: 'dashboard_user' })
                });
                
                const data = await response.json();
                
                // Add bot response
                const botDiv = document.createElement('div');
                botDiv.style.marginBottom = '1rem';
                botDiv.innerHTML = `<strong>EnableBot:</strong> ${data.ai_response}`;
                chatMessages.appendChild(botDiv);
                
            } catch (error) {
                const errorDiv = document.createElement('div');
                errorDiv.style.marginBottom = '1rem';
                errorDiv.innerHTML = `<strong>EnableBot:</strong> Sorry, I encountered an error.`;
                chatMessages.appendChild(errorDiv);
            }
            
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }

        // Initialize
        refreshStats();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard"""
    return DASHBOARD_HTML

@app.get("/health")
async def health_check():
    """Enhanced health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": bool(openai_client),
            "slack": bool(slack_client),
            "jira": bool(jira_client)
        },
        "memory": {
            "active_conversations": len(chat_memory),
            "typing_indicators": len(typing_tasks)
        }
    }

@app.post("/jira/connect")
async def connect_jira_endpoint(connection_data: JiraConnectionRequest):
    """Connect to Jira with provided credentials"""
    global jira_client, JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN
    
    try:
        # Test connection
        result = await JiraIntegration.test_connection(
            connection_data.jira_url,
            connection_data.email,
            connection_data.api_token
        )
        
        if result["success"]:
            # Update global variables
            JIRA_URL = connection_data.jira_url.rstrip('/')
            JIRA_EMAIL = connection_data.email
            JIRA_API_TOKEN = connection_data.api_token
            
            # Reinitialize Jira client
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
            
            logger.info(f"✅ Jira connected successfully for {result['user']}")
            
        return result
        
    except Exception as e:
        logger.error(f"Error connecting to Jira: {e}")
        return {"success": False, "error": str(e)}

@app.get("/jira/projects")
async def get_jira_projects():
    """Get available Jira projects"""
    if not jira_client:
        raise HTTPException(status_code=400, detail="Jira not connected")
    
    projects = await JiraIntegration.get_projects()
    return projects

@app.post("/jira/create-ticket")
async def create_jira_ticket(ticket_data: JiraTicketRequest):
    """Create a new Jira ticket"""
    if not jira_client:
        raise HTTPException(status_code=400, detail="Jira not connected")
    
    result = await JiraIntegration.create_ticket(ticket_data)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    logger.info(f"✅ Jira ticket created: {result['ticket_key']}")
    return result

@app.get("/jira/issue-types/{project_key}")
async def get_issue_types(project_key: str):
    """Get available issue types for a project"""
    if not jira_client:
        raise HTTPException(status_code=400, detail="Jira not connected")
    
    issue_types = await JiraIntegration.get_issue_types(project_key)
    return issue_types

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
            
            if not verify_slack_signature(body, timestamp, signature):
                logger.error("❌ Invalid Slack signature")
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Handle events
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            
            # Skip bot messages
            if (event.get("bot_id") or 
                event.get("subtype") in ["bot_message", "file_share", "message_changed"]):
                return JSONResponse({"status": "ignored"})
            
            if event.get("type") == "message":
                channel = event.get("channel")
                user = event.get("user")
                text = event.get("text", "").strip()
                
                if all([channel, user, text]):
                    asyncio.create_task(process_slack_message(channel, user, text))
        
        return JSONResponse({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def process_slack_message(channel: str, user: str, text: str):
    """Process Slack message with typing indicator"""
    try:
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
        await slack_api.send_message(
            channel, 
            "I'm sorry, I encountered an error processing your message. Please try again."
        )

@app.post("/test-ai")
async def test_ai(request: Request):
    """Test AI functionality directly"""
    try:
        if not openai_client:
            raise HTTPException(
                status_code=503, 
                detail="OpenAI service not available. Please check API key."
            )
        
        body = await request.json()
        message = body.get("message")
        user_id = body.get("user_id", "test_user")
        
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        response = await ai_agent.process_message(user_id, message)
        return {
            "user_input": message,
            "ai_response": response,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/reset")
async def reset_memory():
    """Reset chat memory"""
    global chat_memory, typing_tasks
    chat_memory.clear()
    typing_tasks.clear()
    return {"status": "memory_reset", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting EnableBot with Jira Integration on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)