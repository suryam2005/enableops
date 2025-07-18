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

def main():
    """Main startup function"""
    logger.info("� Startingg EnableBot Web Interface...")
    
    try:
        import uvicorn
        from enablebot.api.main import app  # Using API service for now
        
        port = int(os.getenv("PORT", 8000))
        host = os.getenv("HOST", "0.0.0.0")
        
        logger.info(f"🎉 EnableBot starting on http://{host}:{port}")
        
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