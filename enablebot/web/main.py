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

# Database connection
db_pool = None

async def get_database_url() -> str:
    """Construct database URL from environment variables"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
    supabase_db_password = os.getenv("SUPABASE_DB_PASSWORD")
    
    if not supabase_url or not supabase_service_key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required")
    
    # Extract project ID from Supabase URL
    project_id = supabase_url.split("//")[1].split(".")[0]
    
    # Use service key as password if no specific DB password is provided
    db_password = supabase_db_password or supabase_service_key
    db_user = "postgres"
    db_host = f"db.{project_id}.supabase.co"
    db_port = "5432"
    db_name = "postgres"
    
    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

async def init_database():
    """Initialize database connection pool and create tables"""
    global db_pool
    try:
        database_url = await get_database_url()
        db_pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=5,
            command_timeout=60
        )
        
        # Create tables if they don't exist
        async with db_pool.acquire() as conn:
            # Read and execute the schema SQL
            schema_path = os.path.join(os.path.dirname(__file__), "..", "shared", "database", "migrations", "001_create_multi_tenant_schema.sql")
            try:
                with open(schema_path, 'r') as f:
                    schema_sql = f.read()
                await conn.execute(schema_sql)
                logger.info("✅ Database schema initialized")
            except FileNotFoundError:
                logger.warning("⚠️ Schema file not found, creating basic tables")
                # Create basic tables if schema file is missing
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS tenants (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        team_id VARCHAR(20) UNIQUE NOT NULL,
                        team_name VARCHAR(255) NOT NULL,
                        encrypted_bot_token TEXT NOT NULL,
                        encryption_key_id VARCHAR(255) NOT NULL,
                        bot_user_id VARCHAR(20),
                        installer_user_id VARCHAR(20),
                        installer_name VARCHAR(255),
                        scopes JSONB DEFAULT '[]'::jsonb,
                        status VARCHAR(20) DEFAULT 'active',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                    
                    CREATE TABLE IF NOT EXISTS installation_events (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        team_id VARCHAR(20) NOT NULL,
                        event_type VARCHAR(50) NOT NULL,
                        installer_user_id VARCHAR(20),
                        installer_name VARCHAR(255),
                        metadata JSONB DEFAULT '{}'::jsonb,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                """)
        
        logger.info("✅ Database connection pool initialized")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
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
    """Store installation data in Supabase"""
    if not db_pool:
        logger.error("Database pool not initialized")
        return False
    
    try:
        async with db_pool.acquire() as conn:
            # Encrypt the bot token
            encrypted_token, encryption_key = await encrypt_token(
                installation_data["bot_token"], 
                installation_data["team_id"]
            )
            
            # Store tenant data
            await conn.execute("""
                INSERT INTO tenants (
                    team_id, team_name, encrypted_bot_token, encryption_key_id,
                    bot_user_id, installer_user_id, installer_name, 
                    scopes, status, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
                ON CONFLICT (team_id) DO UPDATE SET
                    team_name = EXCLUDED.team_name,
                    encrypted_bot_token = EXCLUDED.encrypted_bot_token,
                    encryption_key_id = EXCLUDED.encryption_key_id,
                    bot_user_id = EXCLUDED.bot_user_id,
                    installer_user_id = EXCLUDED.installer_user_id,
                    installer_name = EXCLUDED.installer_name,
                    scopes = EXCLUDED.scopes,
                    status = EXCLUDED.status,
                    updated_at = NOW()
            """, 
                installation_data["team_id"],
                installation_data["team_name"],
                encrypted_token,
                encryption_key,  # Using encryption key as key_id for simplicity
                installation_data["bot_user_id"],
                installation_data.get("installer_user_id", "unknown"),
                installation_data.get("installer_name", "Unknown User"),
                json.dumps(installation_data.get("scopes", [])),
                "active"
            )
            
            # Store installation event
            await conn.execute("""
                INSERT INTO installation_events (
                    team_id, event_type, installer_user_id, installer_name,
                    metadata, created_at
                ) VALUES ($1, $2, $3, $4, $5, NOW())
            """,
                installation_data["team_id"],
                "app_installed",
                installation_data.get("installer_user_id", "unknown"),
                installation_data.get("installer_name", "Unknown User"),
                json.dumps({
                    "bot_user_id": installation_data["bot_user_id"],
                    "scopes": installation_data.get("scopes", []),
                    "installation_source": "web_oauth"
                })
            )
            
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
    
    # Initialize database connection
    if await init_database():
        logger.info("✅ Database connection initialized")
    else:
        logger.warning("⚠️ Database connection failed - continuing without database")
    
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