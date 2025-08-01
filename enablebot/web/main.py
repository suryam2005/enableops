"""
EnableOps Web Interface - Production Version with Prisma
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
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import Prisma services
try:
    from enablebot.shared.database.prisma_client import init_prisma, close_prisma, get_prisma
    from enablebot.shared.database.models import (
        UserProfileService, TenantService, InstallationEventService, 
        KnowledgeBaseService, EncryptionKeyService
    )
    from enablebot.shared.auth.supabase_auth import auth_service as supabase_auth_service
    from enablebot.shared.encryption.encryption import encrypt_slack_token, initialize_encryption
    from prisma.enums import PlanType, TenantStatus, EventType
    PRISMA_AVAILABLE = True
    print("✅ Prisma services imported successfully")
except ImportError as e:
    print(f"⚠️ Prisma not available: {e}")
    PRISMA_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="EnableOps Web Interface",
    description="Slack OAuth and Dashboard for EnableOps AI Assistant",
    version="3.0.0"
)

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-secret-key"))

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates setup
from pathlib import Path
current_dir = Path(__file__).parent
templates_dir = current_dir / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Supabase Auth Service
if PRISMA_AVAILABLE:
    auth_service = supabase_auth_service
else:
    # Fallback simple auth service
    class SimpleSupabaseAuth:
        def __init__(self):
            self.supabase_url = os.getenv("SUPABASE_URL")
            self.supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
            self.client = httpx.AsyncClient(timeout=30.0)
        
        async def verify_token(self, access_token: str) -> Optional[Dict[str, Any]]:
            """Verify Supabase access token"""
            try:
                response = await self.client.get(
                    f"{self.supabase_url}/auth/v1/user",
                    headers={
                        "apikey": self.supabase_anon_key,
                        "Authorization": f"Bearer {access_token}"
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                return None
            except Exception as e:
                logger.error(f"Token verification error: {e}")
                return None
    
    auth_service = SimpleSupabaseAuth()

# Authentication helper
async def verify_supabase_token(authorization: str = Header(None)):
    """Verify Supabase JWT token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    try:
        token = authorization.split(" ")[1] if authorization.startswith("Bearer ") else authorization
        user_data = await auth_service.verify_token(token)
        
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return user_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

@app.on_event("startup")
async def startup_event():
    """Initialize web application"""
    logger.info("🚀 Starting EnableOps Web Application...")
    
    if PRISMA_AVAILABLE:
        # Initialize Prisma database connection
        if await init_prisma():
            logger.info("✅ Prisma database connection initialized")
        else:
            logger.error("❌ Prisma database connection failed")
            # Don't fail startup, continue with limited functionality
        
        # Initialize encryption system
        initialize_encryption()
        logger.info("✅ Encryption system initialized")
    else:
        logger.warning("⚠️ Running in simplified mode without Prisma")
    
    logger.info("🎉 EnableOps Web Application ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    logger.info("🛑 Shutting down EnableOps Web Application...")
    
    if PRISMA_AVAILABLE:
        # Close Prisma connection
        await close_prisma()
        
        # Close auth service
        await supabase_auth_service.close()
    else:
        # Close simple auth service
        await auth_service.client.aclose()
    
    logger.info("✅ Cleanup completed")

@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Landing page with signup/signin"""
    return templates.TemplateResponse("landingpage.html", {"request": request})

@app.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request):
    """Authentication page with Supabase Auth"""
    return templates.TemplateResponse("auth.html", {
        "request": request,
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "")
    })

@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    """Protected home page with Slack installation"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "")
    })

@app.get("/dashboard", response_class=HTMLResponse)
async def general_dashboard(request: Request):
    """General dashboard for authenticated users"""
    return templates.TemplateResponse("user_dashboard.html", {
        "request": request,
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "")
    })

async def store_installation_with_prisma(installation_data: Dict[str, Any]) -> bool:
    """Store installation data using Prisma ORM"""
    if not PRISMA_AVAILABLE:
        logger.warning("Prisma not available, skipping database storage")
        return False
    
    try:
        # Initialize encryption if not already done
        initialize_encryption()
        
        # Encrypt the bot token
        encrypted_token, encryption_key_id = await encrypt_slack_token(
            installation_data["bot_token"], 
            installation_data["team_id"]
        )
        
        # Create or update user profile if Supabase user data is available
        if installation_data.get("supabase_user_id") and installation_data.get("installer_email"):
            await UserProfileService.create_or_update_user(
                supabase_user_id=installation_data["supabase_user_id"],
                email=installation_data["installer_email"],
                full_name=installation_data.get("installer_name")
            )
            logger.info(f"✅ Created/updated user profile for {installation_data['installer_email']}")
        
        # Check if tenant already exists
        existing_tenant = await TenantService.get_tenant_by_team_id(installation_data["team_id"])
        
        if existing_tenant:
            # Update existing tenant
            await TenantService.update_tenant(
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
            await TenantService.create_tenant(
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

@app.get("/api/user/workspaces")
async def get_user_workspaces_api(user: dict = Depends(verify_supabase_token)):
    """API endpoint to get user's workspaces using Prisma"""
    try:
        if PRISMA_AVAILABLE:
            user_email = user.get("email", "")
            user_id = user.get("id", "")
            
            # Get workspaces using Prisma
            if user_id:
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
            workspaces = []
            for tenant in tenants:
                workspaces.append({
                    "team_id": tenant.teamId,
                    "team_name": tenant.teamName,
                    "role": "admin" if tenant.supabaseUserId == user_id else "member",
                    "installation_date": tenant.createdAt.strftime("%B %d, %Y") if tenant.createdAt else "Unknown",
                    "installer_name": tenant.installerName or "Unknown",
                    "bot_user_id": tenant.botUserId or ""
                })
            
            logger.info(f"✅ Found {len(workspaces)} workspaces for user {user_email}")
        else:
            # Fallback when Prisma is not available
            workspaces = []
            logger.warning("Prisma not available, returning empty workspaces")
        
        return JSONResponse({
            "success": True,
            "workspaces": workspaces,
            "user": {
                "email": user.get("email", ""),
                "name": user.get("user_metadata", {}).get("full_name", ""),
                "id": user.get("id", "")
            }
        })
    except Exception as e:
        logger.error(f"Error getting user workspaces: {e}")
        raise HTTPException(status_code=500, detail="Failed to get workspaces")

@app.get("/slack/install")
async def slack_install_get():
    """Slack install endpoint (simplified)"""
    slack_client_id = os.getenv("SLACK_CLIENT_ID", "")
    if not slack_client_id:
        raise HTTPException(status_code=500, detail="Slack Client ID not configured")
    
    install_url = f"https://slack.com/oauth/v2/authorize?client_id={slack_client_id}&scope=chat:write,im:history,im:read,im:write,team:read,users:read&user_scope="
    return RedirectResponse(url=install_url)

@app.post("/slack/install")
async def slack_install_post(request: Request):
    """Handle Slack install with user session data (simplified)"""
    slack_client_id = os.getenv("SLACK_CLIENT_ID", "")
    if not slack_client_id:
        raise HTTPException(status_code=500, detail="Slack Client ID not configured")
    
    try:
        # Get form data (user session info from frontend)
        form_data = await request.form()
        user_data_str = form_data.get("user_data")
        
        if user_data_str:
            import json
            user_data = json.loads(user_data_str)
            logger.info(f"✅ Received user data for Slack install: {user_data.get('email', 'unknown')}")
            
            # Store user info in session for later use (when we implement full OAuth)
            request.session["pending_install_user"] = {
                "user_id": user_data.get("user_id"),
                "email": user_data.get("email"),
                "full_name": user_data.get("full_name")
            }
        
        # Generate state parameter for OAuth security
        import secrets
        state = secrets.token_urlsafe(32)
        request.session["oauth_state"] = state
        
        # Redirect to Slack OAuth with state
        install_url = f"https://slack.com/oauth/v2/authorize?client_id={slack_client_id}&scope=chat:write,im:history,im:read,im:write,team:read,users:read&user_scope=&state={state}"
        return RedirectResponse(url=install_url)
        
    except Exception as e:
        logger.error(f"Error in Slack install POST: {e}")
        return HTMLResponse(f"""
        <html>
            <head><title>EnableOps Installation Error</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1>❌ Installation Error</h1>
                <p>There was an error starting the Slack installation.</p>
                <p>Error: {str(e)}</p>
                <p><a href="/home" style="color: #4A154B; text-decoration: none;">← Back to Home</a></p>
            </body>
        </html>
        """)

@app.get("/slack/oauth/callback")
async def slack_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(None),
    error: str = Query(None)
):
    """Handle Slack OAuth callback with proper database storage"""
    if error:
        logger.error(f"Slack OAuth error: {error}")
        return HTMLResponse(f"""
        <html>
            <head><title>EnableOps Installation Error</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1>❌ Installation Error</h1>
                <p>There was an error during Slack installation: {error}</p>
                <p><a href="/" style="color: #4A154B; text-decoration: none;">← Back to Home</a></p>
            </body>
        </html>
        """)
    
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
                    "redirect_uri": f"https://enableops-backend.madrasco.space/slack/oauth/callback"
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
            
            # Get user session data if available
            pending_user = request.session.get("pending_install_user", {})
            supabase_user_id = pending_user.get("user_id")
            supabase_user_email = pending_user.get("email")
            supabase_user_name = pending_user.get("full_name")
            
            # Get installer's name from Slack API
            installer_name = "Unknown User"
            installer_email = None
            
            if supabase_user_name and supabase_user_email:
                # Use Supabase user data if available
                installer_name = supabase_user_name
                installer_email = supabase_user_email
                logger.info(f"✅ Using Supabase user data: {installer_name} ({installer_email})")
            elif installer_access_token and installer_user_id != "unknown":
                # Fallback to Slack API
                try:
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
            
            # Store installation data using Prisma if available
            if PRISMA_AVAILABLE:
                success = await store_installation_with_prisma({
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
                })
                
                if success:
                    storage_status = "✅ Installation data stored in database"
                else:
                    storage_status = "⚠️ Installation successful but data storage failed"
            else:
                storage_status = "⚠️ Installation successful (database storage not available)"
            
            # Clear session data
            request.session.pop("pending_install_user", None)
            request.session.pop("oauth_state", None)
            
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
                            // Also redirect current page back to dashboard
                            setTimeout(function() {{
                                window.location.href = '/dashboard';
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
                    
                    <p><a href="/dashboard" style="color: #4A154B; text-decoration: none;">← View Dashboard</a></p>
                    
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
                <p>There was an error processing the installation.</p>
                <p>Error: {str(e)}</p>
                <p><a href="/" style="color: #4A154B; text-decoration: none;">← Try Again</a></p>
            </body>
        </html>
        """)

@app.post("/slack/events")
async def slack_events(request: Request):
    """Handle Slack events (simplified)"""
    try:
        body = await request.json()
        
        # Handle URL verification challenge
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge")}
        
        # For now, just acknowledge other events
        logger.info(f"Received Slack event: {body.get('type', 'unknown')}")
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Slack events error: {e}")
        return {"status": "error", "message": str(e)}

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