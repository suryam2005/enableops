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
from fastapi.staticfiles import StaticFiles
import uvicorn

# Import shared components
from enablebot.shared.database.config import init_database, close_database
from enablebot.web.auth import slack_auth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="EnableBot Web Interface",
    description="Slack OAuth and Dashboard for EnableBot AI Assistant",
    version="3.0.0"
)

# Templates
templates = Jinja2Templates(directory="enablebot/web/templates")

@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup"""
    logger.info("🚀 Starting EnableBot Web Application...")
    
    # Initialize database
    if await init_database():
        logger.info("✅ Database connection initialized")
    else:
        logger.error("❌ Failed to initialize database")
    
    logger.info("🎉 EnableBot Web Application ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    logger.info("🛑 Shutting down EnableBot Web Application...")
    await close_database()
    await slack_auth.close()
    logger.info("✅ Cleanup completed")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with Slack installation"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/slack/install")
async def slack_install():
    """Redirect to Slack OAuth"""
    try:
        install_url = await slack_auth.get_install_url()
        return RedirectResponse(url=install_url)
    except Exception as e:
        logger.error(f"Error generating install URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate installation URL")

@app.get("/slack/oauth/callback")
async def slack_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(None)
):
    """Handle Slack OAuth callback"""
    if error:
        logger.error(f"Slack OAuth error: {error}")
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    
    try:
        # Handle OAuth callback
        installation_data = await slack_auth.handle_oauth_callback(code, state, request)
        
        # Redirect to dashboard
        team_id = installation_data["team_id"]
        return RedirectResponse(url=f"/dashboard/{team_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail="Installation failed")

@app.get("/dashboard/{team_id}", response_class=HTMLResponse)
async def dashboard(request: Request, team_id: str):
    """Dashboard page after successful installation"""
    try:
        # Get installation data
        installation_data = await slack_auth.get_installation_data(team_id)
        
        if not installation_data:
            raise HTTPException(status_code=404, detail="Installation not found")
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            **installation_data
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "EnableBot Web Interface",
        "version": "3.0.0"
    }

@app.get("/api/installations/{team_id}")
async def get_installation_info(team_id: str):
    """API endpoint to get installation information"""
    try:
        installation_data = await slack_auth.get_installation_data(team_id)
        
        if not installation_data:
            raise HTTPException(status_code=404, detail="Installation not found")
        
        return installation_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get installation data")

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