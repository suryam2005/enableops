# 🚀 Supabase Setup Guide for EnableOps

Since your previous Supabase database was corrupted, you need to set up a new Supabase project. Follow these steps:

## Step 1: Create New Supabase Project

1. Go to [Supabase Dashboard](https://supabase.com/dashboard)
2. Click **"New Project"**
3. Choose your organization
4. Fill in project details:
   - **Name**: `EnableOps` (or your preferred name)
   - **Database Password**: Create a strong password (save this!)
   - **Region**: Choose closest to your users
5. Click **"Create new project"**
6. Wait for the project to be created (takes ~2 minutes)

## Step 2: Get API Keys

1. In your new project dashboard, go to **Settings** → **API**
2. Copy the following values:

### Project URL
```
https://your-project-id.supabase.co
```

### API Keys
- **anon public key** (starts with `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`)
- **service_role secret key** (starts with `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`)

## Step 3: Get Database Connection Details

1. Go to **Settings** → **Database**
2. Scroll down to **Connection parameters**
3. Note your:
   - **Host**: `aws-0-us-east-1.pooler.supabase.com` (or your region)
   - **Database**: `postgres`
   - **Port**: `5432` (direct) / `6543` (pooler)
   - **User**: `postgres.your-project-id`
   - **Password**: The password you set when creating the project

## Step 4: Update Your .env File

Replace the placeholder values in your `.env` file:

```env
# Supabase Configuration
SUPABASE_URL=https://your-actual-project-id.supabase.co
SUPABASE_SERVICE_KEY=your-actual-service-role-key
SUPABASE_ANON_KEY=your-actual-anon-key
SUPABASE_DB_PASSWORD=your-actual-database-password

# Database URLs for Prisma
DATABASE_URL=postgresql://postgres.your-actual-project-id:your-actual-password@aws-0-us-east-1.pooler.supabase.com:6543/postgres?pgbouncer=true&connection_limit=1
DIRECT_URL=postgresql://postgres.your-actual-project-id:your-actual-password@aws-0-us-east-1.pooler.supabase.com:5432/postgres
```

## Step 5: Enable Authentication

1. In your Supabase dashboard, go to **Authentication** → **Settings**
2. Make sure **Enable email confirmations** is turned OFF for development
3. Under **Auth Providers**, ensure **Email** is enabled

## Step 6: Test Your Configuration

After updating your `.env` file, run:

```bash
source venv/bin/activate
python setup_enableops.py
```

## 🔐 Security Notes

- **Never commit your service_role key** to version control
- **Use environment variables** in production
- **Rotate keys regularly** in production
- **Enable Row Level Security (RLS)** for production data

## 🆘 Need Help?

If you encounter issues:

1. **Double-check your keys** - they should be long JWT tokens
2. **Verify your project ID** in the URL
3. **Check your database password** is correct
4. **Ensure your project is fully created** (not still initializing)

## Example of Correct Values

Your keys should look like this format:

```env
SUPABASE_URL=https://abcdefghijklmnop.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFiY2RlZmdoaWprbG1ub3AiLCJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNjc4OTEyMzQ1LCJleHAiOjE5OTQ0ODgzNDV9.example-signature-here
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFiY2RlZmdoaWprbG1ub3AiLCJyb2xlIjoiYW5vbiIsImlhdCI6MTY3ODkxMjM0NSwiZXhwIjoxOTk0NDg4MzQ1fQ.example-signature-here
```

Once you have the correct values, your EnableOps application will be ready to run! 🎉