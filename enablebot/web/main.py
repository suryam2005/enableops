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
        
        # Prepare tenant data for Supabase (matching existing schema)
        tenant_data = {
            "team_id": installation_data["team_id"],
            "team_name": installation_data["team_name"],
            "access_token": encrypted_token,  # Using access_token column instead of encrypted_bot_token
            "bot_user_id": installation_data["bot_user_id"],
            "installed_by": installation_data.get("installer_user_id", "unknown"),
            "installer_name": installation_data.get("installer_name", "Unknown User"),
            "active": True
        }
        
        # Store tenant data using Supabase REST API (upsert)
        # First try to update existing record
        update_response = await supabase_client.patch(
            "/rest/v1/tenants",
            json=tenant_data,
            params={"team_id": f"eq.{installation_data['team_id']}"}
        )
        
        if update_response.status_code in [200, 204]:
            logger.info(f"✅ Updated existing tenant data for team {installation_data['team_id']}")
        else:
            # If update fails, try to insert new record
            insert_response = await supabase_client.post(
                "/rest/v1/tenants",
                json=tenant_data
            )
            
            if insert_response.status_code not in [200, 201]:
                logger.error(f"Failed to store tenant data: {insert_response.status_code} - {insert_response.text}")
                return False
            else:
                logger.info(f"✅ Inserted new tenant data for team {installation_data['team_id']}")
        
        # Store installation event (matching existing schema)
        event_data = {
            "team_id": installation_data["team_id"],
            "team_name": installation_data["team_name"],
            "event_type": "app_installed",
            "installed_by": installation_data.get("installer_user_id", "unknown"),
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
    
    install_url = f"https://slack.com/oauth/v2/authorize?client_id={slack_client_id}&scope=chat:write,im:history,im:read,im:write,team:read,users:read&user_scope="
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
            installer_access_token = oauth_response.get("authed_user", {}).get("access_token")
            scopes = oauth_response.get("scope", "").split(",")
            
            # Get installer's name from Slack API
            installer_name = "Unknown User"
            if installer_access_token and installer_user_id != "unknown":
                try:
                    async with httpx.AsyncClient() as client:
                        user_response = await client.get(
                            "https://slack.com/api/users.info",
                            headers={"Authorization": f"Bearer {installer_access_token}"},
                            params={"user": installer_user_id}
                        )
                        user_data = user_response.json()
                        if user_data.get("ok") and user_data.get("user"):
                            user_profile = user_data["user"].get("profile", {})
                            installer_name = user_profile.get("display_name") or user_profile.get("real_name") or user_data["user"].get("name", "Unknown User")
                            logger.info(f"✅ Retrieved installer name: {installer_name}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not retrieve installer name: {e}")
            
            # Prepare installation data for storage
            installation_data = {
                "team_id": team_id,
                "team_name": team_name,
                "bot_token": bot_token,
                "bot_user_id": bot_user_id,
                "installer_user_id": installer_user_id,
                "installer_name": installer_name,
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
            
            # Get the Slack workspace URL for redirect
            slack_workspace_url = f"https://{team_name.lower().replace(' ', '')}.slack.com"
            if 'team' in oauth_response and 'url' in oauth_response['team']:
                slack_workspace_url = oauth_response['team']['url']
            
            # Show success page with auto-redirect to Slack
            return HTMLResponse(f"""
            <html>
                <head>
                    <title>EnableBot Installation Successful</title>
                    <script>
                        // Auto-redirect to Slack after 3 seconds
                        setTimeout(function() {{
                            window.open('{slack_workspace_url}', '_blank');
                            // Also redirect current page back to home
                            setTimeout(function() {{
                                window.location.href = '/';
                            }}, 1000);
                        }}, 3000);
                    </script>
                </head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>🎉 EnableBot Installation Successful!</h1>
                    <p><strong>{team_name}</strong> workspace is now connected to EnableBot.</p>
                    <p>Bot User ID: <code>{bot_user_id}</code></p>
                    <p>{storage_status}</p>
                    
                    <div style="margin: 30px 0; padding: 20px; background: #e8f5e8; border-radius: 8px; border: 2px solid #4caf50;">
                        <h3>🚀 Redirecting to Slack...</h3>
                        <p>You will be automatically redirected to your Slack workspace in <span id="countdown">3</span> seconds.</p>
                        <p>If the redirect doesn't work, <a href="{slack_workspace_url}" target="_blank" style="color: #4A154B; font-weight: bold;">click here to open Slack</a></p>
                    </div>
                    
                    <div style="margin: 30px 0; padding: 20px; background: #f0f8ff; border-radius: 8px;">
                        <h3>Next Steps in Slack:</h3>
                        <ol style="text-align: left; display: inline-block;">
                            <li>Look for <strong>@EnableOps</strong> in your Apps section</li>
                            <li>Send a direct message to @EnableOps</li>
                            <li>Start chatting with your AI assistant!</li>
                        </ol>
                    </div>
                    
                    <p><a href="/" style="color: #4A154B; text-decoration: none;">← Back to Home</a></p>
                    
                    <script>
                        // Countdown timer
                        let countdown = 3;
                        const countdownElement = document.getElementById('countdown');
                        const timer = setInterval(function() {{
                            countdown--;
                            countdownElement.textContent = countdown;
                            if (countdown <= 0) {{
                                clearInterval(timer);
                                countdownElement.textContent = 'now';
                            }}
                        }}, 1000);
                    </script>
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