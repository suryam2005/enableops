#!/usr/bin/env python3
"""
Database Migration Script
Adds missing columns to existing database
"""

import os
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def migrate_database():
    """Add missing columns to the database"""
    print("🔧 Starting database migration...")
    
    # Get database URL
    database_url = os.getenv("DIRECT_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ No database URL found")
        return False
    
    try:
        # Connect to database
        conn = await asyncpg.connect(database_url)
        print("✅ Connected to database")
        
        # Check if tenants table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'tenants'
            );
        """)
        
        if not table_exists:
            print("⚠️ Tenants table doesn't exist, running full schema creation...")
            # Run Prisma db push
            import subprocess
            result = subprocess.run(
                ["python", "-m", "prisma", "db", "push", "--accept-data-loss"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("✅ Database schema created successfully")
            else:
                print(f"❌ Schema creation failed: {result.stderr}")
                return False
        else:
            print("✅ Tenants table exists, checking for missing columns...")
            
            # Check if supabase_user_id column exists
            supabase_col_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'tenants' AND column_name = 'supabase_user_id'
                );
            """)
            
            if not supabase_col_exists:
                print("➕ Adding supabase_user_id column...")
                await conn.execute("""
                    ALTER TABLE tenants 
                    ADD COLUMN supabase_user_id TEXT;
                """)
                print("✅ Added supabase_user_id column")
            else:
                print("✅ supabase_user_id column already exists")
            
            # Check if installer_email column exists
            email_col_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'tenants' AND column_name = 'installer_email'
                );
            """)
            
            if not email_col_exists:
                print("➕ Adding installer_email column...")
                await conn.execute("""
                    ALTER TABLE tenants 
                    ADD COLUMN installer_email TEXT;
                """)
                print("✅ Added installer_email column")
            else:
                print("✅ installer_email column already exists")
            
            # Check settings column type
            settings_type = await conn.fetchval("""
                SELECT data_type FROM information_schema.columns 
                WHERE table_name = 'tenants' AND column_name = 'settings';
            """)
            
            if settings_type != 'jsonb':
                print("🔧 Updating settings column type...")
                await conn.execute("""
                    ALTER TABLE tenants 
                    ALTER COLUMN settings TYPE JSONB USING settings::JSONB;
                """)
                print("✅ Updated settings column type")
            else:
                print("✅ Settings column type is correct")
        
        await conn.close()
        print("✅ Database migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(migrate_database())
    exit(0 if success else 1)