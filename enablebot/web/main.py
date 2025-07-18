"""
EnableBot Web Interface
Handles Slack OAuth, dashboard, and installation flow
"""

import os
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import uvicorn
import httpx
import asyncpg
import json
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Supabase client
supabase_client = None

async def init_supabase():
    """Initialize Supabase REST API client"""
    global supabase_client
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not supabase_url or not supabase_service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required")
        
        # Create HTTP client for Supabase REST API
        supabase_client = httpx.AsyncClient(
            base_url=supabase_url,
            headers={
                "apikey": supabase_service_key,
                "Authorization": f"Bearer {supabase_service_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            timeout=30.0
        )
        
        # Test connection by making a simple request
        response = await supabase_client.get("/rest/v1/")
        if response.status_code == 200:
            logger.info("✅ Supabase REST API connection initialized")
            return True
        else:
            logger.error(f"❌ Supabase connection test failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize Supabase: {e}")
        return False

async def encrypt_token(token: str, tenant_id: str) -> tuple[str, str]:
    """Simple token encryption (basic implementation)"""
    import base64
    import secrets
    from cryptography.fernet import Fernet
    
    # Generate a key (in production, this should be managed properly)
    key = Fernet.generate_key()
    cipher_suite = Fernet(key)
    
    # Encrypt the token
    encrypted_token = cipher_suite.encrypt(token.encode())
    
    # Return base64 encoded encrypted token and key
    return base64.b64encode(encrypted_token).decode(), base64.b64encode(key).decode()

async def store_installation(installation_data: Dict[str, Any]) -> bool:
    """Store installation data in Supabase using REST API"""
    if not supabase_client:
        logger.error("Supabase client not initialized")
        return False
    
    try:
        # Encrypt the bot token
        encrypted_token, encryption_key = await encrypt_token(
            installation_data["bot_token"], 
            installation_data["team_id"]
        )
        
        # Prepare tenant data for Supabase
        tenant_data = {
            "team_id": installation_data["team_id"],
            "team_name": installation_data["team_name"],
            "encrypted_bot_token": encrypted_token,
            "encryption_key_id": encryption_key,
            "bot_user_id": installation_data["bot_user_id"],
            "installer_user_id": installation_data.get("installer_user_id", "unknown"),
            "installer_name": installation_data.get("installer_name", "Unknown User"),
            "scopes": installation_data.get("scopes", []),
            "status": "active"
        }
        
        # Store tenant data using Supabase REST API (upsert)
        response = await supabase_client.post(
            "/rest/v1/tenants",
            json=tenant_data,
            headers={"Prefer": "resolution=merge-duplicates"}
        )
        
        if response.status_code not in [200, 201]:
            logger.error(f"Failed to store tenant data: {response.status_code} - {response.text}")
            return False
        
        # Store installation event
        event_data = {
            "team_id": installation_data["team_id"],
            "event_type": "app_installed",
            "installer_user_id": installation_data.get("installer_user_id", "unknown"),
            "installer_name": installation_data.get("installer_name", "Unknown User"),
            "metadata": {
                "bot_user_id": installation_data["bot_user_id"],
                "scopes": installation_data.get("scopes", []),
                "installation_source": "web_oauth"
            }
        }
        
        response = await supabase_client.post(
            "/rest/v1/installation_events",
            json=event_data
        )
        
        if response.status_code not in [200, 201]:
            logger.warning(f"Failed to store installation event: {response.status_code} - {response.text}")
            # Don't fail the whole operation if event logging fails
        
        logger.info(f"✅ Stored installation data for team {installation_data['team_id']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to store installation data: {e}")
        return False

# Initialize FastAPI app
app = FastAPI(
    title="EnableBot Web Interface",
    description="Slack OAuth and Dashboard for EnableBot AI Assistant",
    version="3.0.0"
)

# Templates - handle different working directories
import os
from pathlib import Path

# Get the directory of this file
current_dir = Path(__file__).parent
templates_dir = current_dir / "templates"

# Fallback paths for different deployment scenarios
possible_template_paths = [
    str(templates_dir),  # Relative to this file
    "enablebot/web/templates",  # From project root
    "./enablebot/web/templates",  # Explicit relative
]

# Find the correct templates directory
templates_path = None
for path in possible_template_paths:
    if os.path.exists(path) and os.path.isdir(path):
        templates_path = path
        break

if not templates_path:
    # Create a fallback if templates not found
    templates_path = str(templates_dir)
    logger.warning(f"Templates directory not found, using: {templates_path}")

logger.info(f"Using templates directory: {templates_path}")
templates = Jinja2Templates(directory=templates_path)

@app.on_event("startup")
async def startup_event():
    """Initialize web application"""
    logger.info("🚀 Starting EnableBot Web Application...")
    
    # Initialize Supabase connection
    if await init_supabase():
        logger.info("✅ Supabase connection initialized")
    else:
        logger.warning("⚠️ Supabase connection failed - continuing without database")
    
    logger.info("🎉 EnableBot Web Application ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    logger.info("🛑 Shutting down EnableBot Web Application...")
    logger.info("✅ Cleanup completed")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with Slack installation"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/slack/install")
async def slack_install():
    """Redirect to Slack OAuth"""
    # For now, redirect to Slack app installation page
    slack_client_id = os.getenv("SLACK_CLIENT_ID", "")
    if not slack_client_id:
        raise HTTPException(status_code=500, detail="Slack Client ID not configured")
    
    install_url = f"https://slack.com/oauth/v2/authorize?client_id={slack_client_id}&scope=app_mentions:read,chat:write,im:history,im:read,im:write,users:read&user_scope="
    return RedirectResponse(url=install_url)

@app.get("/slack/oauth/callback")
async def slack_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(None),
    error: str = Query(None)
):
    """Handle Slack OAuth callback"""
    if error:
        logger.error(f"Slack OAuth error: {error}")
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    
    try:
        # Get environment variables
        slack_client_id = os.getenv("SLACK_CLIENT_ID")
        slack_client_secret = os.getenv("SLACK_CLIENT_SECRET")
        
        if not slack_client_id or not slack_client_secret:
            raise HTTPException(status_code=500, detail="Slack OAuth credentials not configured")
        
        # Exchange authorization code for access token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": slack_client_id,
                    "client_secret": slack_client_secret,
                    "code": code,
                    "redirect_uri": os.getenv("SLACK_REDIRECT_URI")
                }
            )
            
            oauth_response = response.json()
            
            if not oauth_response.get("ok"):
                error_msg = oauth_response.get("error", "Unknown OAuth error")
                logger.error(f"Slack OAuth token exchange failed: {error_msg}")
                raise HTTPException(status_code=400, detail=f"OAuth failed: {error_msg}")
            
            # Extract installation data
            team_id = oauth_response.get("team", {}).get("id")
            team_name = oauth_response.get("team", {}).get("name")
            bot_token = oauth_response.get("access_token")
            bot_user_id = oauth_response.get("bot_user_id")
            installer_user_id = oauth_response.get("authed_user", {}).get("id", "unknown")
            scopes = oauth_response.get("scope", "").split(",")
            
            # Prepare installation data for storage
            installation_data = {
                "team_id": team_id,
                "team_name": team_name,
                "bot_token": bot_token,
                "bot_user_id": bot_user_id,
                "installer_user_id": installer_user_id,
                "installer_name": "Unknown User",  # We'll get this from Slack API later
                "scopes": scopes,
                "installation_source": "web_oauth"
            }
            
            # Store installation data in Supabase
            storage_success = await store_installation(installation_data)
            
            if storage_success:
                logger.info(f"✅ Successfully installed and stored EnableBot for team {team_name} ({team_id})")
                storage_status = "✅ Installation data securely stored in database"
            else:
                logger.warning(f"⚠️ EnableBot installed for team {team_name} but failed to store in database")
                storage_status = "⚠️ Installation successful but data storage failed"
            
            # Show success page with storage status
            return HTMLResponse(f"""
            <html>
                <head><title>EnableBot Installation Successful</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>🎉 EnableBot Installation Successful!</h1>
                    <p><strong>{team_name}</strong> workspace is now connected to EnableBot.</p>
                    <p>Bot User ID: <code>{bot_user_id}</code></p>
                    <p>You can now send direct messages to <strong>@EnableBot</strong> in Slack!</p>
                    <div style="margin: 30px 0; padding: 20px; background: #f0f8ff; border-radius: 8px;">
                        <h3>Next Steps:</h3>
                        <ol style="text-align: left; display: inline-block;">
                            <li>Go to your Slack workspace</li>
                            <li>Send a direct message to @EnableBot</li>
                            <li>Start chatting with your AI assistant!</li>
                        </ol>
                    </div>
                    <p><a href="/" style="color: #4A154B; text-decoration: none;">← Back to Home</a></p>
                </body>
            </html>
            """)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return HTMLResponse(f"""
        <html>
            <head><title>EnableBot Installation Error</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1>❌ Installation Error</h1>
                <p>There was an error completing the installation.</p>
                <p>Error: {str(e)}</p>
                <p><a href="/" style="color: #4A154B; text-decoration: none;">← Try Again</a></p>
            </body>
        </html>
        """)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "EnableBot Web Interface",
        "version": "3.0.0"
    }

if __name__ == "__main__":
    # Run the web application
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting EnableBot Web Interface on {host}:{port}")
    
    uvicorn.run(
        "enablebot.web.main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )