# 🤖 EnableBot - AI-Powered Slack Assistant

EnableBot is a production-ready, multi-tenant AI assistant for Slack workspaces with enterprise-grade security and scalability.

## 🚀 Quick Deploy to Railway

### Prerequisites
- GitHub account
- Railway account ([railway.app](https://railway.app))
- Slack app credentials
- Supabase database (already configured)

### 1. Deploy to Railway via GitHub

1. **Push to GitHub**:
   ```bash
   git add .
   git commit -m "Deploy EnableBot to Railway"
   git push origin main
   ```

2. **Connect to Railway**:
   - Go to [railway.app](https://railway.app)
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your EnableBot repository
   - Railway will automatically detect the configuration

3. **Set Environment Variables** in Railway dashboard:
   ```
   SUPABASE_URL=https://rwizlvyrzmlsdkwrqiuo.supabase.co
   SUPABASE_SERVICE_KEY=your-service-key
   SUPABASE_DB_PASSWORD=botenable123
   SLACK_CLIENT_ID=your-slack-client-id
   SLACK_CLIENT_SECRET=your-slack-client-secret
   SLACK_REDIRECT_URI=https://your-app.railway.app/slack/oauth/callback
   OPENAI_API_KEY=your-openai-api-key
   ```

4. **Update Slack App Settings**:
   - Go to [api.slack.com/apps](https://api.slack.com/apps)
   - Update OAuth Redirect URL to match your Railway domain

### 2. Test Your Deployment

1. Visit your Railway app URL
2. Click "Add to Slack" 
3. Complete OAuth flow
4. Verify installation dashboard shows your workspace

## 🏗️ Architecture

EnableBot uses a microservices architecture with:

- **Web Service**: Handles Slack OAuth and installation dashboard
- **API Service**: Processes Slack events and AI responses  
- **Shared Components**: Database, encryption, and utilities
- **Multi-tenant Design**: Isolated workspaces with encrypted tokens

## 🔐 Security Features

- **AES-256-GCM Encryption**: All Slack tokens encrypted at rest
- **Tenant Isolation**: Complete data separation between workspaces
- **Audit Logging**: Comprehensive operation tracking
- **HTTPS Only**: End-to-end encryption
- **Environment Variables**: No secrets in code

## 📁 Project Structure

```
enablebot/
├── api/                    # AI backend service
├── web/                    # OAuth and dashboard
├── shared/                 # Common components
│   ├── database/          # Database layer
│   ├── encryption/        # Security layer
│   └── models/           # Data models
├── config/                # Configuration
├── scripts/               # Startup scripts
├── tests/                 # Test suite
└── docs/                  # Documentation
```

## 🧪 Local Development

1. **Setup Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Run Locally**:
   ```bash
   python enablebot/scripts/start_web.py
   ```

## 📊 Monitoring

- **Railway Dashboard**: Application metrics and logs
- **Supabase Dashboard**: Database performance and analytics
- **Health Endpoint**: `/health` for uptime monitoring

## 🆘 Support

- **Railway**: [docs.railway.app](https://docs.railway.app)
- **Slack API**: [api.slack.com/docs](https://api.slack.com/docs)
- **Supabase**: [supabase.com/docs](https://supabase.com/docs)

## 📄 License

MIT License - see LICENSE file for details.

---

**Ready to deploy? Just push to GitHub and connect to Railway! 🚀**