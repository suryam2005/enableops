"""
Supabase Authentication Service
Handles authentication using Supabase Auth API
"""

import os
import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class SupabaseAuthService:
    """Service for Supabase authentication operations"""
    
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
        self.supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not all([self.supabase_url, self.supabase_service_key, self.supabase_anon_key]):
            raise ValueError("Missing required Supabase configuration")
        
        # HTTP client for Supabase Auth API
        self.client = httpx.AsyncClient(
            base_url=self.supabase_url,
            timeout=30.0
        )
    
    async def verify_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Verify Supabase access token and get user data"""
        try:
            response = await self.client.get(
                "/auth/v1/user",
                headers={
                    "apikey": self.supabase_anon_key,
                    "Authorization": f"Bearer {access_token}"
                }
            )
            
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"✅ Token verified for user: {user_data.get('email')}")
                return user_data
            else:
                logger.warning(f"⚠️ Token verification failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error verifying token: {e}")
            return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user data by Supabase user ID (admin operation)"""
        try:
            response = await self.client.get(
                f"/auth/v1/admin/users/{user_id}",
                headers={
                    "apikey": self.supabase_service_key,
                    "Authorization": f"Bearer {self.supabase_service_key}"
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"⚠️ User lookup failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting user: {e}")
            return None
    
    async def create_user(
        self, 
        email: str, 
        password: str, 
        user_metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a new user (admin operation)"""
        try:
            response = await self.client.post(
                "/auth/v1/admin/users",
                headers={
                    "apikey": self.supabase_service_key,
                    "Authorization": f"Bearer {self.supabase_service_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "email": email,
                    "password": password,
                    "user_metadata": user_metadata or {},
                    "email_confirm": True  # Auto-confirm for admin creation
                }
            )
            
            if response.status_code in [200, 201]:
                user_data = response.json()
                logger.info(f"✅ User created: {email}")
                return user_data
            else:
                logger.error(f"❌ User creation failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error creating user: {e}")
            return None
    
    async def update_user_metadata(
        self, 
        user_id: str, 
        user_metadata: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update user metadata (admin operation)"""
        try:
            response = await self.client.put(
                f"/auth/v1/admin/users/{user_id}",
                headers={
                    "apikey": self.supabase_service_key,
                    "Authorization": f"Bearer {self.supabase_service_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "user_metadata": user_metadata
                }
            )
            
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"✅ User metadata updated for: {user_id}")
                return user_data
            else:
                logger.error(f"❌ User metadata update failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error updating user metadata: {e}")
            return None
    
    async def sign_in_with_password(
        self, 
        email: str, 
        password: str
    ) -> Optional[Dict[str, Any]]:
        """Sign in user with email and password"""
        try:
            response = await self.client.post(
                "/auth/v1/token?grant_type=password",
                headers={
                    "apikey": self.supabase_anon_key,
                    "Content-Type": "application/json"
                },
                json={
                    "email": email,
                    "password": password
                }
            )
            
            if response.status_code == 200:
                auth_data = response.json()
                logger.info(f"✅ User signed in: {email}")
                return auth_data
            else:
                logger.warning(f"⚠️ Sign in failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error signing in: {e}")
            return None
    
    async def sign_up_with_password(
        self, 
        email: str, 
        password: str,
        user_metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Sign up new user with email and password"""
        try:
            response = await self.client.post(
                "/auth/v1/signup",
                headers={
                    "apikey": self.supabase_anon_key,
                    "Content-Type": "application/json"
                },
                json={
                    "email": email,
                    "password": password,
                    "data": user_metadata or {}
                }
            )
            
            if response.status_code == 200:
                auth_data = response.json()
                logger.info(f"✅ User signed up: {email}")
                return auth_data
            else:
                logger.error(f"❌ Sign up failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error signing up: {e}")
            return None
    
    async def refresh_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh access token"""
        try:
            response = await self.client.post(
                "/auth/v1/token?grant_type=refresh_token",
                headers={
                    "apikey": self.supabase_anon_key,
                    "Content-Type": "application/json"
                },
                json={
                    "refresh_token": refresh_token
                }
            )
            
            if response.status_code == 200:
                auth_data = response.json()
                logger.info("✅ Token refreshed successfully")
                return auth_data
            else:
                logger.warning(f"⚠️ Token refresh failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error refreshing token: {e}")
            return None
    
    async def sign_out(self, access_token: str) -> bool:
        """Sign out user"""
        try:
            response = await self.client.post(
                "/auth/v1/logout",
                headers={
                    "apikey": self.supabase_anon_key,
                    "Authorization": f"Bearer {access_token}"
                }
            )
            
            if response.status_code == 204:
                logger.info("✅ User signed out successfully")
                return True
            else:
                logger.warning(f"⚠️ Sign out failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error signing out: {e}")
            return False
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

# Global auth service instance
auth_service = SupabaseAuthService()