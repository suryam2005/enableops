-- Migration 001: Create Multi-Tenant Database Schema
-- This migration creates the enhanced database tables for multi-tenant token storage
-- with encryption infrastructure and audit logging

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tenants table (enhanced for multi-tenancy)
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
    
    -- Constraints
    CONSTRAINT valid_plan CHECK (plan IN ('free', 'pro', 'enterprise')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'inactive', 'suspended', 'pending'))
);

-- Create indexes for performance optimization
CREATE INDEX IF NOT EXISTS idx_tenants_team_id ON tenants(team_id);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
CREATE INDEX IF NOT EXISTS idx_tenants_last_active ON tenants(last_active);
CREATE INDEX IF NOT EXISTS idx_tenants_created_at ON tenants(created_at);
CREATE INDEX IF NOT EXISTS idx_tenants_encryption_key_id ON tenants(encryption_key_id);

-- Installation events table for tracking
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
    
    -- Constraints
    CONSTRAINT valid_event_type CHECK (event_type IN ('app_installed', 'app_uninstalled', 'token_refreshed', 'tenant_activated', 'tenant_deactivated'))
);

-- Create indexes for installation events
CREATE INDEX IF NOT EXISTS idx_installation_events_team_id ON installation_events(team_id);
CREATE INDEX IF NOT EXISTS idx_installation_events_event_type ON installation_events(event_type);
CREATE INDEX IF NOT EXISTS idx_installation_events_created_at ON installation_events(created_at);

-- Token audit log for compliance tracking
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
    
    -- Constraints
    CONSTRAINT valid_operation CHECK (operation IN ('token_stored', 'token_retrieved', 'token_decrypted', 'token_refreshed', 'token_revoked', 'key_rotated'))
);

-- Create indexes for audit log
CREATE INDEX IF NOT EXISTS idx_token_audit_log_tenant_id ON token_audit_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_token_audit_log_operation ON token_audit_log(operation);
CREATE INDEX IF NOT EXISTS idx_token_audit_log_created_at ON token_audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_token_audit_log_success ON token_audit_log(success);

-- Encryption keys table for key management
CREATE TABLE IF NOT EXISTS encryption_keys (
    id VARCHAR(50) PRIMARY KEY,
    key_data TEXT NOT NULL,
    algorithm VARCHAR(20) DEFAULT 'AES-256-GCM',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    
    -- Constraints
    CONSTRAINT valid_key_status CHECK (status IN ('active', 'expired', 'revoked')),
    CONSTRAINT valid_algorithm CHECK (algorithm IN ('AES-256-GCM', 'AES-256-CBC'))
);

-- Create indexes for encryption keys
CREATE INDEX IF NOT EXISTS idx_encryption_keys_status ON encryption_keys(status);
CREATE INDEX IF NOT EXISTS idx_encryption_keys_expires_at ON encryption_keys(expires_at);
CREATE INDEX IF NOT EXISTS idx_encryption_keys_created_at ON encryption_keys(created_at);

-- Enhanced user_profiles table (if not exists)
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
    
    -- Unique constraint for tenant-user combination
    UNIQUE(tenant_id, slack_user_id)
);

-- Create indexes for user profiles
CREATE INDEX IF NOT EXISTS idx_user_profiles_tenant_id ON user_profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_slack_user_id ON user_profiles(slack_user_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_active ON user_profiles(active);

-- Enhanced documents table (if not exists)
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(20) NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536), -- OpenAI embedding dimension
    document_type VARCHAR(50) NOT NULL,
    metadata JSONB DEFAULT '{}',
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for documents
CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_document_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_active ON documents(active);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);

-- Chat memory table (if not exists)
CREATE TABLE IF NOT EXISTS chat_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(20) NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    message_type VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_message_type CHECK (message_type IN ('human', 'ai', 'system'))
);

-- Create indexes for chat memory
CREATE INDEX IF NOT EXISTS idx_chat_memory_tenant_id ON chat_memory(tenant_id);
CREATE INDEX IF NOT EXISTS idx_chat_memory_session_id ON chat_memory(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_memory_created_at ON chat_memory(created_at);

-- Row Level Security (RLS) policies for tenant isolation
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE installation_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_memory ENABLE ROW LEVEL SECURITY;

-- RLS policies for tenants table
CREATE POLICY tenant_isolation_policy ON tenants
    FOR ALL USING (team_id = current_setting('app.current_tenant_id', true));

-- RLS policies for installation_events table
CREATE POLICY installation_events_isolation_policy ON installation_events
    FOR ALL USING (team_id = current_setting('app.current_tenant_id', true));

-- RLS policies for token_audit_log table
CREATE POLICY token_audit_isolation_policy ON token_audit_log
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true));

-- RLS policies for user_profiles table
CREATE POLICY user_profiles_isolation_policy ON user_profiles
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true));

-- RLS policies for documents table
CREATE POLICY documents_isolation_policy ON documents
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true));

-- RLS policies for chat_memory table
CREATE POLICY chat_memory_isolation_policy ON chat_memory
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true));

-- Function to search documents with vector similarity
CREATE OR REPLACE FUNCTION search_documents(
    query_embedding VECTOR(1536),
    similarity_threshold FLOAT DEFAULT 0.7,
    result_limit INT DEFAULT 5,
    tenant_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    title VARCHAR(500),
    content TEXT,
    similarity FLOAT,
    metadata JSONB,
    document_type VARCHAR(50)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        d.id,
        d.title,
        d.content,
        (1 - (d.embedding <=> query_embedding)) as similarity,
        d.metadata,
        d.document_type
    FROM documents d
    WHERE 
        d.active = true
        AND (tenant_filter IS NULL OR d.tenant_id = tenant_filter)
        AND (1 - (d.embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY d.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at columns
CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create a function to cleanup expired tokens
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS INTEGER AS $$
DECLARE
    expired_count INTEGER;
BEGIN
    -- Mark tenants with expired tokens as inactive
    UPDATE tenants 
    SET status = 'inactive', updated_at = NOW()
    WHERE token_expires_at < NOW() AND status = 'active';
    
    GET DIAGNOSTICS expired_count = ROW_COUNT;
    
    -- Log the cleanup operation
    INSERT INTO token_audit_log (tenant_id, operation, success, metadata)
    SELECT team_id, 'token_expired', true, jsonb_build_object('expired_count', expired_count)
    FROM tenants 
    WHERE token_expires_at < NOW() AND status = 'inactive';
    
    RETURN expired_count;
END;
$$ LANGUAGE plpgsql;

-- Create a function to rotate encryption keys
CREATE OR REPLACE FUNCTION rotate_encryption_keys()
RETURNS BOOLEAN AS $$
BEGIN
    -- Mark old keys as expired
    UPDATE encryption_keys 
    SET status = 'expired', metadata = metadata || jsonb_build_object('rotated_at', NOW())
    WHERE expires_at < NOW() AND status = 'active';
    
    RETURN true;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON TABLE tenants IS 'Multi-tenant workspace information with encrypted bot tokens';
COMMENT ON TABLE installation_events IS 'Audit trail for Slack app installations and events';
COMMENT ON TABLE token_audit_log IS 'Comprehensive audit log for all token operations';
COMMENT ON TABLE encryption_keys IS 'Encryption key management for AES-256-GCM token encryption';
COMMENT ON COLUMN tenants.encrypted_bot_token IS 'AES-256-GCM encrypted Slack bot token';
COMMENT ON COLUMN tenants.encryption_key_id IS 'Reference to encryption key used for token encryption';
COMMENT ON FUNCTION search_documents IS 'Vector similarity search for tenant documents using OpenAI embeddings';
COMMENT ON FUNCTION cleanup_expired_tokens IS 'Automated cleanup of expired bot tokens';
COMMENT ON FUNCTION rotate_encryption_keys IS 'Automated rotation of encryption keys';