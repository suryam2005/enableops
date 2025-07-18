"""
Encryption Infrastructure for Multi-Tenant Token Management
Implements AES-256-GCM encryption with key management and rotation
"""

import os
import secrets
import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import httpx

logger = logging.getLogger(__name__)

class EncryptionError(Exception):
    """Custom exception for encryption-related errors"""
    pass

class KeyManager:
    """Manages encryption keys with rotation and secure storage"""
    
    def __init__(self, supabase_client: Optional[httpx.AsyncClient] = None, supabase_url: str = None):
        self.supabase_client = supabase_client
        self.supabase_url = supabase_url
        self.key_cache = {}  # In-memory cache for active keys
        
    async def generate_key(self, key_id: Optional[str] = None) -> str:
        """Generate a new AES-256 encryption key"""
        if not key_id:
            key_id = f"key_{secrets.token_hex(16)}_{int(datetime.now().timestamp())}"
        
        # Generate 256-bit (32 bytes) key for AES-256
        key_bytes = secrets.token_bytes(32)
        key_b64 = base64.b64encode(key_bytes).decode('utf-8')
        
        # Store key in database
        await self._store_key(key_id, key_b64)
        
        # Cache the key
        self.key_cache[key_id] = {
            'key': key_b64,
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(days=90)  # 90-day rotation
        }
        
        logger.info(f"Generated new encryption key: {key_id}")
        return key_id
    
    async def get_key(self, key_id: str) -> Optional[str]:
        """Retrieve encryption key by ID"""
        # Check cache first
        if key_id in self.key_cache:
            cached_key = self.key_cache[key_id]
            if cached_key['expires_at'] > datetime.now():
                return cached_key['key']
            else:
                # Remove expired key from cache
                del self.key_cache[key_id]
        
        # Fetch from database
        if self.supabase_client and self.supabase_url:
            try:
                response = await self.supabase_client.get(
                    f"{self.supabase_url}/rest/v1/encryption_keys",
                    params={
                        "id": f"eq.{key_id}",
                        "status": "eq.active"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        key_data = data[0]
                        # Cache the key
                        self.key_cache[key_id] = {
                            'key': key_data['key_data'],
                            'created_at': datetime.fromisoformat(key_data['created_at'].replace('Z', '+00:00')),
                            'expires_at': datetime.fromisoformat(key_data['expires_at'].replace('Z', '+00:00'))
                        }
                        return key_data['key_data']
            except Exception as e:
                logger.error(f"Error fetching encryption key {key_id}: {e}")
        
        return None
    
    async def _store_key(self, key_id: str, key_data: str) -> bool:
        """Store encryption key in database"""
        if not self.supabase_client or not self.supabase_url:
            logger.warning("Supabase client not available - key storage skipped")
            return False
        
        try:
            expires_at = datetime.now() + timedelta(days=90)
            
            response = await self.supabase_client.post(
                f"{self.supabase_url}/rest/v1/encryption_keys",
                json={
                    "id": key_id,
                    "key_data": key_data,
                    "algorithm": "AES-256-GCM",
                    "expires_at": expires_at.isoformat(),
                    "status": "active",
                    "metadata": {
                        "generated_at": datetime.now().isoformat(),
                        "key_length": 256
                    }
                }
            )
            
            if response.status_code == 201:
                logger.info(f"Stored encryption key {key_id} in database")
                return True
            else:
                logger.error(f"Failed to store encryption key: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error storing encryption key: {e}")
            return False
    
    async def rotate_keys(self) -> Dict[str, Any]:
        """Rotate expired encryption keys"""
        if not self.supabase_client or not self.supabase_url:
            return {"error": "Supabase client not available"}
        
        try:
            # Mark expired keys as expired
            response = await self.supabase_client.post(
                f"{self.supabase_url}/rest/v1/rpc/rotate_encryption_keys"
            )
            
            if response.status_code == 200:
                # Clear cache of expired keys
                current_time = datetime.now()
                expired_keys = [
                    key_id for key_id, key_info in self.key_cache.items()
                    if key_info['expires_at'] <= current_time
                ]
                
                for key_id in expired_keys:
                    del self.key_cache[key_id]
                
                logger.info(f"Rotated {len(expired_keys)} expired encryption keys")
                return {"rotated_keys": len(expired_keys), "status": "success"}
            else:
                logger.error(f"Key rotation failed: {response.text}")
                return {"error": "Key rotation failed"}
                
        except Exception as e:
            logger.error(f"Error during key rotation: {e}")
            return {"error": str(e)}
    
    async def get_active_key_id(self) -> str:
        """Get or create an active encryption key ID"""
        # Check if we have any active keys in cache
        current_time = datetime.now()
        for key_id, key_info in self.key_cache.items():
            if key_info['expires_at'] > current_time:
                return key_id
        
        # Generate new key if none active
        return await self.generate_key()

class TokenEncryption:
    """Handles encryption and decryption of Slack bot tokens"""
    
    def __init__(self, key_manager: KeyManager):
        self.key_manager = key_manager
    
    async def encrypt_token(self, token: str, tenant_id: str) -> Tuple[str, str]:
        """
        Encrypt a Slack bot token using AES-256-GCM
        Returns: (encrypted_token_b64, key_id)
        """
        try:
            # Get active encryption key
            key_id = await self.key_manager.get_active_key_id()
            key_b64 = await self.key_manager.get_key(key_id)
            
            if not key_b64:
                raise EncryptionError(f"Could not retrieve encryption key: {key_id}")
            
            # Decode the base64 key
            key_bytes = base64.b64decode(key_b64)
            
            # Create AESGCM cipher
            aesgcm = AESGCM(key_bytes)
            
            # Generate nonce (96 bits for GCM)
            nonce = secrets.token_bytes(12)
            
            # Additional authenticated data (AAD) - includes tenant_id for binding
            aad = f"tenant:{tenant_id}".encode('utf-8')
            
            # Encrypt the token
            ciphertext = aesgcm.encrypt(nonce, token.encode('utf-8'), aad)
            
            # Combine nonce + ciphertext and encode as base64
            encrypted_data = nonce + ciphertext
            encrypted_token_b64 = base64.b64encode(encrypted_data).decode('utf-8')
            
            logger.info(f"Successfully encrypted token for tenant {tenant_id}")
            return encrypted_token_b64, key_id
            
        except Exception as e:
            logger.error(f"Token encryption failed for tenant {tenant_id}: {e}")
            raise EncryptionError(f"Token encryption failed: {str(e)}")
    
    async def decrypt_token(self, encrypted_token_b64: str, key_id: str, tenant_id: str) -> str:
        """
        Decrypt a Slack bot token using AES-256-GCM
        """
        try:
            # Get encryption key
            key_b64 = await self.key_manager.get_key(key_id)
            
            if not key_b64:
                raise EncryptionError(f"Could not retrieve encryption key: {key_id}")
            
            # Decode the base64 key and encrypted data
            key_bytes = base64.b64decode(key_b64)
            encrypted_data = base64.b64decode(encrypted_token_b64)
            
            # Extract nonce (first 12 bytes) and ciphertext
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]
            
            # Create AESGCM cipher
            aesgcm = AESGCM(key_bytes)
            
            # Additional authenticated data (AAD) - must match encryption
            aad = f"tenant:{tenant_id}".encode('utf-8')
            
            # Decrypt the token
            plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
            token = plaintext.decode('utf-8')
            
            logger.info(f"Successfully decrypted token for tenant {tenant_id}")
            return token
            
        except Exception as e:
            logger.error(f"Token decryption failed for tenant {tenant_id}: {e}")
            raise EncryptionError(f"Token decryption failed: {str(e)}")
    
    async def validate_token_format(self, token: str) -> bool:
        """Validate that token follows Slack bot token format"""
        if not token or not isinstance(token, str):
            return False
        
        # Slack bot tokens start with 'xoxb-'
        if not token.startswith('xoxb-'):
            return False
        
        # Basic length check (Slack tokens are typically 50+ characters)
        if len(token) < 50:
            return False
        
        return True

class AuditLogger:
    """Logs encryption/decryption operations for compliance"""
    
    def __init__(self, supabase_client: Optional[httpx.AsyncClient] = None, supabase_url: str = None):
        self.supabase_client = supabase_client
        self.supabase_url = supabase_url
    
    async def log_operation(
        self, 
        tenant_id: str, 
        operation: str, 
        success: bool, 
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> bool:
        """Log encryption/decryption operation for audit trail"""
        
        if not self.supabase_client or not self.supabase_url:
            # Log to application logs as fallback
            log_entry = {
                "tenant_id": tenant_id,
                "operation": operation,
                "success": success,
                "error_message": error_message,
                "metadata": metadata or {},
                "timestamp": datetime.now().isoformat()
            }
            logger.info(f"Audit log (fallback): {json.dumps(log_entry)}")
            return True
        
        try:
            response = await self.supabase_client.post(
                f"{self.supabase_url}/rest/v1/token_audit_log",
                json={
                    "tenant_id": tenant_id,
                    "operation": operation,
                    "success": success,
                    "error_message": error_message,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "request_id": request_id,
                    "metadata": metadata or {}
                }
            )
            
            if response.status_code == 201:
                return True
            else:
                logger.error(f"Failed to log audit entry: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error logging audit entry: {e}")
            return False

# Global instances (to be initialized in main.py)
key_manager: Optional[KeyManager] = None
token_encryption: Optional[TokenEncryption] = None
audit_logger: Optional[AuditLogger] = None

def initialize_encryption(supabase_client: Optional[httpx.AsyncClient] = None, supabase_url: str = None):
    """Initialize encryption infrastructure"""
    global key_manager, token_encryption, audit_logger
    
    key_manager = KeyManager(supabase_client, supabase_url)
    token_encryption = TokenEncryption(key_manager)
    audit_logger = AuditLogger(supabase_client, supabase_url)
    
    logger.info("✅ Encryption infrastructure initialized")

async def encrypt_slack_token(token: str, tenant_id: str, ip_address: str = None, user_agent: str = None) -> Tuple[str, str]:
    """
    High-level function to encrypt a Slack token with audit logging
    Returns: (encrypted_token, key_id)
    """
    if not token_encryption or not audit_logger:
        raise EncryptionError("Encryption infrastructure not initialized")
    
    try:
        # Validate token format
        if not await token_encryption.validate_token_format(token):
            await audit_logger.log_operation(
                tenant_id, "token_stored", False, 
                "Invalid token format", 
                {"validation": "failed"},
                ip_address, user_agent
            )
            raise EncryptionError("Invalid Slack token format")
        
        # Encrypt the token
        encrypted_token, key_id = await token_encryption.encrypt_token(token, tenant_id)
        
        # Log successful encryption
        await audit_logger.log_operation(
            tenant_id, "token_stored", True, 
            None, 
            {"key_id": key_id, "token_length": len(token)},
            ip_address, user_agent
        )
        
        return encrypted_token, key_id
        
    except Exception as e:
        # Log failed encryption
        await audit_logger.log_operation(
            tenant_id, "token_stored", False, 
            str(e), 
            {"error_type": type(e).__name__},
            ip_address, user_agent
        )
        raise

async def decrypt_slack_token(encrypted_token: str, key_id: str, tenant_id: str, ip_address: str = None, user_agent: str = None) -> str:
    """
    High-level function to decrypt a Slack token with audit logging
    """
    if not token_encryption or not audit_logger:
        raise EncryptionError("Encryption infrastructure not initialized")
    
    try:
        # Decrypt the token
        token = await token_encryption.decrypt_token(encrypted_token, key_id, tenant_id)
        
        # Log successful decryption
        await audit_logger.log_operation(
            tenant_id, "token_retrieved", True, 
            None, 
            {"key_id": key_id},
            ip_address, user_agent
        )
        
        return token
        
    except Exception as e:
        # Log failed decryption
        await audit_logger.log_operation(
            tenant_id, "token_retrieved", False, 
            str(e), 
            {"key_id": key_id, "error_type": type(e).__name__},
            ip_address, user_agent
        )
        raise