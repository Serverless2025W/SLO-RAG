"""
Tests for context-summarizer handler.
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
        spec = importlib.util.spec_from_file_location("context_summarizer_handler", handler_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    handler = load_handler()
    handle = handler.handle
    validate_summarization_trigger = handler.validate_summarization_trigger
    parse_input = handler.parse_input
    format_messages_for_summarization = handler.format_messages_for_summarization


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
        req = MockRequest('{"session_id": "test-123", "trigger_reason": "token_threshold", "current_tokens": 4500, "current_messages": 25, "threshold": 4000}')
        result = parse_input(req)
        assert result["session_id"] == "test-123"
        assert result["trigger_reason"] == "token_threshold"
    
    def test_parse_dict(self):
        """Test parsing dictionary."""
        data = {"session_id": "test-123", "trigger_reason": "token_threshold", "current_tokens": 4500, "current_messages": 25, "threshold": 4000}
        req = MockRequest(data)
        result = parse_input(req)
        assert result == data


class TestValidateSummarizationTrigger:
    """Tests for summarization trigger validation."""
    
    def test_valid_trigger(self):
        """Test validation of valid trigger."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is True
        assert error is None
    
    def test_missing_session_id(self):
        """Test validation fails with missing session_id."""
        data = {
            "trigger_reason": "token_threshold",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is False
        assert "session_id" in error
    
    def test_invalid_trigger_reason(self):
        """Test validation fails with invalid trigger_reason."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "invalid_reason",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is False
        assert "trigger_reason" in error
    
    def test_negative_tokens(self):
        """Test validation fails with negative token count."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": -100,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is False
    
    def test_message_threshold_trigger(self):
        """Test validation accepts message_threshold trigger."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "message_threshold",
            "current_tokens": 3000,
            "current_messages": 25,
            "threshold": 20
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is True
    
    def test_manual_trigger(self):
        """Test validation accepts manual trigger."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "manual",
            "current_tokens": 2000,
            "current_messages": 15,
            "threshold": 0
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is True


class TestFormatMessagesForSummarization:
    """Tests for message formatting for summarization."""
    
    def test_format_basic_history(self):
        """Test formatting basic conversation history."""
        history = [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-12T20:00:00Z"},
            {"role": "assistant", "content": "Hi there", "timestamp": "2026-01-12T20:00:01Z"}
        ]
        messages = format_messages_for_summarization(history)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
    
    def test_format_skips_system_messages(self):
        """Test that system messages (previous summaries) are skipped."""
        history = [
            {"role": "system", "content": "Previous summary", "timestamp": "2026-01-12T19:00:00Z"},
            {"role": "user", "content": "Hello", "timestamp": "2026-01-12T20:00:00Z"},
            {"role": "assistant", "content": "Hi", "timestamp": "2026-01-12T20:00:01Z"}
        ]
        messages = format_messages_for_summarization(history)
        assert len(messages) == 2
        assert messages[0]["content"] == "Hello"


class TestHandle:
    """Tests for main handler function."""
    
    @patch.object(handler, 'get_conversation_history')
    @patch.object(handler, 'call_llm_for_summarization')
    def test_handle_valid_token_threshold_trigger(self, mock_llm, mock_history):
        """Test handling valid token threshold trigger."""
        mock_history.return_value = [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-12T20:00:00Z"},
            {"role": "assistant", "content": "Hi", "timestamp": "2026-01-12T20:00:01Z"}
        ]
        mock_llm.return_value = {
            "summary": "Test summary of conversation",
            "usage": {"total_tokens": 100}
        }
        
        data = {
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert response_body["status"] == "success"
        assert response_body["session_id"] == "test-123"
        assert "summary" in response_body
        assert response_body["trigger_reason"] == "token_threshold"
        assert response_body["compressed_from"]["messages"] == 25
        assert response_body["compressed_from"]["tokens"] == 4500
    
    @patch.object(handler, 'get_conversation_history')
    @patch.object(handler, 'call_llm_for_summarization')
    def test_handle_message_threshold_trigger(self, mock_llm, mock_history):
        """Test handling message threshold trigger."""
        mock_history.return_value = [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-12T20:00:00Z"}
        ]
        mock_llm.return_value = {
            "summary": "Test summary",
            "usage": {"total_tokens": 50}
        }
        
        data = {
            "session_id": "test-123",
            "trigger_reason": "message_threshold",
            "current_tokens": 3000,
            "current_messages": 25,
            "threshold": 20
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert response_body["status"] == "success"
        assert response_body["trigger_reason"] == "message_threshold"
    
    @patch.object(handler, 'get_conversation_history')
    @patch.object(handler, 'call_llm_for_summarization')
    def test_handle_manual_trigger(self, mock_llm, mock_history):
        """Test handling manual trigger."""
        mock_history.return_value = [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-12T20:00:00Z"}
        ]
        mock_llm.return_value = {
            "summary": "Manual summary",
            "usage": {}
        }
        
        data = {
            "session_id": "test-123",
            "trigger_reason": "manual",
            "current_tokens": 2000,
            "current_messages": 15,
            "threshold": 0
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert response_body["status"] == "success"
        assert response_body["trigger_reason"] == "manual"
    
    def test_handle_invalid_json(self):
        """Test handling invalid JSON."""
        req = MockRequest("invalid json")
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 400
        response_body = json.loads(result["body"])
        assert "error" in response_body
    
    def test_handle_missing_required_field(self):
        """Test handling trigger with missing required field."""
        data = {
            "trigger_reason": "token_threshold",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
            # Missing session_id
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 400
        response_body = json.loads(result["body"])
        assert response_body["error"] == "Validation failed"
    
    def test_handle_invalid_trigger_reason(self):
        """Test handling trigger with invalid trigger_reason."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "invalid",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 400
        response_body = json.loads(result["body"])
        assert "error" in response_body
    
    @patch.object(handler, 'get_conversation_history')
    def test_handle_no_conversation_history(self, mock_history):
        """Test handling when no conversation history exists."""
        mock_history.return_value = []
        
        data = {
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 404
        response_body = json.loads(result["body"])
        assert "error" in response_body
        assert "No conversation history" in response_body["error"]
    
    @patch.object(handler, 'get_conversation_history')
    @patch.object(handler, 'call_llm_for_summarization')
    def test_handle_llm_failure(self, mock_llm, mock_history):
        """Test handling LLM summarization failure."""
        mock_history.return_value = [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-12T20:00:00Z"}
        ]
        mock_llm.side_effect = Exception("LLM API error")
        
        data = {
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 500
        response_body = json.loads(result["body"])
        assert "error" in response_body
        assert "LLM summarization failed" in response_body["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
