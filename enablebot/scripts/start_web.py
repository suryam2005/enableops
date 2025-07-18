#!/usr/bin/env python3
"""
Start EnableBot Web Interface
Production startup script for the web interface
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def check_environment():
    """Check if environment is properly configured"""
    logger.info("🔍 Checking web interface environment...")
    
    # Check database configuration
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.error("❌ Database configuration missing!")
        logger.error("Please set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env file")
        return False
    
    logger.info("✅ Database configuration found")
    
    # Check Slack OAuth configuration
    slack_client_id = os.getenv("SLACK_CLIENT_ID")
    slack_client_secret = os.getenv("SLACK_CLIENT_SECRET")
    
    if not slack_client_id or not slack_client_secret:
        logger.warning("⚠️  Slack OAuth configuration missing!")
        logger.warning("Please set SLACK_CLIENT_ID and SLACK_CLIENT_SECRET in .env file")
        logger.warning("Installation flow will not work without these credentials")
    else:
        logger.info("✅ Slack OAuth configuration found")
    
    return True

async def test_database_connection():
    """Test database connection"""
    logger.info("🔍 Testing database connection...")
    
    try:
        from enablebot.shared.database.config import init_database, close_database
        
        if await init_database():
            logger.info("✅ Database connection successful")
            await close_database()
            return True
        else:
            logger.error("❌ Database connection failed")
            return False
    except Exception as e:
        logger.error(f"❌ Database connection error: {e}")
        return False

def main():
    """Main startup function"""
    logger.info("🚀 Starting EnableBot Web Interface...")
    
    # Check environment
    if not asyncio.run(check_environment()):
        logger.error("❌ Environment check failed")
        sys.exit(1)
    
    # Test database connection
    if not asyncio.run(test_database_connection()):
        logger.error("❌ Database connection test failed")
        sys.exit(1)
    
    # Start web interface
    logger.info("🌐 Starting web server...")
    
    try:
        import uvicorn
        from enablebot.web.main import app
        
        port = int(os.getenv("WEB_PORT", 8000))
        host = os.getenv("HOST", "0.0.0.0")
        
        logger.info(f"🎉 EnableBot Web Interface starting on http://{host}:{port}")
        logger.info("📱 Visit the URL to test the Slack installation flow")
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down web server...")
    except Exception as e:
        logger.error(f"❌ Failed to start web server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()