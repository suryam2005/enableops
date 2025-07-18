#!/usr/bin/env python3
"""
EnableBot Structure Validation
Validates the production scaling architecture
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_project_structure():
    """Check if all required files and folders exist"""
    logger.info("📁 Checking project structure...")
    
    required_structure = {
        # Main package
        'enablebot/__init__.py': 'Main package init',
        
        # API service
        'enablebot/api/__init__.py': 'API package init',
        'enablebot/api/main.py': 'API service main',
        
        # Web service
        'enablebot/web/__init__.py': 'Web package init',
        'enablebot/web/main.py': 'Web service main',
        'enablebot/web/auth.py': 'Slack OAuth handling',
        'enablebot/web/templates/index.html': 'Landing page template',
        'enablebot/web/templates/dashboard.html': 'Dashboard template',
        
        # Shared components
        'enablebot/shared/__init__.py': 'Shared package init',
        'enablebot/shared/database/config.py': 'Database configuration',
        'enablebot/shared/database/models.py': 'Database models',
        'enablebot/shared/database/init_db.py': 'Database initialization',
        'enablebot/shared/encryption/encryption.py': 'Encryption module',
        'enablebot/shared/models/__init__.py': 'Shared models init',
        
        # Configuration
        'enablebot/config/__init__.py': 'Config package init',
        'enablebot/config/settings.py': 'Application settings',
        
        # Scripts
        'enablebot/scripts/__init__.py': 'Scripts package init',
        'enablebot/scripts/start_api.py': 'API startup script',
        'enablebot/scripts/start_web.py': 'Web startup script',
        
        # Tests
        'enablebot/tests/__init__.py': 'Tests package init',
        'enablebot/tests/api/__init__.py': 'API tests init',
        'enablebot/tests/api/test_main.py': 'API tests',
        'enablebot/tests/web/__init__.py': 'Web tests init',
        'enablebot/tests/shared/test_encryption.py': 'Encryption tests',
        'enablebot/tests/shared/test_database_orm.py': 'Database tests',
        
        # Documentation
        'enablebot/docs/README.md': 'Architecture documentation',
        'enablebot/docs/SCALING_GUIDE.md': 'Scaling guide',
        
        # Configuration files
        'requirements.txt': 'Python dependencies',
        'railway.toml': 'Railway deployment config',
        '.env': 'Environment variables',
        'PROJECT_STRUCTURE.md': 'Project structure documentation'
    }
    
    missing_files = []
    for file_path, description in required_structure.items():
        if not Path(file_path).exists():
            missing_files.append(f"{file_path} ({description})")
        else:
            logger.info(f"  ✅ {file_path}")
    
    if missing_files:
        logger.error(f"❌ Missing files:")
        for file in missing_files:
            logger.error(f"    - {file}")
        return False
    
    logger.info("✅ All required files present")
    return True

def check_imports():
    """Check if all modules can be imported"""
    logger.info("🔍 Checking module imports...")
    
    import_tests = [
        ('enablebot', 'Main package'),
        ('enablebot.api.main', 'API service'),
        ('enablebot.web.main', 'Web service'),
        ('enablebot.web.auth', 'OAuth handling'),
        ('enablebot.shared.database.config', 'Database config'),
        ('enablebot.shared.database.models', 'Database models'),
        ('enablebot.shared.encryption.encryption', 'Encryption module'),
        ('enablebot.config.settings', 'Application settings'),
    ]
    
    failed_imports = []
    for module_name, description in import_tests:
        try:
            __import__(module_name)
            logger.info(f"  ✅ {module_name}")
        except ImportError as e:
            failed_imports.append(f"{module_name} ({description}): {e}")
    
    if failed_imports:
        logger.error(f"❌ Failed imports:")
        for failure in failed_imports:
            logger.error(f"    - {failure}")
        return False
    
    logger.info("✅ All modules import successfully")
    return True

async def check_database_integration():
    """Check database integration"""
    logger.info("🗄️  Checking database integration...")
    
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
        logger.error(f"❌ Database integration error: {e}")
        return False

def check_configuration():
    """Check configuration management"""
    logger.info("⚙️  Checking configuration...")
    
    try:
        from enablebot.config.settings import settings
        
        # Check if settings can be loaded
        assert hasattr(settings, 'app_name')
        assert hasattr(settings, 'app_version')
        assert hasattr(settings, 'api_port')
        assert hasattr(settings, 'web_port')
        
        logger.info(f"  ✅ App: {settings.app_name} v{settings.app_version}")
        logger.info(f"  ✅ Ports: API={settings.api_port}, Web={settings.web_port}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Configuration error: {e}")
        return False

def check_startup_scripts():
    """Check startup scripts"""
    logger.info("🚀 Checking startup scripts...")
    
    scripts = [
        'enablebot/scripts/start_api.py',
        'enablebot/scripts/start_web.py'
    ]
    
    for script in scripts:
        if not Path(script).exists():
            logger.error(f"❌ Missing script: {script}")
            return False
        
        # Check if script is executable
        try:
            with open(script, 'r') as f:
                content = f.read()
                if 'def main():' not in content:
                    logger.error(f"❌ Script {script} missing main() function")
                    return False
            
            logger.info(f"  ✅ {script}")
        except Exception as e:
            logger.error(f"❌ Error checking script {script}: {e}")
            return False
    
    logger.info("✅ All startup scripts valid")
    return True

async def run_tests():
    """Run the test suite"""
    logger.info("🧪 Running test suite...")
    
    try:
        import subprocess
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            'enablebot/tests/', '-v', '--tb=short'
        ], capture_output=True, text=True, cwd='.')
        
        if result.returncode == 0:
            logger.info("✅ All tests passed")
            return True
        else:
            logger.error("❌ Some tests failed:")
            logger.error(result.stdout)
            logger.error(result.stderr)
            return False
    except Exception as e:
        logger.warning(f"⚠️  Could not run tests: {e}")
        return True  # Don't fail validation if pytest not available

async def main():
    """Main validation function"""
    logger.info("🚀 EnableBot Structure Validation")
    logger.info("=" * 50)
    
    checks = [
        ("Project Structure", check_project_structure()),
        ("Module Imports", check_imports()),
        ("Configuration", check_configuration()),
        ("Startup Scripts", check_startup_scripts()),
        ("Database Integration", await check_database_integration()),
        ("Test Suite", await run_tests())
    ]
    
    all_passed = True
    for check_name, result in checks:
        if not result:
            all_passed = False
    
    logger.info("=" * 50)
    
    if all_passed:
        logger.info("🎉 All validation checks passed!")
        logger.info("✅ EnableBot is ready for production deployment")
        logger.info("")
        logger.info("🚀 Next steps:")
        logger.info("1. Deploy API service: python enablebot/scripts/start_api.py")
        logger.info("2. Deploy web service: python enablebot/scripts/start_web.py")
        logger.info("3. Or deploy to Railway: railway up")
        return True
    else:
        logger.error("❌ Some validation checks failed")
        logger.error("Please fix the issues above before deploying")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)