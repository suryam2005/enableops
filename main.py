# main.py - EnableBot with Dashboard Integration
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
import asyncio
import logging
import time
import json
import hmac
import hashlib
from datetime import datetime, timedelta
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
POSTGRES_URL = os.getenv("POSTGRES_URL")
JIRA_URL = os.getenv("JIRA_URL")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")

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

# PostgreSQL client (placeholder for future implementation)
postgres_client = None
if POSTGRES_URL:
    try:
        # import asyncpg
        # postgres_client = await asyncpg.connect(POSTGRES_URL)
        logger.info("✅ PostgreSQL client ready (not implemented yet)")
    except Exception as e:
        logger.error(f"❌ Failed to initialize PostgreSQL: {e}")

# Jira client (placeholder for future implementation)
jira_client = None
if JIRA_URL and JIRA_TOKEN:
    try:
        # from jira import JIRA
        # jira_client = JIRA(server=JIRA_URL, token_auth=JIRA_TOKEN)
        logger.info("✅ Jira client ready (not implemented yet)")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Jira: {e}")

# In-memory storage (replace with database later)
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
            
            # Update usage stats
            update_usage_stats(response.usage.total_tokens, 0.003)
            
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

# Dashboard HTML content
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

        /* Sidebar */
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

        .nav-icon {
            width: 1.25rem;
            height: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        /* Main Content */
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

        .header-actions {
            display: flex;
            gap: 0.75rem;
            align-items: center;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
        }

        .status-online {
            background: #DCFCE7;
            color: #15803D;
        }

        .status-offline {
            background: #FEE2E2;
            color: #DC2626;
        }

        .status-dot {
            width: 0.5rem;
            height: 0.5rem;
            border-radius: 50%;
            background: currentColor;
        }

        /* Buttons */
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
            background: #1E293B;
            color: #FFFFFF;
        }

        .btn-primary:hover {
            background: #334155;
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

        /* Grid Layout */
        .grid {
            display: grid;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        .grid-cols-1 { grid-template-columns: 1fr; }
        .grid-cols-2 { grid-template-columns: repeat(2, 1fr); }
        .grid-cols-3 { grid-template-columns: repeat(3, 1fr); }
        .grid-cols-4 { grid-template-columns: repeat(4, 1fr); }

        /* Cards */
        .card {
            background: #FFFFFF;
            border-radius: 0.75rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
            border: 1px solid #E2E8F0;
            overflow: hidden;
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

        .card-subtitle {
            font-size: 0.875rem;
            color: #64748B;
            margin-top: 0.25rem;
        }

        .card-content {
            padding: 1.5rem;
        }

        .card-footer {
            padding: 1rem 1.5rem;
            background: #F8FAFC;
            border-top: 1px solid #F1F5F9;
        }

        /* Metrics */
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 0;
            border-bottom: 1px solid #F1F5F9;
        }

        .metric:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }

        .metric-label {
            font-size: 0.875rem;
            color: #64748B;
            font-weight: 500;
        }

        .metric-value {
            font-size: 1.125rem;
            font-weight: 600;
            color: #1E293B;
        }

        .metric-large .metric-value {
            font-size: 2rem;
            line-height: 1.2;
        }

        .metric-change {
            font-size: 0.875rem;
            font-weight: 500;
            margin-top: 0.25rem;
        }

        .metric-change.positive { color: #10B981; }
        .metric-change.negative { color: #EF4444; }

        /* Input */
        .input {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 0.5rem;
            padding: 0.75rem 1rem;
            font-size: 0.875rem;
            color: #1E293B;
            transition: all 0.2s ease;
            width: 100%;
        }

        .input:focus {
            outline: none;
            border-color: #3B82F6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }

        .input::placeholder {
            color: #94A3B8;
        }

        /* Chat */
        .chat-container {
            display: flex;
            flex-direction: column;
            height: 600px;
        }

        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
            background: #F8FAFC;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }

        .message {
            margin-bottom: 1rem;
            max-width: 80%;
            animation: fadeIn 0.3s ease;
        }

        .message.user {
            margin-left: auto;
        }

        .message-bubble {
            padding: 1rem;
            border-radius: 1rem;
            font-size: 0.875rem;
            line-height: 1.5;
        }

        .message.user .message-bubble {
            background: #3B82F6;
            color: white;
            border-bottom-right-radius: 0.5rem;
        }

        .message.bot .message-bubble {
            background: #FFFFFF;
            color: #1E293B;
            border: 1px solid #E2E8F0;
            border-bottom-left-radius: 0.5rem;
        }

        .message-header {
            font-size: 0.75rem;
            color: #64748B;
            margin-bottom: 0.5rem;
            font-weight: 500;
        }

        .chat-input-container {
            display: flex;
            gap: 0.75rem;
            align-items: flex-end;
        }

        .chat-input {
            flex: 1;
        }

        /* Loading */
        .loading {
            display: inline-block;
            width: 1rem;
            height: 1rem;
            border: 2px solid #E2E8F0;
            border-top: 2px solid #3B82F6;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(0.5rem); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Responsive */
        @media (max-width: 1024px) {
            .sidebar {
                transform: translateX(-100%);
                transition: transform 0.3s ease;
            }
            
            .sidebar.open {
                transform: translateX(0);
            }
            
            .main-content {
                margin-left: 0;
                max-width: 100vw;
            }
            
            .grid-cols-4 {
                grid-template-columns: repeat(2, 1fr);
            }
        }

        @media (max-width: 768px) {
            .main-content {
                padding: 1rem;
            }
            
            .header {
                flex-direction: column;
                align-items: flex-start;
                gap: 1rem;
            }
            
            .grid-cols-2,
            .grid-cols-3,
            .grid-cols-4 {
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
                    <a href="#" class="nav-item active" onclick="showSection('dashboard')">
                        <span class="nav-icon">📊</span>
                        Dashboard
                    </a>
                </div>
                
                <div class="nav-section">
                    <div class="nav-section-title">Operations</div>
                    <a href="#" class="nav-item" onclick="showSection('conversations')">
                        <span class="nav-icon">💬</span>
                        Test Chat
                    </a>
                </div>
                
                <div class="nav-section">
                    <div class="nav-section-title">Configuration</div>
                    <a href="#" class="nav-item" onclick="showSection('integrations')">
                        <span class="nav-icon">🔗</span>
                        Integrations
                    </a>
                    <a href="#" class="nav-item" onclick="showSection('billing')">
                        <span class="nav-icon">💳</span>
                        Billing & Usage
                    </a>
                </div>
            </div>
        </nav>

        <!-- Main Content -->
        <main class="main-content">
            <div class="header">
                <div>
                    <h1 class="header-title">Dashboard</h1>
                    <p class="header-subtitle">Monitor and manage your AI assistant</p>
                </div>
                <div class="header-actions">
                    <div class="status-badge status-online" id="systemStatus">
                        <div class="status-dot"></div>
                        System Online
                    </div>
                    <button class="btn btn-secondary" onclick="refreshStats()">
                        <span>🔄</span> Refresh
                    </button>
                </div>
            </div>

            <!-- Dashboard Section -->
            <div id="dashboard" class="section">
                <div class="grid grid-cols-4">
                    <div class="card">
                        <div class="card-content">
                            <div class="metric metric-large">
                                <div>
                                    <div class="metric-label">Active Sessions</div>
                                    <div class="metric-value" id="activeSessions">0</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <div class="card-content">
                            <div class="metric metric-large">
                                <div>
                                    <div class="metric-label">Total Messages</div>
                                    <div class="metric-value" id="totalMessages">0</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <div class="card-content">
                            <div class="metric metric-large">
                                <div>
                                    <div class="metric-label">Total Cost</div>
                                    <div class="metric-value" id="totalCost">$0.00</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <div class="card-content">
                            <div class="metric metric-large">
                                <div>
                                    <div class="metric-label">Uptime</div>
                                    <div class="metric-value" id="uptime">0h 0m</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-2">
                    <div class="card">
                        <div class="card-header">
                            <h3 class="card-title">🔧 System Health</h3>
                        </div>
                        <div class="card-content">
                            <div class="metric">
                                <span class="metric-label">OpenAI API</span>
                                <span class="metric-value" id="openaiStatus">Loading...</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Slack Integration</span>
                                <span class="metric-value" id="slackStatus">Loading...</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">PostgreSQL</span>
                                <span class="metric-value" id="postgresStatus">Not Connected</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Jira</span>
                                <span class="metric-value" id="jiraStatus">Not Connected</span>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <div class="card-header">
                            <h3 class="card-title">📈 Quick Stats</h3>
                        </div>
                        <div class="card-content">
                            <div class="metric">
                                <span class="metric-label">Total Tokens Used</span>
                                <span class="metric-value" id="totalTokens">0</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Avg Response Time</span>
                                <span class="metric-value">~2.1s</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Success Rate</span>
                                <span class="metric-value">98.5%</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Test Chat Section -->
            <div id="conversations" class="section" style="display: none;">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">💬 Test Conversation</h3>
                        <p class="card-subtitle">Test your bot's responses in real-time</p>
                    </div>
                    <div class="card-content">
                        <div class="chat-container">
                            <div class="chat-messages" id="chatMessages">
                                <div class="message bot">
                                    <div class="message-header">EnableBot • Just now</div>
                                    <div class="message-bubble">
                                        Hello! I'm your EnableOps Assistant. How can I help you today?
                                    </div>
                                </div>
                            </div>
                            <div class="chat-input-container">
                                <input type="text" class="input chat-input" id="messageInput" 
                                       placeholder="Type your message here..." 
                                       onkeypress="handleKeyPress(event)">
                                <button class="btn btn-primary" onclick="sendMessage()">
                                    Send
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Integrations Section -->
            <div id="integrations" class="section" style="display: none;">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">🔗 Service Integrations</h3>
                        <p class="card-subtitle">Manage connections to external services</p>
                    </div>
                    <div class="card-content">
                        <div class="grid grid-cols-2">
                            <div class="card">
                                <div class="card-content">
                                    <div class="metric">
                                        <span class="metric-label">🤖 OpenAI</span>
                                        <span class="metric-value" id="openaiStatusDetail">Connected</span>
                                    </div>
                                    <p style="font-size: 0.875rem; color: #64748B; margin-top: 0.5rem;">
                                        AI language model for generating responses
                                    </p>
                                </div>
                            </div>

                            <div class="card">
                                <div class="card-content">
                                    <div class="metric">
                                        <span class="metric-label">💬 Slack</span>
                                        <span class="metric-value" id="slackStatusDetail">Connected</span>
                                    </div>
                                    <p style="font-size: 0.875rem; color: #64748B; margin-top: 0.5rem;">
                                        Team communication platform
                                    </p>
                                </div>
                            </div>

                            <div class="card">
                                <div class="card-content">
                                    <div class="metric">
                                        <span class="metric-label">🗄️ PostgreSQL</span>
                                        <span class="metric-value">Not Connected</span>
                                    </div>
                                    <p style="font-size: 0.875rem; color: #64748B; margin-top: 0.5rem;">
                                        Persistent data storage for conversations
                                    </p>
                                    <button class="btn btn-primary" style="margin-top: 1rem; font-size: 0.75rem; padding: 0.5rem 1rem;">
                                        Connect Database
                                    </button>
                                </div>
                            </div>

                            <div class="card">
                                <div class="card-content">
                                    <div class="metric">
                                        <span class="metric-label">🎫 Jira</span>
                                        <span class="metric-value">Not Connected</span>
                                    </div>
                                    <p style="font-size: 0.875rem; color: #64748B; margin-top: 0.5rem;">
                                        Issue tracking and project management
                                    </p>
                                    <button class="btn btn-primary" style="margin-top: 1rem; font-size: 0.75rem; padding: 0.5rem 1rem;">
                                        Connect Jira
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Billing Section -->
            <div id="billing" class="section" style="display: none;">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">💳 Usage & Billing</h3>
                        <p class="card-subtitle">Monitor your API usage and costs</p>
                    </div>
                    <div class="card-content">
                        <div class="grid grid-cols-4">
                            <div class="metric metric-large">
                                <div>
                                    <div class="metric-label">This Month</div>
                                    <div class="metric-value" id="monthlySpend">$0.00</div>
                                </div>
                            </div>
                            <div class="metric metric-large">
                                <div>
                                    <div class="metric-label">Total Tokens</div>
                                    <div class="metric-value" id="billingTokens">0</div>
                                </div>
                            </div>
                            <div class="metric metric-large">
                                <div>
                                    <div class="metric-label">API Calls</div>
                                    <div class="metric-value" id="apiCalls">0</div>
                                </div>
                            </div>
                            <div class="metric metric-large">
                                <div>
                                    <div class="metric-label">Avg Cost/Day</div>
                                    <div class="metric-value" id="avgDailyCost">$0.00</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-2">
                    <div class="card">
                        <div class="card-header">
                            <h3 class="card-title">📊 OpenAI Usage</h3>
                        </div>
                        <div class="card-content">
                            <div class="metric">
                                <span class="metric-label">Model</span>
                                <span class="metric-value">GPT-4o-mini</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Total Cost</span>
                                <span class="metric-value" id="openaiCost">$0.00</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Rate per 1K tokens</span>
                                <span class="metric-value">$0.000075</span>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <div class="card-header">
                            <h3 class="card-title">🔧 Infrastructure</h3>
                        </div>
                        <div class="card-content">
                            <div class="metric">
                                <span class="metric-label">Hosting (Railway)</span>
                                <span class="metric-value">$0.00</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Database</span>
                                <span class="metric-value">$0.00</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Total Infrastructure</span>
                                <span class="metric-value">$0.00</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        let startTime = new Date();

        function showSection(sectionName) {
            document.querySelectorAll('.section').forEach(section => {
                section.style.display = 'none';
            });
            
            document.querySelectorAll('.nav-item').forEach(item => {
                item.classList.remove('active');
            });
            
            const section = document.getElementById(sectionName);
            if (section) {
                section.style.display = 'block';
            }
            
            event.target.classList.add('active');
            
            const headerTitle = document.querySelector('.header-title');
            headerTitle.textContent = sectionName.charAt(0).toUpperCase() + sectionName.slice(1);
        }

        function updateUptime() {
            const now = new Date();
            const diff = now - startTime;
            const hours = Math.floor(diff / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            document.getElementById('uptime').textContent = `${hours}h ${minutes}m`;
        }

        async function refreshStats() {
            try {
                const response = await fetch('/health');
                const data = await response.json();
                
                document.getElementById('openaiStatus').textContent = data.services.openai ? 'Connected' : 'Disconnected';
                document.getElementById('slackStatus').textContent = data.services.slack ? 'Connected' : 'Disconnected';
                document.getElementById('activeSessions').textContent = data.memory.active_conversations;
                
                // Update detailed status
                document.getElementById('openaiStatusDetail').textContent = data.services.openai ? 'Connected' : 'Disconnected';
                document.getElementById('slackStatusDetail').textContent = data.services.slack ? 'Connected' : 'Disconnected';
                
                const usageResponse = await fetch('/usage-stats');
                const usageData = await usageResponse.json();
                
                document.getElementById('totalMessages').textContent = usageData.total_messages.toLocaleString();
                document.getElementById('totalCost').textContent = `${usageData.total_cost.toFixed(2)}`;
                document.getElementById('totalTokens').textContent = usageData.total_tokens.toLocaleString();
                
                // Update billing section
                document.getElementById('monthlySpend').textContent = `${usageData.total_cost.toFixed(2)}`;
                document.getElementById('billingTokens').textContent = usageData.total_tokens.toLocaleString();
                document.getElementById('apiCalls').textContent = usageData.total_messages.toLocaleString();
                document.getElementById('openaiCost').textContent = `${usageData.total_cost.toFixed(2)}`;
                
                const avgDaily = usageData.total_cost / Math.max(1, Object.keys(usageData.daily_usage || {}).length);
                document.getElementById('avgDailyCost').textContent = `${avgDaily.toFixed(2)}`;
                
                // Update system status
                const statusBadge = document.getElementById('systemStatus');
                if (data.services.openai && data.services.slack) {
                    statusBadge.innerHTML = '<div class="status-dot"></div>System Online';
                    statusBadge.className = 'status-badge status-online';
                } else {
                    statusBadge.innerHTML = '<div class="status-dot"></div>Partial Service';
                    statusBadge.className = 'status-badge status-offline';
                }
                
            } catch (error) {
                console.error('Failed to refresh stats:', error);
            }
        }

        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            
            if (!message) return;
            
            const chatMessages = document.getElementById('chatMessages');
            
            // Add user message
            const userMessage = document.createElement('div');
            userMessage.className = 'message user';
            userMessage.innerHTML = `
                <div class="message-header">You • Just now</div>
                <div class="message-bubble">${message}</div>
            `;
            chatMessages.appendChild(userMessage);
            
            // Add loading indicator
            const loadingMessage = document.createElement('div');
            loadingMessage.className = 'message bot';
            loadingMessage.innerHTML = `
                <div class="message-header">EnableBot • <span class="loading"></span></div>
                <div class="message-bubble">Thinking...</div>
            `;
            chatMessages.appendChild(loadingMessage);
            
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
                
                // Remove loading message
                chatMessages.removeChild(loadingMessage);
                
                // Add bot response
                const botMessage = document.createElement('div');
                botMessage.className = 'message bot';
                botMessage.innerHTML = `
                    <div class="message-header">EnableBot • Just now</div>
                    <div class="message-bubble">${data.ai_response}</div>
                `;
                chatMessages.appendChild(botMessage);
                
                // Refresh stats to show updated usage
                await refreshStats();
                
            } catch (error) {
                // Remove loading message
                chatMessages.removeChild(loadingMessage);
                
                // Add error message
                const errorMessage = document.createElement('div');
                errorMessage.className = 'message bot';
                errorMessage.innerHTML = `
                    <div class="message-header">EnableBot • Error</div>
                    <div class="message-bubble">Sorry, I encountered an error processing your message.</div>
                `;
                chatMessages.appendChild(errorMessage);
            }
            
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }

        // Initialize
        setInterval(updateUptime, 1000);
        setInterval(refreshStats, 30000);
        refreshStats();
        updateUptime();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard"""
    return DASHBOARD_HTML

@app.get("/dashboard", response_class=HTMLResponse) 
async def dashboard_alt():
    """Alternative dashboard route"""
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
            "postgres": bool(postgres_client),
            "jira": bool(jira_client)
        },
        "memory": {
            "active_conversations": len(chat_memory),
            "typing_indicators": len(typing_tasks)
        },
        "uptime": {
            "start_time": usage_stats["start_time"].isoformat(),
            "seconds": (datetime.now() - usage_stats["start_time"]).total_seconds()
        }
    }

@app.get("/usage-stats")
async def get_usage_stats():
    """Get usage statistics for billing dashboard"""
    return {
        "total_messages": usage_stats["total_messages"],
        "total_tokens": usage_stats["total_tokens"],
        "total_cost": usage_stats["total_cost"],
        "daily_usage": usage_stats["daily_usage"],
        "start_time": usage_stats["start_time"].isoformat(),
        "current_month": datetime.now().strftime("%Y-%m"),
        "infrastructure_cost": 0.0  # Placeholder for Railway/other costs
    }

@app.post("/slack/events")
async def handle_slack_events(request: Request):
    """Handle Slack events via HTTP webhooks"""
    try:
        # Log that we received ANY request to this endpoint
        logger.info("🎯 SLACK EVENT ENDPOINT HIT!")
        
        # Get request body and headers
        body = await request.body()
        headers = request.headers
        
        logger.info(f"📦 Request body length: {len(body)}")
        logger.info(f"📋 Headers: {dict(headers)}")
        
        # Parse request first
        try:
            data = json.loads(body.decode())
            logger.info(f"📄 Parsed JSON: {data}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Log all incoming requests for debugging
        logger.info(f"📩 Received Slack event: {data.get('type', 'unknown')}")
        
        # Handle URL verification FIRST (before signature check)
        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            logger.info(f"✅ URL verification challenge: {challenge}")
            return JSONResponse({"challenge": challenge})
        
        # Verify signature for other requests
        if SLACK_SIGNING_SECRET:
            timestamp = headers.get("x-slack-request-timestamp")
            signature = headers.get("x-slack-signature")
            
            if not verify_slack_signature(body, timestamp, signature):
                logger.error("❌ Invalid Slack signature")
                raise HTTPException(status_code=401, detail="Invalid signature")
        else:
            logger.warning("⚠️ No SLACK_SIGNING_SECRET - skipping signature verification")
        
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
            
            # Handle DM messages
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

@app.get("/debug")
async def debug_info():
    """Debug endpoint"""
    return {
        "environment": {
            "openai_key_set": bool(OPENAI_API_KEY),
            "slack_token_set": bool(SLACK_BOT_TOKEN),
            "slack_secret_set": bool(SLACK_SIGNING_SECRET),
            "postgres_url_set": bool(POSTGRES_URL),
            "jira_url_set": bool(JIRA_URL)
        },
        "services": {
            "openai_client": bool(openai_client),
            "slack_client": bool(slack_client),
            "postgres_client": bool(postgres_client),
            "jira_client": bool(jira_client)
        },
        "memory": {
            "chat_sessions": len(chat_memory),
            "active_typing": len(typing_tasks)
        },
        "usage": usage_stats
    }

@app.delete("/reset")
async def reset_memory():
    """Reset chat memory (for testing)"""
    global chat_memory, typing_tasks
    chat_memory.clear()
    typing_tasks.clear()
    return {"status": "memory_reset", "timestamp": datetime.now().isoformat()}

# Integration endpoints for future PostgreSQL and Jira setup
@app.post("/integrations/postgres/connect")
async def connect_postgres():
    """Connect to PostgreSQL database"""
    # TODO: Implement PostgreSQL connection
    return {"status": "not_implemented", "message": "PostgreSQL integration coming soon"}

@app.post("/integrations/jira/connect") 
async def connect_jira():
    """Connect to Jira"""
    # TODO: Implement Jira connection
    return {"status": "not_implemented", "message": "Jira integration coming soon"}

@app.get("/integrations/status")
async def integration_status():
    """Get status of all integrations"""
    return {
        "openai": {
            "status": "connected" if openai_client else "disconnected",
            "model": "gpt-4o-mini" if openai_client else None
        },
        "slack": {
            "status": "connected" if slack_client else "disconnected",
            "bot_token_set": bool(SLACK_BOT_TOKEN)
        },
        "postgres": {
            "status": "ready" if POSTGRES_URL else "not_configured",
            "connected": bool(postgres_client)
        },
        "jira": {
            "status": "ready" if (JIRA_URL and JIRA_TOKEN) else "not_configured", 
            "connected": bool(jira_client)
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting EnableBot with Dashboard on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)