"""
Simple Database Initialization (Drizzle-style approach)
Creates database schema directly with SQL
"""

import os
import asyncio
import logging
from pathlib import Path

# Import database components
from database.config import db, init_database
from encryption import initialize_encryption, key_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database schema SQL
CREATE_SCHEMA_SQL = """
-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id VARCHAR(20) UNIQUE NOT NULL,
    team_name VARCHAR(255) NOT NULL,
    encrypted_bot_token TEXT NOT NULL,
    encryption_key_id VARCHAR(50) NOT NULL,
    bot_user_id VARCHAR(20) NOT NULL,
    installed_by VARCHAR(20) NOT NULL,
    installer_name VARCHAR(255) NOT NULL,
    plan VARCHAR(20) DEFAULT 'free',
    status VARCHAR(20) DEFAULT 'active',
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    token_expires_at TIMESTAMP WITH TIME ZONE,
    
    CONSTRAINT valid_plan CHECK (plan IN ('free', 'pro', 'enterprise')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'inactive', 'suspended', 'pending'))
);

-- Installation events table
CREATE TABLE IF NOT EXISTS installation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id VARCHAR(20) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL,
    installer_id VARCHAR(20),
    installer_name VARCHAR(255),
    scopes TEXT[],
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_event_type CHECK (event_type IN ('app_installed', 'app_uninstalled', 'token_refreshed', 'tenant_activated', 'tenant_deactivated'))
);

-- Token audit log table
CREATE TABLE IF NOT EXISTS token_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(20) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    ip_address INET,
    user_agent TEXT,
    request_id VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_operation CHECK (operation IN ('token_stored', 'token_retrieved', 'token_decrypted', 'token_refreshed', 'token_revoked', 'key_rotated'))
);

-- Encryption keys table
CREATE TABLE IF NOT EXISTS encryption_keys (
    id VARCHAR(50) PRIMARY KEY,
    key_data TEXT NOT NULL,
    algorithm VARCHAR(20) DEFAULT 'AES-256-GCM',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_key_status CHECK (status IN ('active', 'expired', 'revoked')),
    CONSTRAINT valid_algorithm CHECK (algorithm IN ('AES-256-GCM', 'AES-256-CBC'))
);

-- User profiles table
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(20) NOT NULL,
    slack_user_id VARCHAR(20) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(100) NOT NULL,
    department VARCHAR(100) NOT NULL,
    location VARCHAR(255) NOT NULL,
    tool_access TEXT[] DEFAULT '{}',
    permissions JSONB DEFAULT '{}',
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(tenant_id, slack_user_id)
);

-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(20) NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    embedding TEXT,
    document_type VARCHAR(50) NOT NULL,
    metadata JSONB DEFAULT '{}',
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chat memory table
CREATE TABLE IF NOT EXISTS chat_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(20) NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    message_type VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_message_type CHECK (message_type IN ('human', 'ai', 'system'))
);
"""

CREATE_INDEXES_SQL = """
-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_tenants_team_id ON tenants(team_id);
CREATE INDEX IF NOT EXISTS idx_tenants_last_active ON tenants(last_active);

CREATE INDEX IF NOT EXISTS idx_installation_events_team_id ON installation_events(team_id);
CREATE INDEX IF NOT EXISTS idx_installation_events_event_type ON installation_events(event_type);

CREATE INDEX IF NOT EXISTS idx_token_audit_log_tenant_id ON token_audit_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_token_audit_log_operation ON token_audit_log(operation);
CREATE INDEX IF NOT EXISTS idx_token_audit_log_created_at ON token_audit_log(created_at);

CREATE INDEX IF NOT EXISTS idx_encryption_keys_status ON encryption_keys(status);
CREATE INDEX IF NOT EXISTS idx_encryption_keys_expires_at ON encryption_keys(expires_at);

CREATE INDEX IF NOT EXISTS idx_user_profiles_tenant_id ON user_profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_slack_user_id ON user_profiles(slack_user_id);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_active ON documents(active);

CREATE INDEX IF NOT EXISTS idx_chat_memory_tenant_id ON chat_memory(tenant_id);
CREATE INDEX IF NOT EXISTS idx_chat_memory_session_id ON chat_memory(session_id);
"""

async def check_table_exists(table_name: str) -> bool:
    """Check if a table exists"""
    try:
        result = await db.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        """, table_name)
        return result
    except Exception as e:
        logger.debug(f"Table check failed for {table_name}: {e}")
        return False

async def create_database_schema() -> bool:
    """Create database schema"""
    try:
        logger.info("🚀 Creating database schema...")
        
        # Execute schema creation SQL
        await db.execute(CREATE_SCHEMA_SQL)
        logger.info("✅ Database tables created")
        
        # Create indexes
        await db.execute(CREATE_INDEXES_SQL)
        logger.info("✅ Database indexes created")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to create database schema: {e}")
        return False

async def verify_schema() -> bool:
    """Verify database schema exists"""
    try:
        logger.info("🔍 Verifying database schema...")
        
        required_tables = [
            'tenants', 'installation_events', 'token_audit_log', 
            'encryption_keys', 'user_profiles', 'documents', 'chat_memory'
        ]
        
        for table in required_tables:
            exists = await check_table_exists(table)
            if exists:
                logger.info(f"✅ Table '{table}' exists")
            else:
                logger.error(f"❌ Table '{table}' not found")
                return False
        
        logger.info("✅ Database schema verification successful")
        return True
        
    except Exception as e:
        logger.error(f"❌ Schema verification failed: {e}")
        return False

async def create_initial_encryption_key() -> bool:
    """Create the first encryption key"""
    try:
        logger.info("🔑 Creating initial encryption key...")
        
        # Initialize encryption infrastructure
        initialize_encryption()
        
        # Generate initial key
        if key_manager:
            key_id = await key_manager.generate_key()
            logger.info(f"✅ Created initial encryption key: {key_id}")
            return True
        else:
            logger.error("❌ Key manager not initialized")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to create initial encryption key: {e}")
        return False

async def test_database_operations() -> bool:
    """Test basic database operations"""
    try:
        logger.info("🧪 Testing database operations...")
        
        # Test basic query
        result = await db.fetchval("SELECT 1 as test")
        if result != 1:
            logger.error("❌ Basic query test failed")
            return False
        
        # Test table count
        table_count = await db.fetchval("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('tenants', 'installation_events', 'token_audit_log', 'encryption_keys')
        """)
        
        if table_count < 4:
            logger.error(f"❌ Expected at least 4 tables, found {table_count}")
            return False
        
        logger.info("✅ Database operations test successful")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database operations test failed: {e}")
        return False

async def initialize_database_complete() -> bool:
    """Complete database initialization"""
    logger.info("🚀 Starting database initialization...")
    
    try:
        # Step 1: Initialize database connection
        logger.info("📡 Initializing database connection...")
        if not await init_database():
            logger.error("❌ Failed to initialize database connection")
            return False
        
        # Step 2: Check if schema needs to be created/updated
        tenants_exists = await check_table_exists('tenants')
        audit_log_exists = await check_table_exists('token_audit_log')
        
        if tenants_exists and audit_log_exists:
            logger.info("✅ Database schema already exists")
        else:
            # Step 3: Create/update database schema
            logger.info("🔧 Creating/updating database schema...")
            if not await create_database_schema():
                logger.error("❌ Failed to create database schema")
                return False
        
        # Step 4: Verify schema
        if not await verify_schema():
            logger.error("❌ Schema verification failed")
            return False
        
        # Step 5: Test database operations
        if not await test_database_operations():
            logger.error("❌ Database operations test failed")
            return False
        
        # Step 6: Create initial encryption key
        if not await create_initial_encryption_key():
            logger.warning("⚠️  Failed to create encryption key, but continuing...")
        
        logger.info("✅ Database initialization completed successfully!")
        logger.info("🎉 Multi-tenant infrastructure is ready!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False
    
    finally:
        # Clean up database connections
        await db.close()

async def main():
    """Main initialization function"""
    success = await initialize_database_complete()
    if not success:
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())