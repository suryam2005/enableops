"""
Database Models using Pydantic (Drizzle-style approach)
Simple, clean models without complex ORM overhead
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

# Enums for constrained values
class PlanType(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class TenantStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"

class EventType(str, Enum):
    APP_INSTALLED = "app_installed"
    APP_UNINSTALLED = "app_uninstalled"
    TOKEN_REFRESHED = "token_refreshed"
    TENANT_ACTIVATED = "tenant_activated"
    TENANT_DEACTIVATED = "tenant_deactivated"

class AuditOperation(str, Enum):
    TOKEN_STORED = "token_stored"
    TOKEN_RETRIEVED = "token_retrieved"
    TOKEN_DECRYPTED = "token_decrypted"
    TOKEN_REFRESHED = "token_refreshed"
    TOKEN_REVOKED = "token_revoked"
    KEY_ROTATED = "key_rotated"

class KeyStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"

class MessageType(str, Enum):
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"

# Database Models
class Tenant(BaseModel):
    """Multi-tenant workspace information"""
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    team_id: str = Field(..., max_length=20)
    team_name: str = Field(..., max_length=255)
    encrypted_bot_token: str
    encryption_key_id: str = Field(..., max_length=50)
    bot_user_id: str = Field(..., max_length=20)
    installed_by: str = Field(..., max_length=20)
    installer_name: str = Field(..., max_length=255)
    plan: PlanType = PlanType.FREE
    status: TenantStatus = TenantStatus.ACTIVE
    settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)
    last_active: Optional[datetime] = Field(default_factory=datetime.now)
    token_expires_at: Optional[datetime] = None

    class Config:
        use_enum_values = True

class InstallationEvent(BaseModel):
    """Audit trail for Slack app installations"""
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    team_id: str = Field(..., max_length=20)
    event_type: EventType
    event_data: Dict[str, Any]
    installer_id: Optional[str] = Field(None, max_length=20)
    installer_name: Optional[str] = Field(None, max_length=255)
    scopes: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True

class TokenAuditLog(BaseModel):
    """Audit log for token operations"""
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    tenant_id: str = Field(..., max_length=20)
    operation: AuditOperation
    success: bool
    error_message: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = Field(None, max_length=100)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True

class EncryptionKey(BaseModel):
    """Encryption key management"""
    id: str = Field(..., max_length=50)
    key_data: str
    algorithm: str = Field(default="AES-256-GCM", max_length=20)
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    expires_at: datetime
    status: KeyStatus = KeyStatus.ACTIVE
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True

class UserProfile(BaseModel):
    """User profiles for multi-tenant access"""
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    tenant_id: str = Field(..., max_length=20)
    slack_user_id: str = Field(..., max_length=20)
    full_name: str = Field(..., max_length=255)
    role: str = Field(..., max_length=100)
    department: str = Field(..., max_length=100)
    location: str = Field(..., max_length=255)
    tool_access: List[str] = Field(default_factory=list)
    permissions: Dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

class Document(BaseModel):
    """Documents for knowledge base"""
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    tenant_id: str = Field(..., max_length=20)
    title: str = Field(..., max_length=500)
    content: str
    embedding: Optional[List[float]] = None  # OpenAI embedding
    document_type: str = Field(..., max_length=50)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

class ChatMemory(BaseModel):
    """Chat memory for conversation history"""
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    tenant_id: str = Field(..., max_length=20)
    session_id: str = Field(..., max_length=100)
    message_type: MessageType
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True