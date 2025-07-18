# EnableBot - Multi-Tenant Slack AI Assistant

## 🏗️ Architecture Overview

EnableBot is a production-ready, multi-tenant Slack AI assistant with encrypted token storage and scalable architecture.

### 📁 Project Structure

```
enablebot/
├── api/                    # AI Backend Service
│   ├── __init__.py
│   └── main.py            # FastAPI app for Slack events
├── web/                   # Web Interface
│   ├── __init__.py
│   ├── main.py           # Web app for OAuth/dashboard
│   ├── auth.py           # Slack OAuth handling
│   └── templates/        # HTML templates
├── shared/               # Shared Components
│   ├── database/         # Database layer
│   ├── encryption/       # Token encryption
│   └── models/          # Data models
├── config/              # Configuration
│   ├── __init__.py
│   └── settings.py      # Centralized settings
├── scripts/             # Startup Scripts
│   ├── start_api.py     # Start AI backend
│   └── start_web.py     # Start web interface
├── tests/               # Test Suite
└── docs/                # Documentation
```

## 🚀 Services

### 1. API Service (`enablebot/api/`)
- **Purpose**: Multi-tenant AI backend for Slack events
- **Port**: 8001 (configurable)
- **Features**:
  - Handles Slack events from all workspaces
  - Dynamically retrieves encrypted bot tokens
  - Tenant-aware AI responses
  - Document upload and knowledge base

### 2. Web Service (`enablebot/web/`)
- **Purpose**: Slack OAuth and installation dashboard
- **Port**: 8000 (configurable)
- **Features**:
  - Slack app installation flow
  - OAuth callback handling
  - Installation dashboard
  - Token encryption and storage

## 🔧 Configuration

### Environment Variables

```bash
# Database
SUPABASE_URL=your-supabase-url
SUPABASE_SERVICE_KEY=your-service-key
SUPABASE_DB_PASSWORD=your-db-password

# AI Services
OPENAI_API_KEY=your-openai-key

# Slack OAuth
SLACK_CLIENT_ID=your-client-id
SLACK_CLIENT_SECRET=your-client-secret
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_REDIRECT_URI=https://your-domain.com/slack/oauth/callback

# Server
HOST=0.0.0.0
API_PORT=8001
WEB_PORT=8000
LOG_LEVEL=INFO
```

## 🏃‍♂️ Running Services

### Development (Local)

```bash
# Terminal 1: Start API service
python enablebot/scripts/start_api.py

# Terminal 2: Start web interface
python enablebot/scripts/start_web.py
```

### Production (Railway/Docker)

```bash
# API Service
python -m enablebot.scripts.start_api

# Web Interface  
python -m enablebot.scripts.start_web
```

## 🔐 Security Features

- **Token Encryption**: AES-256-GCM encryption for all bot tokens
- **Tenant Isolation**: Complete data isolation per workspace
- **Audit Logging**: Comprehensive operation logging
- **Signature Verification**: Slack request verification
- **Environment Security**: No secrets in code

## 📊 Multi-Tenant Support

- **Unlimited Workspaces**: Supports any number of Slack workspaces
- **Dynamic Token Management**: Retrieves correct token per workspace
- **Isolated Data**: Each workspace has separate data
- **Personalized AI**: Context-aware responses per company

## 🧪 Testing

```bash
# Run all tests
python -m pytest enablebot/tests/

# Test specific component
python -m pytest enablebot/tests/test_api.py
```

## 📈 Scaling

The architecture is designed for horizontal scaling:

- **Stateless Services**: Both API and web services are stateless
- **Database Pooling**: Connection pooling for performance
- **Async Processing**: Non-blocking operations
- **Caching**: Client caching for performance
- **Load Balancing**: Can run multiple instances

## 🚀 Deployment

See deployment guides:
- [Railway Deployment](../../RAILWAY_DEPLOYMENT.md)
- [Docker Deployment](./DOCKER_DEPLOYMENT.md)
- [Production Setup](./PRODUCTION_SETUP.md)

## 🔍 Monitoring

- **Health Checks**: `/health` endpoints on both services
- **Logging**: Structured logging with levels
- **Metrics**: Built-in performance metrics
- **Error Tracking**: Comprehensive error handling

## 🤝 Contributing

1. Follow the existing architecture patterns
2. Add tests for new features
3. Update documentation
4. Use type hints and docstrings
5. Follow security best practices