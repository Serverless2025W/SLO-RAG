"""
Tests for conversation-manager handler.
"""

import importlib.util
import json
import os
import pytest

def load_handler():
    handler_path = os.path.join(os.path.dirname(__file__), "handler.py")
    spec = importlib.util.spec_from_file_location("conversation_manager_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

handler = load_handler()
handle = handler.handle
validate_conversation_event = handler.validate_conversation_event
parse_input = handler.parse_input


class MockRequest:
    """Mock request object for testing."""
    def __init__(self, body):
        self.body = body


class MockContext:
    """Mock context object for testing."""
    pass


class TestParseInput:
    """Tests for input parsing."""
    
    def test_parse_json_string(self):
        """Test parsing JSON string."""
        req = MockRequest('{"session_id": "test-123", "role": "user", "content": "Hello", "timestamp": "2026-01-12T20:00:00Z"}')
        result = parse_input(req)
        assert result["session_id"] == "test-123"
        assert result["role"] == "user"
    
    def test_parse_dict(self):
        """Test parsing dictionary."""
        data = {"session_id": "test-123", "role": "user", "content": "Hello", "timestamp": "2026-01-12T20:00:00Z"}
        req = MockRequest(data)
        result = parse_input(req)
        assert result == data
    
    def test_parse_bytes(self):
        """Test parsing bytes."""
        req = MockRequest(b'{"session_id": "test-123", "role": "user", "content": "Hello", "timestamp": "2026-01-12T20:00:00Z"}')
        result = parse_input(req)
        assert result["session_id"] == "test-123"


class TestValidateConversationEvent:
    """Tests for conversation event validation."""
    
    def test_valid_event(self):
        """Test validation of valid event."""
        data = {
            "session_id": "test-123",
            "role": "user",
            "content": "Hello",
            "timestamp": "2026-01-12T20:00:00Z"
        }
        is_valid, error = validate_conversation_event(data)
        assert is_valid is True
        assert error is None
    
    def test_missing_session_id(self):
        """Test validation fails with missing session_id."""
        data = {
            "role": "user",
            "content": "Hello",
            "timestamp": "2026-01-12T20:00:00Z"
        }
        is_valid, error = validate_conversation_event(data)
        assert is_valid is False
        assert "session_id" in error
    
    def test_invalid_role(self):
        """Test validation fails with invalid role."""
        data = {
            "session_id": "test-123",
            "role": "invalid",
            "content": "Hello",
            "timestamp": "2026-01-12T20:00:00Z"
        }
        is_valid, error = validate_conversation_event(data)
        assert is_valid is False
        assert "Invalid role" in error
    
    def test_empty_content(self):
        """Test validation fails with empty content."""
        data = {
            "session_id": "test-123",
            "role": "user",
            "content": "",
            "timestamp": "2026-01-12T20:00:00Z"
        }
        is_valid, error = validate_conversation_event(data)
        assert is_valid is False
        assert "content" in error
    
    def test_assistant_role(self):
        """Test validation accepts assistant role."""
        data = {
            "session_id": "test-123",
            "role": "assistant",
            "content": "Hello there",
            "timestamp": "2026-01-12T20:00:00Z"
        }
        is_valid, error = validate_conversation_event(data)
        assert is_valid is True


class TestHandle:
    """Tests for main handler function."""
    
    def test_handle_valid_user_message(self):
        """Test handling valid user message."""
        data = {
            "event_type": "user_query",
            "session_id": "test-123",
            "role": "user",
            "content": "Hello, how are you?",
            "timestamp": "2026-01-12T20:00:00Z",
            "metadata": {
                "tokens": 10,
                "model": "gpt-4"
            }
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert response_body["status"] == "success"
        assert response_body["session_id"] == "test-123"
        assert response_body["role"] == "user"
    
    def test_handle_valid_assistant_message(self):
        """Test handling valid assistant message."""
        data = {
            "event_type": "llm_response",
            "session_id": "test-123",
            "role": "assistant",
            "content": "I'm doing well, thank you!",
            "timestamp": "2026-01-12T20:00:01Z",
            "metadata": {
                "tokens": 150,
                "model": "gpt-4"
            }
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert response_body["status"] == "success"
        assert response_body["role"] == "assistant"
    
    def test_handle_invalid_json(self):
        """Test handling invalid JSON."""
        req = MockRequest("invalid json")
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 400
        response_body = json.loads(result["body"])
        assert "error" in response_body
    
    def test_handle_missing_required_field(self):
        """Test handling message with missing required field."""
        data = {
            "role": "user",
            "content": "Hello",
            "timestamp": "2026-01-12T20:00:00Z"
            # Missing session_id
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 400
        response_body = json.loads(result["body"])
        assert response_body["error"] == "Validation failed"
    
    def test_handle_invalid_role(self):
        """Test handling message with invalid role."""
        data = {
            "session_id": "test-123",
            "role": "invalid_role",
            "content": "Hello",
            "timestamp": "2026-01-12T20:00:00Z"
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 400
        response_body = json.loads(result["body"])
        assert "error" in response_body
    
    def test_handle_with_metadata(self):
        """Test handling message with metadata."""
        data = {
            "session_id": "test-123",
            "role": "user",
            "content": "Hello",
            "timestamp": "2026-01-12T20:00:00Z",
            "metadata": {
                "query_id": "query-123",
                "tokens": 10,
                "model": "gpt-4"
            }
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert response_body["status"] == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
