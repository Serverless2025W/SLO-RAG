"""
Tests for conversation-manager handler.
"""

import importlib.util
import json
import os
import pytest
from unittest.mock import patch, Mock

# Mock redis before loading the handler
with patch.dict('sys.modules', {'redis': Mock()}):
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
    format_messages_for_llm = handler.format_messages_for_llm


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


class TestFormatMessagesForLLM:
    """Tests for LLM message formatting."""
    
    def test_format_empty_history(self):
        """Test formatting with empty history."""
        history = []
        current = {"role": "user", "content": "Hello"}
        messages = format_messages_for_llm(history, current)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
    
    def test_format_with_history(self):
        """Test formatting with existing history."""
        history = [
            {"role": "user", "content": "Hi", "timestamp": "2026-01-12T19:00:00Z"},
            {"role": "assistant", "content": "Hello!", "timestamp": "2026-01-12T19:00:01Z"}
        ]
        current = {"role": "user", "content": "How are you?"}
        messages = format_messages_for_llm(history, current)
        assert len(messages) == 3
        assert messages[0]["content"] == "Hi"
        assert messages[1]["content"] == "Hello!"
        assert messages[2]["content"] == "How are you?"
    
    def test_format_skips_system_messages(self):
        """Test that system messages (summaries) are skipped."""
        history = [
            {"role": "system", "content": "Summary of previous conversation", "timestamp": "2026-01-12T18:00:00Z"},
            {"role": "user", "content": "Hi", "timestamp": "2026-01-12T19:00:00Z"}
        ]
        current = {"role": "user", "content": "Hello"}
        messages = format_messages_for_llm(history, current)
        # System message should be skipped
        assert len(messages) == 2
        assert messages[0]["content"] == "Hi"


class TestHandle:
    """Tests for main handler function."""
    
    @patch.object(handler, 'get_conversation_history')
    @patch.object(handler, 'call_llm_api')
    def test_handle_valid_user_message(self, mock_llm, mock_history):
        """Test handling valid user message."""
        mock_history.return_value = []
        mock_llm.return_value = {
            "content": "Test response",
            "usage": {"total_tokens": 100}
        }
        
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
        assert "llm_response" in response_body
    
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
    
    @patch.object(handler, 'get_conversation_history')
    @patch.object(handler, 'call_llm_api')
    def test_handle_with_metadata(self, mock_llm, mock_history):
        """Test handling message with metadata."""
        mock_history.return_value = []
        mock_llm.return_value = {
            "content": "Test response",
            "usage": {"total_tokens": 100}
        }
        
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
    
    @patch.object(handler, 'get_conversation_history')
    @patch.object(handler, 'call_llm_api')
    def test_handle_llm_failure(self, mock_llm, mock_history):
        """Test handling LLM API failure."""
        mock_history.return_value = []
        mock_llm.side_effect = Exception("LLM API error")
        
        data = {
            "session_id": "test-123",
            "role": "user",
            "content": "Hello",
            "timestamp": "2026-01-12T20:00:00Z"
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 500
        response_body = json.loads(result["body"])
        assert "error" in response_body
        assert "LLM API" in response_body["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
