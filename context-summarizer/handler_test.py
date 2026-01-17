"""
Unit tests for context-summarizer handler
"""

import pytest
import json
import sys
import os
import importlib.util
from unittest.mock import patch, MagicMock

# Load the context-summarizer handler module directly to avoid caching issues
def load_handler_module():
    """Load handler module directly from file to avoid import caching."""
    handler_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handler.py")
    spec = importlib.util.spec_from_file_location("context_summarizer_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Load the handler module
handler = load_handler_module()

# Extract functions for easier access
parse_input = handler.parse_input
validate_summarization_trigger = handler.validate_summarization_trigger
format_messages_for_summarization = handler.format_messages_for_summarization
handle = handler.handle
get_conversation_history = handler.get_conversation_history
replace_conversation_with_summary = handler.replace_conversation_with_summary
call_llm_for_summarization = handler.call_llm_for_summarization


class TestParseInput:
    """Tests for parse_input function."""
    
    def test_parse_json_string(self):
        result = parse_input('{"key": "value"}')
        assert result == {"key": "value"}
    
    def test_parse_dict(self):
        result = parse_input({"key": "value"})
        assert result == {"key": "value"}
    
    def test_parse_bytes(self):
        result = parse_input(b'{"key": "value"}')
        assert result == {"key": "value"}


class TestValidateSummarizationTrigger:
    """Tests for validate_summarization_trigger function."""
    
    def test_valid_trigger(self):
        data = {
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": 5000,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is True
        assert error is None
    
    def test_missing_session_id(self):
        data = {
            "trigger_reason": "token_threshold",
            "current_tokens": 5000,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is False
        assert "session_id" in error
    
    def test_invalid_trigger_reason(self):
        data = {
            "session_id": "test-123",
            "trigger_reason": "invalid_reason",
            "current_tokens": 5000,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is False
        assert "trigger_reason" in error
    
    def test_negative_tokens(self):
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
        data = {
            "session_id": "test-123",
            "trigger_reason": "message_threshold",
            "current_tokens": 100,
            "current_messages": 25,
            "threshold": 20
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is True
    
    def test_manual_trigger(self):
        data = {
            "session_id": "test-123",
            "trigger_reason": "manual",
            "current_tokens": 100,
            "current_messages": 5,
            "threshold": 0
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is True


class TestFormatMessagesForSummarization:
    """Tests for format_messages_for_summarization function."""
    
    def test_format_basic_history(self):
        history = [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-17T10:00:00Z"},
            {"role": "assistant", "content": "Hi!", "timestamp": "2026-01-17T10:00:01Z"}
        ]
        result = format_messages_for_summarization(history)
        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "Hello"}
        assert result[1] == {"role": "assistant", "content": "Hi!"}
    
    def test_format_skips_system_messages(self):
        history = [
            {"role": "system", "content": "Previous summary", "timestamp": "2026-01-17T10:00:00Z"},
            {"role": "user", "content": "New message", "timestamp": "2026-01-17T10:00:01Z"},
            {"role": "assistant", "content": "Response", "timestamp": "2026-01-17T10:00:02Z"}
        ]
        result = format_messages_for_summarization(history)
        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "New message"}
        assert result[1] == {"role": "assistant", "content": "Response"}


class TestGetConversationHistory:
    """Tests for get_conversation_history function."""
    
    def test_get_history_success(self):
        """Test getting conversation history with mocked Redis."""
        mock_client = MagicMock()
        mock_client.lrange.return_value = [
            '{"role": "user", "content": "Hi", "timestamp": "2026-01-17T10:00:00Z"}',
            '{"role": "assistant", "content": "Hello!", "timestamp": "2026-01-17T10:00:01Z"}'
        ]
        
        # Reset global state and mock init
        handler.redis_client = mock_client
        
        result = get_conversation_history("test-123")
        
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        
        # Cleanup
        handler.redis_client = None
    
    def test_get_history_empty(self):
        """Test getting empty conversation history."""
        mock_client = MagicMock()
        mock_client.lrange.return_value = []
        
        handler.redis_client = mock_client
        
        result = get_conversation_history("test-123")
        assert result == []
        
        handler.redis_client = None
    
    def test_get_history_no_redis(self):
        """Test getting history when Redis is unavailable."""
        handler.redis_client = None
        
        # Patch the init function to return None
        original_init = handler.init_redis_client
        handler.init_redis_client = lambda: None
        
        result = get_conversation_history("test-123")
        assert result == []
        
        handler.init_redis_client = original_init


class TestReplaceConversationWithSummary:
    """Tests for replace_conversation_with_summary function."""
    
    def test_replace_success(self):
        """Test replacing conversation with summary."""
        mock_client = MagicMock()
        
        handler.redis_client = mock_client
        
        result = replace_conversation_with_summary(
            "test-123",
            "This is a summary",
            "2026-01-17T10:00:00Z"
        )
        
        assert result is True
        mock_client.delete.assert_called()
        mock_client.rpush.assert_called_once()
        
        handler.redis_client = None
    
    def test_replace_no_redis(self):
        """Test replacing when Redis is unavailable."""
        handler.redis_client = None
        original_init = handler.init_redis_client
        handler.init_redis_client = lambda: None
        
        result = replace_conversation_with_summary(
            "test-123",
            "This is a summary",
            "2026-01-17T10:00:00Z"
        )
        assert result is False
        
        handler.init_redis_client = original_init


class TestCallLLMForSummarization:
    """Tests for call_llm_for_summarization placeholder."""
    
    def test_placeholder_returns_summary(self):
        """Test that placeholder function returns expected structure."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"}
        ]
        
        result = call_llm_for_summarization(messages)
        
        assert "summary" in result
        assert "usage" in result
        assert "prompt_tokens" in result["usage"]
        assert "completion_tokens" in result["usage"]
        assert "total_tokens" in result["usage"]
    
    def test_placeholder_message_count_in_summary(self):
        """Test that placeholder includes message count."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "How are you?"}
        ]
        
        result = call_llm_for_summarization(messages)
        
        # Placeholder should mention 3 messages
        assert "3" in result["summary"]


class TestHandle:
    """Tests for main handle function."""
    
    def test_handle_valid_trigger(self):
        """Test handling a valid summarization trigger."""
        mock_client = MagicMock()
        mock_client.lrange.return_value = [
            '{"role": "user", "content": "Hi", "timestamp": "2026-01-17T10:00:00Z"}',
            '{"role": "assistant", "content": "Hello!", "timestamp": "2026-01-17T10:00:01Z"}'
        ]
        
        handler.redis_client = mock_client
        
        req = json.dumps({
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": 5000,
            "current_messages": 25,
            "threshold": 4000
        })
        
        result = handle(req, None)
        
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "success"
        assert "summary" in body
        
        handler.redis_client = None
    
    def test_handle_no_history(self):
        """Test handling trigger when no history exists."""
        mock_client = MagicMock()
        mock_client.lrange.return_value = []
        
        handler.redis_client = mock_client
        
        req = json.dumps({
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": 5000,
            "current_messages": 25,
            "threshold": 4000
        })
        
        result = handle(req, None)
        
        assert result["statusCode"] == 404
        body = json.loads(result["body"])
        assert "error" in body
        
        handler.redis_client = None
    
    def test_handle_invalid_json(self):
        """Test handling invalid JSON input."""
        result = handle("not valid json", None)
        assert result["statusCode"] == 400
    
    def test_handle_missing_field(self):
        """Test handling request with missing required field."""
        req = json.dumps({"session_id": "test-123"})
        result = handle(req, None)
        assert result["statusCode"] == 400
    
    def test_handle_invalid_trigger_reason(self):
        """Test handling request with invalid trigger reason."""
        req = json.dumps({
            "session_id": "test-123",
            "trigger_reason": "invalid",
            "current_tokens": 5000,
            "current_messages": 25,
            "threshold": 4000
        })
        result = handle(req, None)
        assert result["statusCode"] == 400
    
    def test_handle_llm_failure(self):
        """Test handling when LLM call fails."""
        mock_client = MagicMock()
        mock_client.lrange.return_value = [
            '{"role": "user", "content": "Hi", "timestamp": "2026-01-17T10:00:00Z"}'
        ]
        
        handler.redis_client = mock_client
        
        # Mock LLM to raise exception
        original_llm = handler.call_llm_for_summarization
        handler.call_llm_for_summarization = MagicMock(side_effect=Exception("LLM API error"))
        
        req = json.dumps({
            "session_id": "test-123",
            "trigger_reason": "manual",
            "current_tokens": 100,
            "current_messages": 5,
            "threshold": 0
        })
        
        result = handle(req, None)
        
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body
        
        # Restore
        handler.call_llm_for_summarization = original_llm
        handler.redis_client = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
