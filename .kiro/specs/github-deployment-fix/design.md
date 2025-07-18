# Design Document

## Overview

We need to recreate the complete EnableBot project structure that was accidentally deleted during git operations. The project is a multi-tenant Slack AI assistant with proper microservices architecture, encryption, and Railway deployment capabilities.

## Architecture

### Project Structure
```
enableops/
├── enablebot/                          # Main Application Package
│   ├── __init__.py                     # Package initialization
│   ├── api/                            # AI Backend Service
│   │   ├── __init__.py
│   │   └── main.py                     # FastAPI app for Slack events
│   ├── web/                            # Web Interface Service
│   │   ├── __init__.py
│   │   ├── main.py                     # Web app for OAuth/dashboard
│   │   ├── auth.py                     # Slack OAuth handling
│   │   └── templates/                  # HTML templates
│   │       ├── index.html              # Landing page
│   │       └── dashboard.html          # Installation dashboard
│   ├── shared/                         # Shared Components
│   │   ├── __init__.py
│   │   ├── database/                   # Database layer
│   │   │   ├── __init__.py
│   │   │   ├── config.py               # Database connection
│   │   │   ├── models.py               # Pydantic models
│   │   │   ├── init_db.py              # Database initialization
│   │   │   └── migrations/             # SQL migrations
│   │   │       └── 001_create_multi_tenant_schema.sql
│   │   ├── encryption/                 # Security layer
│   │   │   ├── __init__.py
│   │   │   └── encryption.py           # AES-256-GCM encryption
│   │   └── models/                     # Data models
│   │       └── __init__.py
│   ├── config/                         # Configuration
│   │   ├── __init__.py
│   │   └── settings.py                 # Centralized settings
│   └── scripts/                        # Startup Scripts
│       ├── __init__.py
│       ├── start_api.py                # Start AI backend
│       └── start_web.py                # Start web interface
├── .env                                # Environment variables
├── requirements.txt                    # Python dependencies
├── railway.toml                        # Railway deployment config
├── Procfile                           # Process definition
└── runtime.txt                        # Python version
```

## Components and Interfaces

### API Service (enablebot/api/main.py)
- Multi-tenant Slack client management
- Tenant-aware AI processing with OpenAI
- Dynamic token decryption per workspace
- Knowledge base search and document processing
- Chat history management
- Slack event handling and signature verification

### Web Service (enablebot/web/)
- Slack OAuth flow handling
- Token encryption before storage
- Installation dashboard
- Tenant onboarding process

### Shared Components
- Database connection and ORM-like operations
- AES-256-GCM encryption for Slack tokens
- Centralized configuration management
- Startup scripts for both services

## Data Models

### Database Schema
- tenants: Store encrypted bot tokens and team info
- user_profiles: User information per tenant
- documents: Knowledge base documents with embeddings
- chat_memory: Conversation history
- installation_events: Installation tracking
- token_audit_log: Security audit trail

### Pydantic Models
- SlackEvent, SlackEventWrapper: Slack API event handling
- ChatRequest: Direct chat API requests
- User profiles and tenant information models

## Error Handling

- Comprehensive logging throughout
- Graceful degradation when services unavailable
- Proper HTTP status codes and error messages
- Slack signature verification for security

## Testing Strategy

- Exclude test files from git to avoid GitHub secret detection
- Mock tokens that don't trigger security scanners
- Unit tests for encryption, database, and API endpoints
- Integration tests for complete workflows