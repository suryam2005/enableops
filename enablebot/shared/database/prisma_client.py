"""
Prisma Database Client Configuration
Handles database connections and operations using Prisma ORM
"""

import os
import logging
from typing import Optional
from prisma import Prisma
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Global Prisma client instance
prisma_client: Optional[Prisma] = None

async def init_prisma() -> bool:
    """Initialize Prisma client connection"""
    global prisma_client
    
    try:
        if prisma_client is None:
            prisma_client = Prisma()
        
        # Connect to database
        await prisma_client.connect()
        
        logger.info("✅ Prisma database connection initialized")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize Prisma: {e}")
        return False

async def close_prisma():
    """Close Prisma client connection"""
    global prisma_client
    
    try:
        if prisma_client and prisma_client.is_connected():
            await prisma_client.disconnect()
            logger.info("✅ Prisma database connection closed")
    except Exception as e:
        logger.error(f"❌ Error closing Prisma connection: {e}")

def get_prisma() -> Prisma:
    """Get the global Prisma client instance"""
    if prisma_client is None:
        raise RuntimeError("Prisma client not initialized. Call init_prisma() first.")
    return prisma_client

@asynccontextmanager
async def get_db():
    """Context manager for database operations"""
    try:
        db = get_prisma()
        yield db
    except Exception as e:
        logger.error(f"Database operation error: {e}")
        raise

# Database health check
async def check_db_health() -> dict:
    """Check database connection health"""
    try:
        db = get_prisma()
        
        # Simple query to test connection
        result = await db.query_raw("SELECT 1 as health_check")
        
        return {
            "status": "healthy",
            "connected": db.is_connected(),
            "query_result": result
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "connected": False,
            "error": str(e)
        }