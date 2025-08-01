"""
EnableOps Web Interface - Deployment Ready Version
Basic version without Prisma dependencies for Railway deployment
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any

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

# Supabase Auth Service (simplified)
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
    logger.info("🚀 Starting EnableOps Web Application (Deployment Mode)...")
    logger.info("🎉 EnableOps Web Application ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    logger.info("🛑 Shutting down EnableOps Web Application...")
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

@app.get("/api/user/workspaces")
async def get_user_workspaces_api(user: dict = Depends(verify_supabase_token)):
    """API endpoint to get user's workspaces (simplified)"""
    try:
        # For now, return empty workspaces - will be implemented with Prisma later
        return JSONResponse({
            "success": True,
            "workspaces": [],
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

@app.get("/slack/oauth/callback")
async def slack_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(None),
    error: str = Query(None)
):
    """Handle Slack OAuth callback (simplified)"""
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
        # For now, show a success message
        # Full OAuth implementation will be added with Prisma later
        return HTMLResponse("""
        <html>
            <head>
                <title>EnableOps Installation Successful</title>
                <script>
                    // Auto-redirect to home after 3 seconds
                    setTimeout(function() {
                        window.location.href = '/';
                    }, 3000);
                </script>
            </head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1>🎉 EnableOps Installation Started!</h1>
                <p>Your Slack workspace connection is being processed.</p>
                
                <div style="margin: 30px 0; padding: 20px; background: #e8f5e8; border-radius: 8px; border: 2px solid #4caf50;">
                    <h3>✅ Installation Received</h3>
                    <p>We've received your installation request. Full database integration will be available soon!</p>
                    <p>Redirecting to home page in <span id="countdown">3</span> seconds...</p>
                </div>
                
                <div style="margin: 30px 0; padding: 20px; background: #f0f8ff; border-radius: 8px;">
                    <h3>Next Steps:</h3>
                    <ol style="text-align: left; display: inline-block;">
                        <li>Complete the full Prisma database setup</li>
                        <li>Configure your Slack app credentials</li>
                        <li>Test the complete installation flow</li>
                    </ol>
                </div>
                
                <p><a href="/" style="color: #4A154B; text-decoration: none;">← Back to Home</a></p>
                
                <script>
                    // Countdown timer
                    let countdown = 3;
                    const countdownElement = document.getElementById('countdown');
                    const timer = setInterval(function() {
                        countdown--;
                        countdownElement.textContent = countdown;
                        if (countdown <= 0) {
                            clearInterval(timer);
                            countdownElement.textContent = 'now';
                        }
                    }, 1000);
                </script>
            </body>
        </html>
        """)
        
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