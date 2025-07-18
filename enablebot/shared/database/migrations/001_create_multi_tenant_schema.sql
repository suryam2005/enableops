-- EnableBot Multi-Tenant Database Schema
-- Creates all necessary tables for multi-tenant Slack bot functionality

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tenants table - stores workspace/team information with encrypted bot tokens
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id VARCHAR(20) UNIQUE NOT NULL,
    team_name VARCHAR(255) NOT NULL,
    encrypted_bot_token TEXT NOT NULL,
    encryption_key_id VARCHAR(255) NOT NULL,
    bot_user_id VARCHAR(20),
    installer_user_id VARCHAR(20),
    installer_name VARCHAR(255),
    scopes JSONB DEFAULT '[]'::jsonb,
    settings JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Installation events table - audit log of installations and changes
CREATE TABLE IF NOT EXISTS installation_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id VARCHAR(20) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    installer_user_id VARCHAR(20),
    installer_name VARCHAR(255),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User profiles table - stores user information per tenant
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(20) NOT NULL,
    slack_user_id VARCHAR(20) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(100),
    department VARCHAR(100),
    location VARCHAR(100),
    tool_access JSONB DEFAULT '[]'::jsonb,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, slack_user_id)
);

-- Documents table - knowledge base documents per tenant
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(20) NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    embedding JSONB,
    document_type VARCHAR(100),
    metadata JSONB DEFAULT '{}'::jsonb,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chat memory table - conversation history per tenant
CREATE TABLE IF NOT EXISTS chat_memory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(20) NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    message_type VARCHAR(20) NOT NULL, -- 'human' or 'ai'
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Token audit log table - security audit trail
CREATE TABLE IF NOT EXISTS token_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(20) NOT NULL,
    operation VARCHAR(50) NOT NULL, -- 'token_stored', 'token_retrieved', etc.
    success BOOLEAN NOT NULL,
    error_message TEXT,
    ip_address INET,
    user_agent TEXT,
    request_id VARCHAR(100),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Encryption keys table - manages encryption keys with rotation
CREATE TABLE IF NOT EXISTS encryption_keys (
    id VARCHAR(100) PRIMARY KEY,
    key_data TEXT NOT NULL,
    algorithm VARCHAR(50) DEFAULT 'AES-256-GCM',
    status VARCHAR(20) DEFAULT 'active',
    expires_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tenants_team_id ON tenants(team_id);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
CREATE INDEX IF NOT EXISTS idx_installation_events_team_id ON installation_events(team_id);
CREATE INDEX IF NOT EXISTS idx_installation_events_created_at ON installation_events(created_at);
CREATE INDEX IF NOT EXISTS idx_user_profiles_tenant_slack ON user_profiles(tenant_id, slack_user_id);
CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_active ON documents(active);
CREATE INDEX IF NOT EXISTS idx_chat_memory_session ON chat_memory(tenant_id, session_id);
CREATE INDEX IF NOT EXISTS idx_chat_memory_created_at ON chat_memory(created_at);
CREATE INDEX IF NOT EXISTS idx_token_audit_tenant ON token_audit_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_token_audit_created_at ON token_audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_encryption_keys_status ON encryption_keys(status);

-- Row Level Security (RLS) policies for multi-tenancy
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE installation_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_audit_log ENABLE ROW LEVEL SECURITY;

-- Create policies (these will be refined based on your auth setup)
CREATE POLICY IF NOT EXISTS "Enable read access for service role" ON tenants FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "Enable read access for service role" ON installation_events FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "Enable read access for service role" ON user_profiles FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "Enable read access for service role" ON documents FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "Enable read access for service role" ON chat_memory FOR ALL USING (true);
CREATE POLICY IF NOT EXISTS "Enable read access for service role" ON token_audit_log FOR ALL USING (true);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers to automatically update updated_at
CREATE TRIGGER IF NOT EXISTS update_tenants_updated_at BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER IF NOT EXISTS update_user_profiles_updated_at BEFORE UPDATE ON user_profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER IF NOT EXISTS update_documents_updated_at BEFORE UPDATE ON documents FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();