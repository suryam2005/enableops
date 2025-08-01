"""
Encryption Service for Slack Tokens
Handles secure encryption and decryption of sensitive data
"""

import os
import base64
import secrets
import logging
from typing import Tuple, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Global encryption key
_encryption_key: Optional[bytes] = None

def initialize_encryption():
    """Initialize encryption system with master key"""
    global _encryption_key
    
    try:
        # Get master key from environment or generate one
        master_key = os.getenv("ENCRYPTION_MASTER_KEY")
        
        if not master_key:
            # Generate a new master key (for development)
            master_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
            logger.warning("⚠️ Generated new encryption master key. Set ENCRYPTION_MASTER_KEY in production!")
            logger.info(f"Generated master key: {master_key}")
        
        # Derive encryption key from master key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'enableops_salt',  # In production, use a random salt per key
            iterations=100000,
        )
        
        _encryption_key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        logger.info("✅ Encryption system initialized")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize encryption: {e}")
        raise

def get_encryption_key() -> bytes:
    """Get the current encryption key"""
    if _encryption_key is None:
        raise RuntimeError("Encryption not initialized. Call initialize_encryption() first.")
    return _encryption_key

async def encrypt_slack_token(token: str, team_id: str, client_ip: str = None, user_agent: str = None) -> Tuple[str, str]:
    """
    Encrypt Slack token with additional context
    Returns: (encrypted_token, key_id)
    """
    try:
        # Get encryption key
        key = get_encryption_key()
        cipher_suite = Fernet(key)
        
        # Create token data with metadata
        token_data = {
            "token": token,
            "team_id": team_id,
            "encrypted_at": secrets.token_hex(16),  # Random nonce
            "client_ip": client_ip,
            "user_agent": user_agent
        }
        
        # Serialize and encrypt
        import json
        token_json = json.dumps(token_data)
        encrypted_token = cipher_suite.encrypt(token_json.encode())
        
        # Generate key ID for tracking
        key_id = f"key_{team_id}_{secrets.token_hex(8)}"
        
        # Return base64 encoded encrypted token
        return base64.urlsafe_b64encode(encrypted_token).decode(), key_id
        
    except Exception as e:
        logger.error(f"❌ Token encryption failed: {e}")
        raise

async def decrypt_slack_token(encrypted_token: str, key_id: str) -> Optional[str]:
    """
    Decrypt Slack token
    Returns: decrypted token or None if failed
    """
    try:
        # Get encryption key
        key = get_encryption_key()
        cipher_suite = Fernet(key)
        
        # Decode and decrypt
        encrypted_data = base64.urlsafe_b64decode(encrypted_token.encode())
        decrypted_data = cipher_suite.decrypt(encrypted_data)
        
        # Parse token data
        import json
        token_data = json.loads(decrypted_data.decode())
        
        return token_data.get("token")
        
    except Exception as e:
        logger.error(f"❌ Token decryption failed: {e}")
        return None

def encrypt_string(data: str) -> str:
    """Encrypt a string and return base64 encoded result"""
    try:
        key = get_encryption_key()
        cipher_suite = Fernet(key)
        encrypted_data = cipher_suite.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted_data).decode()
    except Exception as e:
        logger.error(f"❌ String encryption failed: {e}")
        raise

def decrypt_string(encrypted_data: str) -> Optional[str]:
    """Decrypt a base64 encoded encrypted string"""
    try:
        key = get_encryption_key()
        cipher_suite = Fernet(key)
        decoded_data = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted_data = cipher_suite.decrypt(decoded_data)
        return decrypted_data.decode()
    except Exception as e:
        logger.error(f"❌ String decryption failed: {e}")
        return None