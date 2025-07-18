"""
Slack OAuth Authentication and Installation Flow
Handles Slack app installation with encrypted token storage
"""

import os
import logging
import secrets
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import httpx

# Import shared components
from enablebot.shared.database.config import db
from enablebot.shared.database.models import Tenant, InstallationEvent, PlanType, TenantStatus, EventType
from enablebot.shared.encryption.encryption import encrypt_slack_token, initialize_encryption

logger = logging.getLogger(__name__)

# Slack OAuth configuration
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI", "http://localhost:8000/slack/oauth/callback")

# Required Slack scopes
SLACK_SCOPES = [
    "app_mentions:read",
    "channels:history",
    "chat:write",
    "im:history",
    "im:read",
    "im:write",
    "users:read",
    "users:read.email"
]

class SlackAuthManager:
    """Manages Slack OAuth flow and token storage"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        # Initialize encryption infrastructure
        initialize_encryption()
    
    async def get_install_url(self, state: Optional[str] = None) -> str:
        """Generate Slack installation URL"""
        if not SLACK_CLIENT_ID:
            raise HTTPException(status_code=500, detail="Slack client ID not configured")
        
        # Generate state parameter for security
        if not state:
            state = secrets.token_urlsafe(32)
        
        params = {
            "client_id": SLACK_CLIENT_ID,
            "scope": ",".join(SLACK_SCOPES),
            "redirect_uri": SLACK_REDIRECT_URI,
            "state": state
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"https://slack.com/oauth/v2/authorize?{query_string}"
    
    async def handle_oauth_callback(self, code: str, state: str, request: Request) -> Dict[str, Any]:
        """Handle Slack OAuth callback and store installation"""
        if not SLACK_CLIENT_ID or not SLACK_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Slack OAuth not configured")
        
        try:
            # Exchange code for access token
            token_response = await self.client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": SLACK_CLIENT_ID,
                    "client_secret": SLACK_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": SLACK_REDIRECT_URI
                }
            )
            
            if token_response.status_code != 200:
                logger.error(f"Slack OAuth token exchange failed: {token_response.text}")
                raise HTTPException(status_code=400, detail="Failed to exchange OAuth code")
            
            token_data = token_response.json()
            
            if not token_data.get("ok"):
                logger.error(f"Slack OAuth error: {token_data.get('error')}")
                raise HTTPException(status_code=400, detail=f"Slack OAuth error: {token_data.get('error')}")
            
            # Extract installation data
            team_info = token_data.get("team", {})
            authed_user = token_data.get("authed_user", {})
            bot_info = token_data.get("access_token")  # This is the bot token
            
            team_id = team_info.get("id")
            team_name = team_info.get("name")
            installer_id = authed_user.get("id")
            bot_user_id = token_data.get("bot_user_id")
            scopes = token_data.get("scope", "").split(",")
            
            if not all([team_id, team_name, installer_id, bot_info, bot_user_id]):
                logger.error(f"Missing required OAuth data: {token_data}")
                raise HTTPException(status_code=400, detail="Incomplete OAuth response from Slack")
            
            # Get installer information
            installer_info = await self.get_user_info(bot_info, installer_id)
            installer_name = installer_info.get("real_name", installer_info.get("name", "Unknown User"))
            
            # Encrypt the bot token
            client_ip = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
            
            encrypted_token, encryption_key_id = await encrypt_slack_token(
                bot_info, team_id, client_ip, user_agent
            )
            
            # Store installation in database
            installation_data = await self.store_installation(
                team_id=team_id,
                team_name=team_name,
                encrypted_bot_token=encrypted_token,
                encryption_key_id=encryption_key_id,
                bot_user_id=bot_user_id,
                installer_id=installer_id,
                installer_name=installer_name,
                scopes=scopes,
                raw_oauth_data=token_data
            )
            
            logger.info(f"✅ Successfully installed EnableBot for team {team_name} ({team_id})")
            
            return {
                "success": True,
                "team_id": team_id,
                "team_name": team_name,
                "installer_name": installer_name,
                "bot_user_id": bot_user_id,
                "scopes": scopes,
                "installation_date": installation_data["created_at"],
                "plan": installation_data["plan"]
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"OAuth callback error: {e}")
            raise HTTPException(status_code=500, detail="Installation failed")
    
    async def get_user_info(self, bot_token: str, user_id: str) -> Dict[str, Any]:
        """Get user information from Slack API"""
        try:
            response = await self.client.get(
                "https://slack.com/api/users.info",
                headers={"Authorization": f"Bearer {bot_token}"},
                params={"user": user_id}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return data.get("user", {})
            
            logger.warning(f"Failed to get user info for {user_id}")
            return {}
            
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return {}
    
    async def store_installation(
        self,
        team_id: str,
        team_name: str,
        encrypted_bot_token: str,
        encryption_key_id: str,
        bot_user_id: str,
        installer_id: str,
        installer_name: str,
        scopes: list,
        raw_oauth_data: dict
    ) -> Dict[str, Any]:
        """Store installation data in database"""
        
        try:
            # Check if tenant already exists
            existing_tenant = await db.fetchrow(
                "SELECT * FROM tenants WHERE team_id = $1",
                team_id
            )
            
            current_time = datetime.now()
            
            if existing_tenant:
                # Update existing tenant
                await db.execute("""
                    UPDATE tenants 
                    SET team_name = $2, encrypted_bot_token = $3, encryption_key_id = $4,
                        bot_user_id = $5, installer_name = $6, updated_at = $7, 
                        last_active = $7, status = $8
                    WHERE team_id = $1
                """, team_id, team_name, encrypted_bot_token, encryption_key_id,
                    bot_user_id, installer_name, current_time, TenantStatus.ACTIVE.value)
                
                logger.info(f"Updated existing tenant: {team_id}")
            else:
                # Create new tenant
                await db.execute("""
                    INSERT INTO tenants (
                        team_id, team_name, encrypted_bot_token, encryption_key_id,
                        bot_user_id, installed_by, installer_name, plan, status,
                        settings, created_at, updated_at, last_active
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """, team_id, team_name, encrypted_bot_token, encryption_key_id,
                    bot_user_id, installer_id, installer_name, PlanType.FREE.value,
                    TenantStatus.ACTIVE.value, {}, current_time, current_time, current_time)
                
                logger.info(f"Created new tenant: {team_id}")
            
            # Log installation event
            await db.execute("""
                INSERT INTO installation_events (
                    team_id, event_type, event_data, installer_id, installer_name,
                    scopes, metadata, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, team_id, EventType.APP_INSTALLED.value, raw_oauth_data,
                installer_id, installer_name, scopes, 
                {"oauth_timestamp": current_time.isoformat()}, current_time)
            
            return {
                "team_id": team_id,
                "team_name": team_name,
                "plan": PlanType.FREE.value,
                "created_at": current_time.isoformat(),
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Error storing installation: {e}")
            raise HTTPException(status_code=500, detail="Failed to store installation")
    
    async def get_installation_data(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Get installation data for dashboard"""
        try:
            tenant_data = await db.fetchrow(
                "SELECT * FROM tenants WHERE team_id = $1 AND status = $2",
                team_id, TenantStatus.ACTIVE.value
            )
            
            if not tenant_data:
                return None
            
            # Get latest installation event
            event_data = await db.fetchrow("""
                SELECT * FROM installation_events 
                WHERE team_id = $1 AND event_type = $2 
                ORDER BY created_at DESC LIMIT 1
            """, team_id, EventType.APP_INSTALLED.value)
            
            scopes = event_data["scopes"] if event_data else []
            
            return {
                "team_id": tenant_data["team_id"],
                "team_name": tenant_data["team_name"],
                "bot_user_id": tenant_data["bot_user_id"],
                "installer_name": tenant_data["installer_name"],
                "plan": tenant_data["plan"],
                "status": tenant_data["status"],
                "installation_date": tenant_data["created_at"].strftime("%B %d, %Y"),
                "scopes": scopes
            }
            
        except Exception as e:
            logger.error(f"Error getting installation data: {e}")
            return None
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

# Global instance
slack_auth = SlackAuthManager()