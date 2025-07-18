"""
Simple Database Configuration and Connection Management
Direct asyncpg connection similar to Drizzle ORM approach
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, List
import asyncpg
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Simple database manager with direct asyncpg connection"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._initialized = False
    
    def get_database_url(self) -> str:
        """Construct database URL from environment variables"""
        # Support both Supabase and direct PostgreSQL connections
        supabase_url = os.getenv("SUPABASE_URL")
        database_url = os.getenv("DATABASE_URL")
        
        if database_url:
            return database_url
        elif supabase_url:
            # Supabase connection
            project_id = supabase_url.split("//")[1].split(".")[0]
            
            # Get database credentials from environment
            db_password = os.getenv("SUPABASE_DB_PASSWORD") or os.getenv("SUPABASE_SERVICE_KEY")
            db_user = os.getenv("SUPABASE_DB_USER", "postgres")
            db_host = os.getenv("SUPABASE_DB_HOST", f"db.{project_id}.supabase.co")
            db_port = os.getenv("SUPABASE_DB_PORT", "5432")
            db_name = os.getenv("SUPABASE_DB_NAME", "postgres")
            
            if not db_password:
                raise ValueError("SUPABASE_DB_PASSWORD or SUPABASE_SERVICE_KEY is required")
            
            return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        else:
            # Fallback to local PostgreSQL
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "postgres")
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "5432")
            db_name = os.getenv("DB_NAME", "enablebot")
            
            return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    async def initialize(self) -> bool:
        """Initialize database connection pool"""
        if self._initialized:
            return True
        
        try:
            database_url = self.get_database_url()
            logger.info(f"Initializing database connection pool...")
            
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=10,
                command_timeout=60,
                server_settings={
                    'application_name': 'EnableBot',
                }
            )
            
            # Test connection
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")
            
            self._initialized = True
            logger.info("✅ Database connection pool initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            return False
    
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection from pool"""
        if not self._initialized:
            await self.initialize()
        
        if not self.pool:
            raise RuntimeError("Database not initialized")
        
        async with self.pool.acquire() as conn:
            yield conn
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query and return status"""
        async with self.get_connection() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """Fetch multiple rows as dictionaries"""
        async with self.get_connection() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
    
    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Fetch single row as dictionary"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None
    
    async def fetchval(self, query: str, *args):
        """Fetch single value"""
        async with self.get_connection() as conn:
            return await conn.fetchval(query, *args)
    
    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

# Global database instance
db = DatabaseManager()

# Convenience functions
async def init_database() -> bool:
    """Initialize database connection"""
    return await db.initialize()

async def close_database():
    """Close database connections"""
    await db.close()

async def execute_query(query: str, *args) -> str:
    """Execute a query"""
    return await db.execute(query, *args)

async def fetch_all(query: str, *args) -> List[Dict[str, Any]]:
    """Fetch all rows"""
    return await db.fetch(query, *args)

async def fetch_one(query: str, *args) -> Optional[Dict[str, Any]]:
    """Fetch one row"""
    return await db.fetchrow(query, *args)

async def fetch_value(query: str, *args):
    """Fetch single value"""
    return await db.fetchval(query, *args)