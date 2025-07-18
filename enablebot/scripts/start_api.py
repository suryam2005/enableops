#!/usr/bin/env python3
"""
Start EnableBot API Service
Production startup script for the AI backend
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
    logger.info("🔍 Checking API service environment...")
    
    # Check database configuration
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.error("❌ Database configuration missing!")
        logger.error("Please set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env file")
        return False
    
    logger.info("✅ Database configuration found")
    
    # Check OpenAI configuration
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        logger.warning("⚠️  OpenAI API key missing!")
        logger.warning("AI features will not work without OPENAI_API_KEY")
    else:
        logger.info("✅ OpenAI configuration found")
    
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
    logger.info("🚀 Starting EnableBot API Service...")
    
    # Check environment
    if not asyncio.run(check_environment()):
        logger.error("❌ Environment check failed")
        sys.exit(1)
    
    # Test database connection
    if not asyncio.run(test_database_connection()):
        logger.error("❌ Database connection test failed")
        sys.exit(1)
    
    # Start API service
    logger.info("🤖 Starting AI backend...")
    
    try:
        import uvicorn
        from enablebot.api.main import app
        
        port = int(os.getenv("API_PORT", 8001))
        host = os.getenv("HOST", "0.0.0.0")
        
        logger.info(f"🎉 EnableBot API Service starting on http://{host}:{port}")
        logger.info("📡 Ready to handle Slack events from all workspaces")
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down API service...")
    except Exception as e:
        logger.error(f"❌ Failed to start API service: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()