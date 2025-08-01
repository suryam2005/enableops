#!/usr/bin/env python3
"""
Test environment variables loading
"""

import os
from dotenv import load_dotenv

def test_env_loading():
    print("🔍 Testing environment variable loading...")
    
    # Load .env file
    load_dotenv()
    
    # Check required variables
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY", 
        "SUPABASE_ANON_KEY",
        "DATABASE_URL",
        "DIRECT_URL"
    ]
    
    print("\n📋 Environment Variables Status:")
    print("-" * 50)
    
    all_found = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Show first 20 chars for security
            display_value = value[:20] + "..." if len(value) > 20 else value
            print(f"✅ {var}: {display_value}")
        else:
            print(f"❌ {var}: NOT FOUND")
            all_found = False
    
    print("-" * 50)
    
    if all_found:
        print("✅ All required environment variables found!")
        return True
    else:
        print("❌ Some environment variables are missing.")
        return False

if __name__ == "__main__":
    success = test_env_loading()
    
    if success:
        print("\n🎉 Environment configuration is correct!")
        print("You can now run: python setup_enableops.py")
    else:
        print("\n🔧 Please check your .env file configuration.")