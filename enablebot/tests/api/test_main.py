"""
Test Suite for EnableBot API Service
Tests multi-tenant AI backend functionality
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Import the API app
from enablebot.api.main import app, slack_manager, ai_assistant

client = TestClient(app)

class TestAPIEndpoints:
    """Test API endpoints"""
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["service"] == "EnableBot AI Service"
        assert data["version"] == "3.0.0"
    
    def test_slack_events_url_verification(self):
        """Test Slack URL verification challenge"""
        challenge_data = {
            "type": "url_verification",
            "challenge": "test_challenge_123"
        }
        
        response = client.post("/slack/events", json=challenge_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["challenge"] == "test_challenge_123"
    
    def test_slack_events_invalid_signature(self):
        """Test Slack events with invalid signature"""
        event_data = {
            "type": "event_callback",
            "team_id": "T123456789",
            "event": {
                "type": "message",
                "user": "U123456789",
                "text": "Hello bot",
                "channel": "C123456789"
            }
        }
        
        # Mock signature verification to fail
        with patch('enablebot.api.main.verify_slack_signature', return_value=False):
            response = client.post("/slack/events", json=event_data)
            assert response.status_code == 401

class TestSlackClientManager:
    """Test SlackClientManager functionality"""
    
    @pytest.mark.asyncio
    async def test_slack_client_manager_initialization(self):
        """Test SlackClientManager can be initialized"""
        manager = slack_manager
        assert manager is not None
        assert manager.clients == {}
        assert manager.base_url == "https://slack.com/api"
    
    @pytest.mark.asyncio
    async def test_get_client_no_tenant(self):
        """Test getting client for non-existent tenant"""
        with patch('enablebot.shared.database.config.db') as mock_db:
            mock_db.fetchrow.return_value = None
            
            client = await slack_manager.get_client("T_NONEXISTENT")
            assert client is None

class TestTenantAwareAI:
    """Test AI processing functionality"""
    
    @pytest.mark.asyncio
    async def test_ai_assistant_initialization(self):
        """Test AI assistant can be initialized"""
        assistant = ai_assistant
        assert assistant is not None
        assert hasattr(assistant, 'base_prompt')
        assert hasattr(assistant, 'process_message')
    
    @pytest.mark.asyncio
    async def test_process_message_no_openai(self):
        """Test message processing without OpenAI client"""
        with patch('enablebot.api.main.openai_client', None):
            response = await ai_assistant.process_message("T123", "U123", "Hello")
            assert "not able to access my AI capabilities" in response

class TestDatabaseFunctions:
    """Test database interaction functions"""
    
    @pytest.mark.asyncio
    async def test_get_user_profile_new_user(self):
        """Test getting profile for new user"""
        from enablebot.api.main import get_user_profile
        
        with patch('enablebot.shared.database.config.db') as mock_db:
            # Mock no existing user
            mock_db.fetchrow.return_value = None
            mock_db.execute.return_value = None
            
            profile = await get_user_profile("T123", "U123")
            
            assert profile is not None
            assert profile["slack_user_id"] == "U123"
            assert profile["full_name"] == "Team Member"
    
    @pytest.mark.asyncio
    async def test_search_knowledge_base(self):
        """Test knowledge base search"""
        from enablebot.api.main import search_knowledge_base
        
        with patch('enablebot.shared.database.config.db') as mock_db:
            # Mock search results
            mock_db.fetch.return_value = [
                {
                    "title": "Test Document",
                    "content": "This is test content for the knowledge base search functionality.",
                    "document_type": "guide",
                    "metadata": {"author": "test"}
                }
            ]
            
            results = await search_knowledge_base("T123", "test query")
            
            assert len(results) == 1
            assert results[0]["title"] == "Test Document"
            assert "test content" in results[0]["content"]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])