#!/usr/bin/env python3
"""
Database Setup Script
Initializes Prisma client and creates database tables
"""

import os
import sys
import asyncio
import subprocess
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def setup_database():
    """Setup database with Prisma"""
    print("🚀 Setting up EnableOps database with Prisma...")
    
    try:
        # Step 1: Generate Prisma client
        print("📦 Generating Prisma client...")
        result = subprocess.run(
            ["python", "-m", "prisma", "generate"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"❌ Failed to generate Prisma client: {result.stderr}")
            return False
        
        print("✅ Prisma client generated successfully")
        
        # Step 2: Push database schema
        print("🗄️ Pushing database schema...")
        result = subprocess.run(
            ["python", "-m", "prisma", "db", "push"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"❌ Failed to push database schema: {result.stderr}")
            return False
        
        print("✅ Database schema pushed successfully")
        
        # Step 3: Test database connection
        print("🔍 Testing database connection...")
        from enablebot.shared.database.prisma_client import init_prisma, close_prisma, check_db_health
        
        if await init_prisma():
            health = await check_db_health()
            if health["status"] == "healthy":
                print("✅ Database connection test successful")
                await close_prisma()
                return True
            else:
                print(f"❌ Database health check failed: {health}")
                await close_prisma()
                return False
        else:
            print("❌ Failed to initialize database connection")
            return False
            
    except Exception as e:
        print(f"❌ Database setup error: {e}")
        return False

async def create_sample_data():
    """Create sample data for testing"""
    print("📝 Creating sample data...")
    
    try:
        from enablebot.shared.database.prisma_client import init_prisma, close_prisma
        from enablebot.shared.database.models import UserProfileService, EncryptionKeyService
        
        await init_prisma()
        
        # Create a sample encryption key
        await EncryptionKeyService.create_encryption_key(
            key_id="default-key-001",
            key_data="sample-encrypted-key-data",
            algorithm="AES-256-GCM"
        )
        
        print("✅ Sample data created successfully")
        await close_prisma()
        
    except Exception as e:
        print(f"⚠️ Sample data creation failed (this is optional): {e}")

def main():
    """Main setup function"""
    print("🔧 EnableOps Database Setup")
    print("=" * 50)
    
    # Check if .env file exists
    env_file = project_root / ".env"
    if not env_file.exists():
        print("❌ .env file not found. Please create it with your database configuration.")
        return False
    
    # Run async setup
    success = asyncio.run(setup_database())
    
    if success:
        print("\n🎉 Database setup completed successfully!")
        print("\nNext steps:")
        print("1. Start your EnableOps application")
        print("2. Test the authentication flow")
        print("3. Install EnableOps to a Slack workspace")
        
        # Optionally create sample data
        create_sample = input("\nWould you like to create sample data? (y/N): ").lower().strip()
        if create_sample == 'y':
            asyncio.run(create_sample_data())
        
        return True
    else:
        print("\n❌ Database setup failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)