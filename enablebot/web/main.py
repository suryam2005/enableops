"""
EnableOps Web Interface
Handles Slack OAuth, dashboard, and installation flow using Prisma ORM and Supabase Auth
"""

import os
import logging
import json
import secrets
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Request, Query, Depends, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.session import SessionMiddleware
import uvicorn

# Import our new services
from enablebot.shared.database.prisma_client import init_prisma, close_prisma, get_prisma
from enablebot.shared.database.models import (
    UserProfileService, TenantService, InstallationEventService, 
    KnowledgeBaseService, EncryptionKeyService
)
from enablebot.shared.auth.supabase_auth import auth_service
from enablebot.shared.encryption.encryption import encrypt_slack_token, initialize_encryption
from prisma.enums import PlanType, TenantStatus, EventType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)



async def store_installation(installation_data: Dict[str, Any]) -> bool:
    """Store installation data using Prisma ORM"""
    try:
        # Initialize encryption if not already done
        initialize_encryption()
        
        # Encrypt the bot token
        encrypted_token, encryption_key_id = await encrypt_slack_token(
            installation_data["bot_token"], 
            installation_data["team_id"]
        )
        
        # Create or update user profile if Supabase user data is available
        user_profile = None
        if installation_data.get("supabase_user_id") and installation_data.get("installer_email"):
            user_profile = await UserProfileService.create_or_update_user(
                supabase_user_id=installation_data["supabase_user_id"],
                email=installation_data["installer_email"],
                full_name=installation_data.get("installer_name")
            )
            logger.info(f"✅ Created/updated user profile for {installation_data['installer_email']}")
        
        # Check if tenant already exists
        existing_tenant = await TenantService.get_tenant_by_team_id(installation_data["team_id"])
        
        if existing_tenant:
            # Update existing tenant
            tenant = await TenantService.update_tenant(
                team_id=installation_data["team_id"],
                teamName=installation_data["team_name"],
                encryptedBotToken=encrypted_token,
                encryptionKeyId=encryption_key_id,
                botUserId=installation_data["bot_user_id"],
                installerName=installation_data.get("installer_name", "Unknown User"),
                installerEmail=installation_data.get("installer_email"),
                supabaseUserId=installation_data.get("supabase_user_id"),
                status=TenantStatus.ACTIVE,
                lastActive=datetime.now()
            )
            logger.info(f"✅ Updated existing tenant for team {installation_data['team_id']}")
        else:
            # Create new tenant
            tenant = await TenantService.create_tenant(
                team_id=installation_data["team_id"],
                team_name=installation_data["team_name"],
                encrypted_bot_token=encrypted_token,
                encryption_key_id=encryption_key_id,
                bot_user_id=installation_data["bot_user_id"],
                installed_by=installation_data.get("installer_user_id", "unknown"),
                installer_name=installation_data.get("installer_name", "Unknown User"),
                installer_email=installation_data.get("installer_email"),
                supabase_user_id=installation_data.get("supabase_user_id"),
                plan=PlanType.FREE
            )
            logger.info(f"✅ Created new tenant for team {installation_data['team_id']}")
        
        # Create installation event
        await InstallationEventService.create_event(
            team_id=installation_data["team_id"],
            event_type=EventType.APP_INSTALLED,
            event_data={
                "team_name": installation_data["team_name"],
                "bot_user_id": installation_data["bot_user_id"],
                "installation_source": installation_data.get("installation_source", "web_oauth")
            },
            installer_id=installation_data.get("installer_user_id", "unknown"),
            installer_name=installation_data.get("installer_name", "Unknown User"),
            scopes=installation_data.get("scopes", []),
            supabase_user_id=installation_data.get("supabase_user_id"),
            metadata={
                "oauth_timestamp": datetime.now().isoformat(),
                "encryption_key_id": encryption_key_id
            }
        )
        
        logger.info(f"✅ Successfully stored installation data for team {installation_data['team_id']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to store installation data: {e}")
        return False

# Initialize FastAPI app
app = FastAPI(
    title="EnableOps Web Interface",
    description="Slack OAuth and Dashboard for EnableOps AI Assistant",
    version="3.0.0"
)

# Add session middleware for user tracking
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "your-secret-key-change-in-production"))

# Add CORS middleware for Supabase Auth
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

# Authentication helpers
async def verify_supabase_token(authorization: str = Header(None)):
    """Verify Supabase JWT token using auth service"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    try:
        # Extract token from "Bearer <token>"
        token = authorization.split(" ")[1] if authorization.startswith("Bearer ") else authorization
        
        # Verify token with Supabase Auth service
        user_data = await auth_service.verify_token(token)
        
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return user_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_user_workspaces(user_email: str, user_id: str = None) -> List[Dict[str, Any]]:
    """Get workspaces associated with user using Prisma"""
    try:
        if user_id:
            # Get tenants by Supabase user ID (primary method)
            tenants = await TenantService.get_user_tenants(user_id)
        else:
            # Fallback: get all active tenants and filter by email
            all_tenants = await TenantService.get_active_tenants()
            tenants = [
                tenant for tenant in all_tenants 
                if tenant.installerEmail == user_email or 
                (user_email and tenant.installerName and user_email.split('@')[0].lower() in tenant.installerName.lower())
            ]
        
        # Convert to response format
        user_workspaces = []
        for tenant in tenants:
            user_workspaces.append({
                "team_id": tenant.teamId,
                "team_name": tenant.teamName,
                "role": "admin" if tenant.supabaseUserId == user_id else "member",
                "installation_date": tenant.createdAt.strftime("%B %d, %Y") if tenant.createdAt else "Unknown",
                "installer_name": tenant.installerName or "Unknown",
                "bot_user_id": tenant.botUserId or ""
            })
        
        logger.info(f"✅ Found {len(user_workspaces)} workspaces for user {user_email}")
        return user_workspaces
        
    except Exception as e:
        logger.error(f"Error getting user workspaces: {e}")
        return []

@app.on_event("startup")
async def startup_event():
    """Initialize web application"""
    logger.info("🚀 Starting EnableOps Web Application...")
    
    # Initialize Prisma database connection
    if await init_prisma():
        logger.info("✅ Prisma database connection initialized")
    else:
        logger.error("❌ Prisma database connection failed")
        raise RuntimeError("Database connection required")
    
    # Initialize encryption system
    initialize_encryption()
    logger.info("✅ Encryption system initialized")
    
    logger.info("🎉 EnableOps Web Application ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    logger.info("🛑 Shutting down EnableOps Web Application...")
    
    # Close Prisma connection
    await close_prisma()
    
    # Close auth service
    await auth_service.close()
    
    logger.info("✅ Cleanup completed")

@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Landing page with signup/signin"""
    return templates.TemplateResponse("landingpage.html", {"request": request})

@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    """Protected home page with Slack installation (after auth)"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "")
    })

@app.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request):
    """Authentication page with Supabase Auth"""
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    
    return templates.TemplateResponse("auth.html", {
        "request": request,
        "supabase_url": supabase_url,
        "supabase_anon_key": supabase_anon_key
    })

@app.get("/dashboard", response_class=HTMLResponse)
async def general_dashboard(request: Request):
    """General dashboard for authenticated users"""
    return templates.TemplateResponse("user_dashboard.html", {
        "request": request,
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "")
    })

@app.get("/api/user/workspaces")
async def get_user_workspaces_api(user: dict = Depends(verify_supabase_token)):
    """API endpoint to get user's workspaces"""
    try:
        user_email = user.get("email", "")
        user_id = user.get("id", "")
        workspaces = await get_user_workspaces(user_email, user_id)
        
        return JSONResponse({
            "success": True,
            "workspaces": workspaces,
            "user": {
                "email": user_email,
                "name": user.get("user_metadata", {}).get("full_name", ""),
                "id": user_id
            }
        })
    except Exception as e:
        logger.error(f"Error getting user workspaces: {e}")
        raise HTTPException(status_code=500, detail="Failed to get workspaces")

@app.get("/dashboard/{team_id}", response_class=HTMLResponse)
async def workspace_dashboard(request: Request, team_id: str):
    """Dashboard for specific workspace using Prisma"""
    try:
        # Get tenant data using Prisma
        tenant = await TenantService.get_tenant_by_team_id(team_id)
        
        if not tenant or tenant.status != TenantStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        # Get installation events for scopes
        events = await InstallationEventService.get_team_events(team_id)
        scopes = []
        
        # Find the latest installation event
        for event in events:
            if event.eventType == EventType.APP_INSTALLED:
                scopes = event.scopes
                break
        
        # Prepare dashboard data
        dashboard_data = {
            "request": request,
            "team_id": tenant.teamId,
            "team_name": tenant.teamName,
            "bot_user_id": tenant.botUserId,
            "installer_name": tenant.installerName,
            "plan": tenant.plan.value.title(),
            "installation_date": tenant.createdAt.strftime("%B %d, %Y") if tenant.createdAt else "Unknown",
            "scopes": scopes
        }
        
        return templates.TemplateResponse("dashboard.html", dashboard_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail="Error loading dashboard")

@app.post("/slack/install")
async def slack_install_post(request: Request):
    """Handle Slack install with user session data"""
    slack_client_id = os.getenv("SLACK_CLIENT_ID", "")
    if not slack_client_id:
        raise HTTPException(status_code=500, detail="Slack Client ID not configured")
    
    # Get form data
    form_data = await request.form()
    user_data_str = form_data.get("user_data")
    
    if user_data_str:
        try:
            import json
            user_data = json.loads(user_data_str)
            
            # Store user info in session for later use in callback
            request.session["supabase_user_id"] = user_data.get("user_id")
            request.session["supabase_user_email"] = user_data.get("email")
            request.session["supabase_user_name"] = user_data.get("full_name")
            request.session["supabase_access_token"] = user_data.get("access_token")
            
            logger.info(f"✅ Stored Supabase user session for {user_data.get('email')} during Slack install")
        except Exception as e:
            logger.warning(f"⚠️ Could not parse user data: {e}")
    
    # Generate state parameter for OAuth security
    import secrets
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    
    install_url = f"https://slack.com/oauth/v2/authorize?client_id={slack_client_id}&scope=chat:write,im:history,im:read,im:write,team:read,users:read&user_scope=&state={state}"
    return RedirectResponse(url=install_url)

@app.get("/slack/install")
async def slack_install_get():
    """Fallback GET endpoint for direct Slack install (without user session)"""
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
            
            # Check if we have Supabase user session data
            supabase_user_id = request.session.get("supabase_user_id")
            supabase_user_email = request.session.get("supabase_user_email")
            supabase_user_name = request.session.get("supabase_user_name")
            
            # Get installer's name - prioritize Supabase user data, then Slack API
            installer_name = "Unknown User"
            installer_email = None
            
            if supabase_user_name and supabase_user_email:
                # Use Supabase user data if available
                installer_name = supabase_user_name
                installer_email = supabase_user_email
                installer_user_id = supabase_user_id or installer_user_id
                logger.info(f"✅ Using Supabase user data: {installer_name} ({installer_email})")
            elif installer_access_token and installer_user_id != "unknown":
                # Fallback to Slack API
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
                            installer_email = user_profile.get("email")
                            logger.info(f"✅ Retrieved installer name from Slack: {installer_name}")
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
                "installer_email": installer_email,
                "supabase_user_id": supabase_user_id,
                "scopes": scopes,
                "installation_source": "web_oauth"
            }
            
            # Store installation data in Supabase
            storage_success = await store_installation(installation_data)
            
            if storage_success:
                logger.info(f"✅ Successfully installed and stored EnableOps for team {team_name} ({team_id})")
                storage_status = "✅ Installation data securely stored in database"
            else:
                logger.warning(f"⚠️ EnableOps installed for team {team_name} but failed to store in database")
                storage_status = "⚠️ Installation successful but data storage failed"
            
            # Get the Slack workspace URL for redirect
            slack_workspace_url = f"https://{team_name.lower().replace(' ', '')}.slack.com"
            if 'team' in oauth_response and 'url' in oauth_response['team']:
                slack_workspace_url = oauth_response['team']['url']
            
            # Show success page with auto-redirect to Slack
            return HTMLResponse(f"""
            <html>
                <head>
                    <title>EnableOps Installation Successful</title>
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
                    <h1>🎉 EnableOps Installation Successful!</h1>
                    <p><strong>{team_name}</strong> workspace is now connected to EnableOps.</p>
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
            <head><title>EnableOps Installation Error</title></head>
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
        "service": "EnableOps Web Interface",
        "version": "3.0.0"
    }

if __name__ == "__main__":
    # Run the web application
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting EnableOps Web Interface on {host}:{port}")
    
    uvicorn.run(
        "enablebot.web.main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )