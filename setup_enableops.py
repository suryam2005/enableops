#!/usr/bin/env python3
"""
EnableOps Setup Script
Complete setup for EnableOps with Prisma and Supabase
"""

import os
import sys
import subprocess
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_step(step, description):
    print(f"\n🔧 Step {step}: {description}")

def run_command(command, description, cwd=None):
    """Run a command and return success status"""
    print(f"   Running: {' '.join(command)}")
    try:
        result = subprocess.run(
            command,
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            check=True
        )
        print(f"   ✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   ❌ {description} failed:")
        print(f"   Error: {e.stderr}")
        return False

async def main():
    """Main setup process"""
    print_header("EnableOps Setup with Prisma & Supabase")
    
    # Step 1: Install dependencies
    print_step(1, "Installing Python dependencies")
    if not run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], "Dependencies installation"):
        print("❌ Failed to install dependencies. Please check your Python environment.")
        return False
    
    # Step 2: Generate Prisma client
    print_step(2, "Generating Prisma client")
    if not run_command([sys.executable, "-m", "prisma", "generate"], "Prisma client generation"):
        print("❌ Failed to generate Prisma client. Make sure Prisma is installed.")
        return False
    
    # Step 3: Check environment configuration
    print_step(3, "Checking environment configuration")
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found. Please create it with your configuration.")
        return False
    
    # Check required environment variables
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY", 
        "SUPABASE_ANON_KEY",
        "DATABASE_URL",
        "DIRECT_URL"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("   Please update your .env file with the correct values.")
        return False
    
    print("   ✅ Environment configuration looks good")
    
    # Step 4: Push database schema
    print_step(4, "Setting up database schema")
    if not run_command([sys.executable, "-m", "prisma", "db", "push"], "Database schema setup"):
        print("❌ Failed to setup database schema. Please check your database connection.")
        return False
    
    # Step 5: Test database connection
    print_step(5, "Testing database connection")
    try:
        # Import and test database connection
        sys.path.insert(0, str(Path.cwd()))
        from enablebot.shared.database.prisma_client import init_prisma, close_prisma, check_db_health
        
        if await init_prisma():
            health = await check_db_health()
            if health["status"] == "healthy":
                print("   ✅ Database connection test successful")
                await close_prisma()
            else:
                print(f"   ❌ Database health check failed: {health}")
                await close_prisma()
                return False
        else:
            print("   ❌ Failed to initialize database connection")
            return False
    except Exception as e:
        print(f"   ❌ Database connection test failed: {e}")
        return False
    
    # Step 6: Setup complete
    print_header("Setup Complete! 🎉")
    print("\nYour EnableOps application is ready to run!")
    print("\nNext steps:")
    print("1. Configure your Slack app credentials in .env:")
    print("   - SLACK_CLIENT_ID")
    print("   - SLACK_CLIENT_SECRET") 
    print("   - SLACK_REDIRECT_URI")
    print("\n2. Start the application:")
    print("   python -m uvicorn enablebot.web.main:app --reload --host 0.0.0.0 --port 8000")
    print("\n3. Visit http://localhost:8000 to test your application")
    print("\n4. Test the complete flow:")
    print("   - Sign up with email")
    print("   - Install to Slack workspace")
    print("   - Check dashboard")
    
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Setup failed with error: {e}")
        sys.exit(1)