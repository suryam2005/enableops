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
    """Initialize web application"""
    logger.info("🚀 Starting EnableBot Web Application...")
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
    
    # For now, show a success message
    return HTMLResponse("""
    <html>
        <head><title>EnableBot Installation</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h1>🎉 EnableBot Installation Successful!</h1>
            <p>Your Slack workspace is now connected to EnableBot.</p>
            <p>You can now send direct messages to EnableBot in Slack!</p>
            <p><a href="/">← Back to Home</a></p>
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