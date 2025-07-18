# 🚀 Railway Deployment Checklist for EnableBot

This checklist will guide you through deploying EnableBot to Railway for real-time Slack installation testing.

## 📋 Pre-Deployment Checklist

### ✅ 1. Railway Account Setup
- [ ] Create Railway account at [railway.app](https://railway.app)
- [ ] Install Railway CLI: `npm install -g @railway/cli` or `curl -fsSL https://railway.app/install.sh | sh`
- [ ] Login to Railway: `railway login`

### ✅ 2. Project Preparation
- [ ] Ensure all files are committed to git
- [ ] Test application locally: `python start_web.py`
- [ ] Verify database connection works
- [ ] Check all environment variables are documented

### ✅ 3. Slack App Configuration
- [ ] Create Slack app at [api.slack.com/apps](https://api.slack.com/apps)
- [ ] Note down Client ID and Client Secret
- [ ] Configure OAuth redirect URL (will update after Railway deployment)
- [ ] Set required bot scopes:
  - `app_mentions:read`
  - `channels:history`
  - `chat:write`
  - `im:history`
  - `im:read`
  - `im:write`
  - `users:read`
  - `users:read.email`

## 🚀 Railway Deployment Steps

### Step 1: Create Railway Project

```bash
# Initialize Railway project
railway login
railway init

# Or create from GitHub (recommended)
# Connect your GitHub repo to Railway dashboard
```

### Step 2: Configure Environment Variables

In Railway dashboard, add these environment variables:

#### Database Configuration (Already have these)
```
SUPABASE_URL=https://rwizlvyrzmlsdkwrqiuo.supabase.co
SUPABASE_SERVICE_KEY=your-service-key
SUPABASE_DB_PASSWORD=botenable123
```

#### Slack OAuth Configuration (Need to add)
```
SLACK_CLIENT_ID=your-slack-client-id
SLACK_CLIENT_SECRET=your-slack-client-secret
SLACK_REDIRECT_URI=https://your-railway-domain.railway.app/slack/oauth/callback
```

#### Application Configuration
```
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

### Step 3: Create Railway Configuration Files

Create `railway.toml`:
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python start_web.py"
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3

[environments.production]
variables = { }
```

Create `Procfile`:
```
web: python start_web.py
```

Create `runtime.txt`:
```
python-3.13
```

### Step 4: Deploy to Railway

```bash
# Deploy current directory
railway up

# Or if using GitHub integration, push to main branch
git add .
git commit -m "Deploy to Railway"
git push origin main
```

## 🔧 Post-Deployment Configuration

### Step 1: Get Railway Domain
- [ ] Note your Railway app URL: `https://your-app-name.railway.app`
- [ ] Test health endpoint: `https://your-app-name.railway.app/health`

### Step 2: Update Slack App Configuration
- [ ] Go to your Slack app settings
- [ ] Update OAuth Redirect URL to: `https://your-app-name.railway.app/slack/oauth/callback`
- [ ] Update environment variable `SLACK_REDIRECT_URI` in Railway

### Step 3: Update Environment Variables in Railway
```
SLACK_REDIRECT_URI=https://your-app-name.railway.app/slack/oauth/callback
```

### Step 4: Verify Deployment
- [ ] Visit your Railway app URL
- [ ] Check health endpoint returns 200
- [ ] Test Slack installation flow
- [ ] Verify database records are created

## 🧪 Testing Checklist

### Functional Testing
- [ ] **Home page loads**: Visit `https://your-app.railway.app`
- [ ] **Slack install button works**: Click "Add to Slack"
- [ ] **OAuth flow completes**: Authorize in Slack workspace
- [ ] **Dashboard displays**: See installation details
- [ ] **Database records created**: Check Supabase tables

### Database Verification
Check these tables in Supabase:

1. **Tenants Table**:
```sql
SELECT team_id, team_name, installer_name, status, created_at 
FROM tenants 
ORDER BY created_at DESC 
LIMIT 5;
```

2. **Installation Events**:
```sql
SELECT team_id, event_type, installer_name, created_at 
FROM installation_events 
ORDER BY created_at DESC 
LIMIT 5;
```

3. **Audit Logs**:
```sql
SELECT tenant_id, operation, success, created_at 
FROM token_audit_log 
ORDER BY created_at DESC 
LIMIT 5;
```

### Security Testing
- [ ] **Token encryption**: Verify bot tokens are encrypted in database
- [ ] **Audit logging**: Check all operations are logged
- [ ] **HTTPS enabled**: Ensure all traffic is encrypted
- [ ] **Environment variables secure**: No secrets in code

## 📁 Required Files for Deployment

Make sure these files exist in your project:

### Core Application Files
- [ ] `web_app.py` - Main FastAPI application
- [ ] `slack_auth.py` - Slack OAuth handling
- [ ] `start_web.py` - Application startup script
- [ ] `requirements.txt` - Python dependencies

### Database & Encryption
- [ ] `database/config.py` - Database configuration
- [ ] `database/models.py` - Pydantic models
- [ ] `database/init_db.py` - Database initialization
- [ ] `encryption.py` - Token encryption

### Templates
- [ ] `templates/index.html` - Landing page
- [ ] `templates/dashboard.html` - Installation dashboard

### Configuration
- [ ] `railway.toml` - Railway configuration
- [ ] `Procfile` - Process definition
- [ ] `runtime.txt` - Python version
- [ ] `.env` - Environment variables (for local development)

## 🚨 Troubleshooting

### Common Deployment Issues

1. **Build Failures**:
   ```bash
   # Check Railway logs
   railway logs
   
   # Redeploy
   railway up --detach
   ```

2. **Environment Variable Issues**:
   - Verify all required env vars are set in Railway dashboard
   - Check variable names match exactly (case-sensitive)
   - Restart deployment after changing env vars

3. **Database Connection Issues**:
   - Test Supabase connection from Railway logs
   - Verify Supabase project is active
   - Check IP restrictions in Supabase

4. **Slack OAuth Issues**:
   - Ensure redirect URI matches exactly
   - Check Slack app is not restricted to specific workspaces
   - Verify client ID and secret are correct

### Debug Commands

```bash
# View Railway logs
railway logs

# Connect to Railway shell
railway shell

# Check environment variables
railway variables

# Restart service
railway up --detach
```

## 🔒 Security Considerations

### Production Security
- [ ] **Environment Variables**: All secrets in Railway env vars, not in code
- [ ] **HTTPS Only**: Railway provides HTTPS by default
- [ ] **Database Security**: Supabase RLS policies enabled
- [ ] **Token Encryption**: All Slack tokens encrypted with AES-256-GCM
- [ ] **Audit Logging**: All operations logged for compliance

### Monitoring
- [ ] **Health Checks**: Railway health check configured
- [ ] **Error Logging**: Application logs available in Railway
- [ ] **Database Monitoring**: Supabase dashboard for DB metrics
- [ ] **Uptime Monitoring**: Consider external monitoring service

## 📊 Success Metrics

After deployment, you should see:

### Application Metrics
- ✅ **Response Time**: < 2 seconds for page loads
- ✅ **Uptime**: > 99% availability
- ✅ **Error Rate**: < 1% of requests

### Installation Flow Metrics
- ✅ **OAuth Success Rate**: > 95% successful installations
- ✅ **Database Storage**: 100% of installations stored
- ✅ **Token Encryption**: 100% of tokens encrypted
- ✅ **Audit Coverage**: 100% of operations logged

## 🎯 Next Steps After Deployment

1. **Test with Real Users**: Invite team members to test installation
2. **Monitor Performance**: Watch Railway metrics and logs
3. **Scale if Needed**: Railway auto-scales, but monitor usage
4. **Backup Strategy**: Ensure Supabase backups are configured
5. **Custom Domain**: Consider adding custom domain for production

## 📞 Support Resources

- **Railway Docs**: [docs.railway.app](https://docs.railway.app)
- **Railway Discord**: [discord.gg/railway](https://discord.gg/railway)
- **Slack API Docs**: [api.slack.com](https://api.slack.com)
- **Supabase Docs**: [supabase.com/docs](https://supabase.com/docs)

---

## 🚀 Quick Deploy Commands

```bash
# One-time setup
railway login
railway init

# Deploy
railway up

# Check status
railway status
railway logs

# Update environment variables
railway variables set SLACK_CLIENT_ID=your-client-id
railway variables set SLACK_CLIENT_SECRET=your-client-secret
railway variables set SLACK_REDIRECT_URI=https://your-app.railway.app/slack/oauth/callback
```

**Ready to deploy? Follow this checklist step by step and you'll have EnableBot running on Railway with real-time Slack installation testing! 🎉**