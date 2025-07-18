# 🚀 EnableBot Scaling Guide

## 📁 Production Architecture

EnableBot is designed with a microservices architecture for horizontal scaling:

```
┌─────────────────┐    ┌─────────────────┐
│   Web Service   │    │   API Service   │
│   (Port 8000)   │    │   (Port 8001)   │
│                 │    │                 │
│ • OAuth Flow    │    │ • Slack Events  │
│ • Dashboard     │    │ • AI Processing │
│ • Installation  │    │ • Multi-tenant  │
└─────────────────┘    └─────────────────┘
         │                       │
         └───────────┬───────────┘
                     │
         ┌─────────────────┐
         │ Shared Database │
         │   (Supabase)    │
         │                 │
         │ • Encrypted     │
         │   Tokens        │
         │ • Tenant Data   │
         │ • Audit Logs    │
         └─────────────────┘
```

## 🏗️ Folder Structure Benefits

### 1. **Separation of Concerns**
```
enablebot/
├── api/          # AI Backend (Stateless)
├── web/          # OAuth Interface (Stateless)  
├── shared/       # Common Components
│   ├── database/ # Database layer
│   ├── encryption/ # Security layer
│   └── models/   # Data models
└── config/       # Centralized settings
```

### 2. **Independent Scaling**
- **API Service**: Scale based on Slack event volume
- **Web Service**: Scale based on installation requests
- **Database**: Managed by Supabase (auto-scaling)

### 3. **Deployment Flexibility**
- Deploy services independently
- Different resource allocation per service
- Service-specific environment variables

## 🚀 Deployment Strategies

### Strategy 1: Single Instance (Development)
```bash
# Run both services on one server
python enablebot/scripts/start_web.py &
python enablebot/scripts/start_api.py &
```

### Strategy 2: Separate Services (Production)
```bash
# Server 1: Web Interface
python enablebot/scripts/start_web.py

# Server 2: API Backend  
python enablebot/scripts/start_api.py
```

### Strategy 3: Container Deployment
```dockerfile
# Dockerfile.api
FROM python:3.11-slim
COPY enablebot/ /app/enablebot/
COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt
CMD ["python", "/app/enablebot/scripts/start_api.py"]

# Dockerfile.web
FROM python:3.11-slim
COPY enablebot/ /app/enablebot/
COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt
CMD ["python", "/app/enablebot/scripts/start_web.py"]
```

## 📊 Scaling Metrics

### When to Scale API Service:
- **High Slack Event Volume**: > 1000 events/minute
- **Response Time**: > 2 seconds average
- **CPU Usage**: > 80% sustained
- **Memory Usage**: > 80% sustained

### When to Scale Web Service:
- **High Installation Rate**: > 100 installs/hour
- **OAuth Timeouts**: > 5% failure rate
- **Dashboard Load**: > 500 concurrent users

## 🔧 Configuration for Scaling

### Environment Variables per Service:

#### API Service (.env.api)
```bash
# Core API settings
API_PORT=8001
OPENAI_API_KEY=your-key
SLACK_SIGNING_SECRET=your-secret

# Database (shared)
SUPABASE_URL=your-url
SUPABASE_SERVICE_KEY=your-key

# Performance
MAX_WORKERS=4
TIMEOUT=30
```

#### Web Service (.env.web)
```bash
# Core web settings
WEB_PORT=8000
SLACK_CLIENT_ID=your-id
SLACK_CLIENT_SECRET=your-secret
SLACK_REDIRECT_URI=https://your-domain.com/slack/oauth/callback

# Database (shared)
SUPABASE_URL=your-url
SUPABASE_SERVICE_KEY=your-key
```

## 🌐 Load Balancing

### API Service Load Balancing:
```nginx
upstream api_backend {
    server api1.yourdomain.com:8001;
    server api2.yourdomain.com:8001;
    server api3.yourdomain.com:8001;
}

server {
    location /slack/events {
        proxy_pass http://api_backend;
    }
    
    location /api/ {
        proxy_pass http://api_backend;
    }
}
```

### Web Service Load Balancing:
```nginx
upstream web_backend {
    server web1.yourdomain.com:8000;
    server web2.yourdomain.com:8000;
}

server {
    location / {
        proxy_pass http://web_backend;
    }
}
```

## 📈 Performance Optimization

### 1. **Database Optimization**
```python
# Connection pooling
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30
DATABASE_POOL_TIMEOUT=30
```

### 2. **Caching Strategy**
```python
# Redis for Slack client caching
REDIS_URL=redis://your-redis-server:6379
CACHE_TTL=3600  # 1 hour
```

### 3. **Async Processing**
```python
# Background task processing
CELERY_BROKER_URL=redis://your-redis-server:6379
CELERY_RESULT_BACKEND=redis://your-redis-server:6379
```

## 🔍 Monitoring & Observability

### Health Checks:
```bash
# API Service
curl http://api.yourdomain.com:8001/health

# Web Service  
curl http://web.yourdomain.com:8000/health
```

### Metrics to Monitor:
- **Request Rate**: Requests per second
- **Response Time**: Average response time
- **Error Rate**: 4xx/5xx error percentage
- **Database Connections**: Active connections
- **Memory Usage**: RAM consumption
- **CPU Usage**: Processor utilization

### Logging Strategy:
```python
# Structured logging
{
    "timestamp": "2024-01-01T12:00:00Z",
    "service": "api|web",
    "level": "INFO|ERROR|WARNING",
    "tenant_id": "T123456789",
    "user_id": "U123456789", 
    "message": "Processed Slack message",
    "duration_ms": 150,
    "status": "success|error"
}
```

## 🚨 Auto-Scaling Configuration

### Railway Auto-Scaling:
```toml
[deploy]
replicas = { min = 1, max = 10 }
autoscaling = true
cpu_threshold = 80
memory_threshold = 80
```

### Kubernetes Auto-Scaling:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: enablebot-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: enablebot-api
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## 💾 Database Scaling

### Supabase Scaling:
- **Read Replicas**: For read-heavy workloads
- **Connection Pooling**: Built-in pgBouncer
- **Auto-scaling**: Automatic resource scaling

### Query Optimization:
```sql
-- Index optimization for tenant queries
CREATE INDEX CONCURRENTLY idx_tenants_team_id_status 
ON tenants(team_id, status) WHERE status = 'active';

-- Partition large tables by tenant
CREATE TABLE chat_memory_partitioned (
    LIKE chat_memory INCLUDING ALL
) PARTITION BY HASH (tenant_id);
```

## 🔐 Security at Scale

### Rate Limiting:
```python
# Per-tenant rate limiting
RATE_LIMIT_PER_TENANT = "100/minute"
RATE_LIMIT_GLOBAL = "10000/minute"
```

### Token Management:
```python
# Encryption key rotation
KEY_ROTATION_INTERVAL = "90 days"
ENCRYPTION_ALGORITHM = "AES-256-GCM"
```

## 📊 Cost Optimization

### Resource Allocation:
- **API Service**: CPU-intensive (AI processing)
- **Web Service**: Memory-light (OAuth handling)
- **Database**: I/O intensive (encrypted storage)

### Scaling Economics:
```
Small Scale:  1 API + 1 Web = $50/month
Medium Scale: 3 API + 2 Web = $200/month  
Large Scale:  10 API + 5 Web = $800/month
```

## 🎯 Production Checklist

### Pre-Deployment:
- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] SSL certificates installed
- [ ] Monitoring setup
- [ ] Backup strategy implemented

### Post-Deployment:
- [ ] Health checks passing
- [ ] Logs flowing correctly
- [ ] Metrics being collected
- [ ] Auto-scaling configured
- [ ] Alerts configured

### Ongoing Maintenance:
- [ ] Regular security updates
- [ ] Performance monitoring
- [ ] Cost optimization
- [ ] Capacity planning
- [ ] Disaster recovery testing

This architecture ensures EnableBot can scale from handling a few workspaces to thousands of concurrent Slack installations! 🚀