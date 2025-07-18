# 🚀 Deploy EnableBot via GitHub + Railway

This guide walks you through deploying EnableBot to Railway using GitHub integration.

## 📋 Pre-Deployment Checklist

### ✅ 1. GitHub Repository Setup
- [ ] Push all code to GitHub repository
- [ ] Ensure `.gitignore` is properly configured
- [ ] Verify all necessary files are committed

### ✅ 2. Slack App Configuration
Before deploying, you need a Slack app:

1. **Create Slack App**:
   - Go to [api.slack.com/apps](https://api.slack.com/apps)
   - Click "Create New App" → "From scratch"
   - Name: "EnableBot" 
   - Choose your development workspace

2. **Configure OAuth & Permissions**:
   - Go to "OAuth & Permissions"
   - Add these Bot Token Scopes:
     ```
     app_mentions:read
     channels:history
     chat:write
     im:history
     im:read
     im:write
     users:read
     users:read.email
     ```
   - Note your **Client ID** and **Client Secret**

3. **Configure Event Subscriptions** (Optional for AI features):
   - Go to "Event Subscriptions"
   - Enable Events: ON
   - Request URL: `https://your-app.railway.app/slack/events` (update after deployment)
   - Subscribe to Bot Events:
     ```
     app_mention
     message.im
     ```

## 🚀 Railway Deployment Steps

### Step 1: Connect GitHub to Railway

1. **Login to Railway**:
   - Go to [railway.app](https://railway.app)
   - Sign up/login with GitHub

2. **Create New Project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your EnableBot repository
   - Railway will automatically detect Python and use `railway.toml`

### Step 2: Configure Environment Variables

In your Railway project dashboard, go to "Variables" and add:

#### Required Variables:
```bash
# Database (Already configured)
SUPABASE_URL=https://rwizlvyrzmlsdkwrqiuo.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ3aXpsdnlyem1sc2Rrd3JxaXVvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MDY1MTY3OSwiZXhwIjoyMDY2MjI3Njc5fQ.gH9ydNlVammRA82rAaYKdfuEk-nQtrozW7nDoe_0X2Y
SUPABASE_DB_PASSWORD=botenable123

# Slack OAuth (Get from your Slack app)
SLACK_CLIENT_ID=your-slack-client-id-here
SLACK_CLIENT_SECRET=your-slack-client-secret-here
SLACK_REDIRECT_URI=https://your-app.railway.app/slack/oauth/callback

# Optional: AI Features
OPENAI_API_KEY=your-openai-api-key-here

# Optional: Event Handling
SLACK_SIGNING_SECRET=your-slack-signing-secret-here
```

#### How to Add Variables:
1. In Railway dashboard, click your project
2. Go to "Variables" tab
3. Click "New Variable"
4. Add each variable name and value
5. Click "Add" for each one

### Step 3: Deploy

1. **Automatic Deployment**:
   - Railway automatically deploys when you connect the repo
   - Monitor the build logs in Railway dashboard
   - Wait for deployment to complete (usually 2-3 minutes)

2. **Get Your App URL**:
   - In Railway dashboard, you'll see your app URL
   - Format: `https://your-app-name.railway.app`
   - Click to test the deployment

### Step 4: Update Slack App Configuration

1. **Update OAuth Redirect URL**:
   - Go back to your Slack app settings
   - Navigate to "OAuth & Permissions"
   - Update "Redirect URLs" to: `https://your-app.railway.app/slack/oauth/callback`
   - Click "Save URLs"

2. **Update Event Subscriptions** (if using AI features):
   - Go to "Event Subscriptions"
   - Update Request URL to: `https://your-app.railway.app/slack/events`
   - Click "Save Changes"

3. **Update Railway Environment Variable**:
   - In Railway dashboard, update `SLACK_REDIRECT_URI` to match your actual domain
   - Example: `SLACK_REDIRECT_URI=https://enablebot-production-abc123.railway.app/slack/oauth/callback`

## 🧪 Testing Your Deployment

### Step 1: Basic Health Check
1. Visit your Railway app URL
2. You should see the EnableBot landing page
3. Check health endpoint: `https://your-app.railway.app/health`

### Step 2: Test Slack Installation
1. Click "Add to Slack" button on your landing page
2. Complete OAuth flow in your Slack workspace
3. You should see the installation dashboard
4. Check Supabase database for new records

### Step 3: Verify Database Records
In Supabase dashboard, check these tables:

1. **tenants**: Should have your workspace info
2. **installation_events**: Should log the installation
3. **token_audit_log**: Should log token encryption

## 📊 Monitoring Your Deployment

### Railway Dashboard
- **Logs**: View application logs and errors
- **Metrics**: Monitor CPU, memory, and network usage
- **Deployments**: Track deployment history
- **Variables**: Manage environment variables

### Supabase Dashboard
- **Database**: Monitor queries and performance
- **Auth**: Track user sessions (if applicable)
- **Storage**: Monitor file uploads (if applicable)

## 🔧 Troubleshooting

### Common Issues:

1. **Build Fails**:
   ```bash
   # Check Railway logs for Python/dependency errors
   # Ensure requirements.txt is correct
   # Verify Python version in runtime.txt
   ```

2. **App Won't Start**:
   ```bash
   # Check if all environment variables are set
   # Verify Procfile points to correct startup script
   # Check Railway logs for startup errors
   ```

3. **Slack OAuth Fails**:
   ```bash
   # Verify SLACK_CLIENT_ID and SLACK_CLIENT_SECRET
   # Ensure redirect URI matches exactly
   # Check Slack app configuration
   ```

4. **Database Connection Issues**:
   ```bash
   # Verify Supabase credentials
   # Check if Supabase project is active
   # Test connection from Railway logs
   ```

### Debug Commands:
- View Railway logs in dashboard
- Check environment variables in Railway
- Test endpoints manually
- Monitor Supabase logs

## 🔄 Updating Your Deployment

### For Code Changes:
1. Make changes locally
2. Commit and push to GitHub:
   ```bash
   git add .
   git commit -m "Update: description of changes"
   git push origin main
   ```
3. Railway automatically redeploys

### For Environment Variables:
1. Update in Railway dashboard
2. Restart deployment if needed

## 🎯 Success Checklist

After deployment, verify:
- [ ] **App loads**: Landing page displays correctly
- [ ] **Health check**: `/health` returns 200 OK
- [ ] **Slack install**: OAuth flow completes successfully
- [ ] **Dashboard shows**: Installation details display
- [ ] **Database records**: Check Supabase for new entries
- [ ] **Encryption works**: Bot tokens are encrypted
- [ ] **Logs clean**: No errors in Railway logs

## 🔐 Security Verification

Ensure these security features are active:
- [ ] **HTTPS**: All traffic encrypted (Railway provides SSL)
- [ ] **Environment Variables**: No secrets in code
- [ ] **Token Encryption**: Slack tokens encrypted in database
- [ ] **Audit Logging**: All operations logged
- [ ] **Tenant Isolation**: Data separated by workspace

## 📈 Next Steps

After successful deployment:
1. **Test with real users**: Invite team members to install
2. **Monitor performance**: Watch Railway metrics
3. **Scale if needed**: Railway auto-scales based on usage
4. **Custom domain**: Consider adding custom domain
5. **Backup strategy**: Ensure Supabase backups are configured

## 🆘 Support Resources

- **Railway**: [docs.railway.app](https://docs.railway.app) | [Discord](https://discord.gg/railway)
- **Slack API**: [api.slack.com/docs](https://api.slack.com/docs)
- **Supabase**: [supabase.com/docs](https://supabase.com/docs)

---

## 🚀 Quick Deploy Commands

```bash
# 1. Commit and push to GitHub
git add .
git commit -m "Deploy EnableBot to Railway"
git push origin main

# 2. Connect to Railway (via web dashboard)
# 3. Set environment variables (via Railway dashboard)
# 4. Update Slack app settings
# 5. Test deployment
```

**Your EnableBot is now ready for production! 🎉**