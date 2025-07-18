# EnableBot Slack Installation Testing Guide

This guide will help you test the real-time Slack installation flow with Supabase database storage.

## 🚀 Quick Start

### 1. Prerequisites
- ✅ Supabase database configured (already done)
- ✅ Python virtual environment set up
- ✅ Dependencies installed
- 🔄 Slack app credentials needed (next step)

### 2. Slack App Setup

You need to create a Slack app and get the OAuth credentials:

1. **Go to [Slack API](https://api.slack.com/apps)**
2. **Click "Create New App" → "From scratch"**
3. **Enter app details:**
   - App Name: `EnableBot`
   - Workspace: Select your test workspace
4. **Configure OAuth & Permissions:**
   - Go to "OAuth & Permissions" in sidebar
   - Add Redirect URL: `http://localhost:8000/slack/oauth/callback`
   - Add Bot Token Scopes:
     - `app_mentions:read`
     - `channels:history`
     - `chat:write`
     - `im:history`
     - `im:read`
     - `im:write`
     - `users:read`
     - `users:read.email`
5. **Get credentials:**
   - Client ID: Found in "Basic Information" → "App Credentials"
   - Client Secret: Found in "Basic Information" → "App Credentials"

### 3. Update Environment Variables

Add your Slack credentials to `.env` file:

```bash
# Slack OAuth Settings
SLACK_CLIENT_ID=your-actual-client-id-here
SLACK_CLIENT_SECRET=your-actual-client-secret-here
SLACK_REDIRECT_URI=http://localhost:8000/slack/oauth/callback
```

### 4. Start the Web Application

```bash
# Activate virtual environment
source venv/bin/activate

# Start the web server
python start_web.py
```

You should see:
```
🚀 Starting EnableBot Web Application...
✅ Database configuration found
✅ Slack OAuth configuration found
✅ Database connection successful
🎉 EnableBot Web Interface starting on http://0.0.0.0:8000
📱 Visit http://localhost:8000 to test the Slack installation flow
```

## 🧪 Testing the Installation Flow

### Step 1: Visit the Home Page
1. Open browser to `http://localhost:8000`
2. You should see the EnableBot landing page
3. Click "Add to Slack" button

### Step 2: Slack OAuth Flow
1. You'll be redirected to Slack's authorization page
2. Select your workspace and click "Allow"
3. You'll be redirected back to the dashboard

### Step 3: Verify Database Storage
The installation should automatically:
- ✅ Encrypt and store the Slack bot token
- ✅ Create tenant record in `tenants` table
- ✅ Log installation event in `installation_events` table
- ✅ Create audit log entries in `token_audit_log` table

### Step 4: Check Dashboard
After successful installation, you should see:
- Team information
- Bot details
- Installation date
- Granted permissions
- Quick action buttons

## 🔍 Verification Steps

### Check Database Records

You can verify the data was stored correctly by checking your Supabase dashboard:

1. **Tenants Table:**
   ```sql
   SELECT team_id, team_name, installer_name, plan, status, created_at 
   FROM tenants 
   ORDER BY created_at DESC;
   ```

2. **Installation Events:**
   ```sql
   SELECT team_id, event_type, installer_name, scopes, created_at 
   FROM installation_events 
   ORDER BY created_at DESC;
   ```

3. **Audit Logs:**
   ```sql
   SELECT tenant_id, operation, success, created_at 
   FROM token_audit_log 
   ORDER BY created_at DESC;
   ```

### Test API Endpoints

1. **Health Check:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Installation Info:**
   ```bash
   curl http://localhost:8000/api/installations/YOUR_TEAM_ID
   ```

## 🛠️ Troubleshooting

### Common Issues

1. **"Slack OAuth not configured" error:**
   - Make sure `SLACK_CLIENT_ID` and `SLACK_CLIENT_SECRET` are set in `.env`
   - Restart the web server after updating `.env`

2. **"Database connection failed" error:**
   - Check your Supabase credentials in `.env`
   - Verify your Supabase project is active

3. **"Invalid redirect URI" error:**
   - Make sure the redirect URI in your Slack app matches exactly: `http://localhost:8000/slack/oauth/callback`

4. **"Installation not found" error:**
   - Check if the installation was actually stored in the database
   - Look at the server logs for any errors during OAuth callback

### Debug Mode

To see detailed logs, you can run:

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python start_web.py
```

## 📊 What Gets Stored

When a user installs the app, the following data is securely stored:

### Tenants Table
- `team_id`: Slack workspace ID
- `team_name`: Workspace name
- `encrypted_bot_token`: AES-256-GCM encrypted bot token
- `encryption_key_id`: Reference to encryption key
- `bot_user_id`: Bot's user ID in Slack
- `installer_name`: Name of person who installed
- `plan`: Subscription plan (default: "free")
- `status`: Installation status (default: "active")

### Installation Events Table
- `event_type`: "app_installed"
- `installer_id`: Slack user ID of installer
- `scopes`: Array of granted permissions
- `event_data`: Full OAuth response (for debugging)

### Token Audit Log
- `operation`: "token_stored"
- `success`: true/false
- `ip_address`: Installer's IP
- `user_agent`: Browser information
- `metadata`: Additional context

## 🔐 Security Features

- **Token Encryption**: Bot tokens are encrypted with AES-256-GCM
- **Tenant Isolation**: Each workspace's data is isolated
- **Audit Logging**: All token operations are logged
- **Key Rotation**: Encryption keys can be rotated
- **IP Tracking**: Installation source is tracked

## 🎯 Next Steps

After successful testing:
1. **Deploy to production** with proper domain
2. **Update Slack app** redirect URI to production URL
3. **Configure monitoring** and alerting
4. **Set up key rotation** schedule
5. **Implement user management** features

## 📞 Support

If you encounter issues:
1. Check the server logs for detailed error messages
2. Verify all environment variables are set correctly
3. Test database connection independently
4. Check Slack app configuration matches exactly

The system is designed to be robust and provide detailed logging for troubleshooting!