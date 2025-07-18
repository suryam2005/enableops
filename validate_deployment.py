#!/usr/bin/env python3
"""
Deployment Validation Script
Checks if the application is ready for Railway deployment
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_files():
    """Check if all required files exist"""
    logger.info("📁 Checking required files...")
    
    required_files = [
        'web_app.py',
        'slack_auth.py', 
        'start_web.py',
        'requirements.txt',
        'database/config.py',
        'database/models.py',
        'database/init_db.py',
        'encryption.py',
        'templates/index.html',
        'templates/dashboard.html',
        'railway.toml',
        'Procfile',
        'runtime.txt'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
        else:
            logger.info(f"  ✅ {file_path}")
    
    if missing_files:
        logger.error(f"❌ Missing files: {missing_files}")
        return False
    
    logger.info("✅ All required files present")
    return True

def check_environment():
    """Check environment variables"""
    logger.info("🔧 Checking environment variables...")
    
    # Required for production
    required_vars = {
        'SUPABASE_URL': 'Database connection',
        'SUPABASE_SERVICE_KEY': 'Database authentication', 
        'SUPABASE_DB_PASSWORD': 'Database password'
    }
    
    # Optional but recommended for Slack OAuth
    optional_vars = {
        'SLACK_CLIENT_ID': 'Slack OAuth (required for installation flow)',
        'SLACK_CLIENT_SECRET': 'Slack OAuth (required for installation flow)',
        'SLACK_REDIRECT_URI': 'Slack OAuth callback URL'
    }
    
    missing_required = []
    missing_optional = []
    
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing_required.append(f"{var} ({description})")
        else:
            logger.info(f"  ✅ {var}")
    
    for var, description in optional_vars.items():
        if not os.getenv(var):
            missing_optional.append(f"{var} ({description})")
        else:
            logger.info(f"  ✅ {var}")
    
    if missing_required:
        logger.error(f"❌ Missing required variables: {missing_required}")
        return False
    
    if missing_optional:
        logger.warning(f"⚠️  Missing optional variables: {missing_optional}")
        logger.warning("   Slack installation flow will not work without these")
    
    logger.info("✅ Environment variables configured")
    return True

async def check_database():
    """Test database connection"""
    logger.info("🗄️  Testing database connection...")
    
    try:
        from database.config import init_database, close_database
        
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

def check_dependencies():
    """Check if all dependencies are in requirements.txt"""
    logger.info("📦 Checking dependencies...")
    
    try:
        with open('requirements.txt', 'r') as f:
            requirements = f.read()
        
        required_packages = [
            'fastapi',
            'uvicorn',
            'httpx',
            'pydantic',
            'asyncpg',
            'python-dotenv',
            'jinja2',
            'cryptography'
        ]
        
        missing_packages = []
        for package in required_packages:
            if package not in requirements:
                missing_packages.append(package)
            else:
                logger.info(f"  ✅ {package}")
        
        if missing_packages:
            logger.error(f"❌ Missing packages in requirements.txt: {missing_packages}")
            return False
        
        logger.info("✅ All required dependencies present")
        return True
        
    except FileNotFoundError:
        logger.error("❌ requirements.txt not found")
        return False

def check_railway_config():
    """Check Railway configuration files"""
    logger.info("🚂 Checking Railway configuration...")
    
    # Check railway.toml
    if not Path('railway.toml').exists():
        logger.error("❌ railway.toml not found")
        return False
    
    # Check Procfile
    if not Path('Procfile').exists():
        logger.error("❌ Procfile not found")
        return False
    
    # Check runtime.txt
    if not Path('runtime.txt').exists():
        logger.error("❌ runtime.txt not found")
        return False
    
    # Validate Procfile content
    try:
        with open('Procfile', 'r') as f:
            procfile_content = f.read().strip()
        
        if 'python start_web.py' not in procfile_content:
            logger.error("❌ Procfile should contain 'python start_web.py'")
            return False
    except Exception as e:
        logger.error(f"❌ Error reading Procfile: {e}")
        return False
    
    logger.info("✅ Railway configuration files present and valid")
    return True

async def main():
    """Main validation function"""
    logger.info("🚀 EnableBot Deployment Validation")
    logger.info("=" * 50)
    
    checks = [
        ("Files", check_files()),
        ("Environment", check_environment()),
        ("Dependencies", check_dependencies()),
        ("Railway Config", check_railway_config()),
        ("Database", await check_database())
    ]
    
    all_passed = True
    for check_name, result in checks:
        if not result:
            all_passed = False
    
    logger.info("=" * 50)
    
    if all_passed:
        logger.info("🎉 All validation checks passed!")
        logger.info("✅ Ready for Railway deployment")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Commit all changes to git")
        logger.info("2. Run: railway login")
        logger.info("3. Run: railway init")
        logger.info("4. Run: railway up")
        logger.info("5. Update Slack app redirect URI with Railway domain")
        return True
    else:
        logger.error("❌ Some validation checks failed")
        logger.error("Please fix the issues above before deploying")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)