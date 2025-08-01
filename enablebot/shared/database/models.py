"""
Database Models and Operations
Handles all database operations using Prisma ORM
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from prisma.models import UserProfile, Tenant, InstallationEvent, KnowledgeBase, EncryptionKey
from prisma.enums import PlanType, TenantStatus, EventType
from .prisma_client import get_db

logger = logging.getLogger(__name__)

class UserProfileService:
    """Service for user profile operations"""
    
    @staticmethod
    async def create_or_update_user(
        supabase_user_id: str,
        email: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> UserProfile:
        """Create or update user profile"""
        async with get_db() as db:
            return await db.userprofile.upsert(
                where={"supabaseUserId": supabase_user_id},
                data={
                    "create": {
                        "supabaseUserId": supabase_user_id,
                        "email": email,
                        "fullName": full_name,
                        "avatarUrl": avatar_url
                    },
                    "update": {
                        "email": email,
                        "fullName": full_name,
                        "avatarUrl": avatar_url,
                        "updatedAt": datetime.now()
                    }
                }
            )
    
    @staticmethod
    async def get_user_by_supabase_id(supabase_user_id: str) -> Optional[UserProfile]:
        """Get user by Supabase user ID"""
        async with get_db() as db:
            return await db.userprofile.find_unique(
                where={"supabaseUserId": supabase_user_id}
            )
    
    @staticmethod
    async def get_user_by_email(email: str) -> Optional[UserProfile]:
        """Get user by email"""
        async with get_db() as db:
            return await db.userprofile.find_unique(
                where={"email": email}
            )

class TenantService:
    """Service for tenant operations"""
    
    @staticmethod
    async def create_tenant(
        team_id: str,
        team_name: str,
        encrypted_bot_token: str,
        bot_user_id: str,
        installed_by: str,
        installer_name: str,
        supabase_user_id: Optional[str] = None,
        installer_email: Optional[str] = None,
        encryption_key_id: Optional[str] = None,
        plan: PlanType = PlanType.FREE,
        settings: Dict[str, Any] = None
    ) -> Tenant:
        """Create a new tenant"""
        async with get_db() as db:
            return await db.tenant.create(
                data={
                    "teamId": team_id,
                    "teamName": team_name,
                    "encryptedBotToken": encrypted_bot_token,
                    "encryptionKeyId": encryption_key_id,
                    "botUserId": bot_user_id,
                    "installedBy": installed_by,
                    "installerName": installer_name,
                    "installerEmail": installer_email,
                    "supabaseUserId": supabase_user_id,
                    "plan": plan,
                    "status": TenantStatus.ACTIVE,
                    "settings": settings or {},
                    "lastActive": datetime.now()
                }
            )
    
    @staticmethod
    async def update_tenant(
        team_id: str,
        **updates
    ) -> Optional[Tenant]:
        """Update tenant information"""
        async with get_db() as db:
            return await db.tenant.update(
                where={"teamId": team_id},
                data={
                    **updates,
                    "updatedAt": datetime.now()
                }
            )
    
    @staticmethod
    async def get_tenant_by_team_id(team_id: str) -> Optional[Tenant]:
        """Get tenant by team ID"""
        async with get_db() as db:
            return await db.tenant.find_unique(
                where={"teamId": team_id},
                include={"userProfile": True}
            )
    
    @staticmethod
    async def get_user_tenants(supabase_user_id: str) -> List[Tenant]:
        """Get all tenants for a user"""
        async with get_db() as db:
            return await db.tenant.find_many(
                where={
                    "supabaseUserId": supabase_user_id,
                    "status": TenantStatus.ACTIVE
                },
                include={"userProfile": True}
            )
    
    @staticmethod
    async def get_active_tenants() -> List[Tenant]:
        """Get all active tenants"""
        async with get_db() as db:
            return await db.tenant.find_many(
                where={"status": TenantStatus.ACTIVE},
                include={"userProfile": True}
            )

class InstallationEventService:
    """Service for installation event operations"""
    
    @staticmethod
    async def create_event(
        team_id: str,
        event_type: EventType,
        event_data: Dict[str, Any],
        installer_id: str,
        installer_name: str,
        scopes: List[str],
        supabase_user_id: Optional[str] = None,
        metadata: Dict[str, Any] = None
    ) -> InstallationEvent:
        """Create installation event"""
        async with get_db() as db:
            return await db.installationevent.create(
                data={
                    "teamId": team_id,
                    "eventType": event_type,
                    "eventData": event_data,
                    "installerId": installer_id,
                    "installerName": installer_name,
                    "scopes": scopes,
                    "supabaseUserId": supabase_user_id,
                    "metadata": metadata or {}
                }
            )
    
    @staticmethod
    async def get_team_events(team_id: str) -> List[InstallationEvent]:
        """Get all events for a team"""
        async with get_db() as db:
            return await db.installationevent.find_many(
                where={"teamId": team_id},
                order={"createdAt": "desc"}
            )

class KnowledgeBaseService:
    """Service for knowledge base operations"""
    
    @staticmethod
    async def create_knowledge_item(
        team_id: str,
        title: str,
        content: str,
        content_type: str,
        source: Optional[str] = None,
        metadata: Dict[str, Any] = None
    ) -> KnowledgeBase:
        """Create knowledge base item"""
        async with get_db() as db:
            return await db.knowledgebase.create(
                data={
                    "teamId": team_id,
                    "title": title,
                    "content": content,
                    "contentType": content_type,
                    "source": source,
                    "metadata": metadata or {}
                }
            )
    
    @staticmethod
    async def get_team_knowledge(team_id: str) -> List[KnowledgeBase]:
        """Get all knowledge items for a team"""
        async with get_db() as db:
            return await db.knowledgebase.find_many(
                where={"teamId": team_id},
                order={"createdAt": "desc"}
            )

class EncryptionKeyService:
    """Service for encryption key operations"""
    
    @staticmethod
    async def create_encryption_key(
        key_id: str,
        key_data: str,
        algorithm: str = "AES-256-GCM"
    ) -> EncryptionKey:
        """Create encryption key"""
        async with get_db() as db:
            return await db.encryptionkey.create(
                data={
                    "keyId": key_id,
                    "keyData": key_data,
                    "algorithm": algorithm,
                    "isActive": True
                }
            )
    
    @staticmethod
    async def get_active_key(key_id: str) -> Optional[EncryptionKey]:
        """Get active encryption key"""
        async with get_db() as db:
            return await db.encryptionkey.find_unique(
                where={"keyId": key_id}
            )