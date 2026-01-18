"""
Tests for conversation-manager handler.
"""

import pytest
import json
import sys
import os
from unittest.mock import patch, MagicMock

# Add ONLY this handler directory to path
_handler_dir = os.path.dirname(os.path.abspath(__file__))
if _handler_dir not in sys.path:
    sys.path.insert(0, _handler_dir)

# Clear any cached handler module
if 'handler' in sys.modules:
    del sys.modules['handler']

# Import handler functions
from handler import (
    parse_input,
    validate_conversation_event,
    format_messages_for_llm,
    handle,
    store_message,
    check_summarization_threshold,
    trigger_summarization
)


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


class TestValidateConversationEvent:
    """Tests for validate_conversation_event function."""
    
    def test_valid_event(self):
        data = {
            "session_id": "test-123",
            "role": "user",
            "content": "Hello",
            "timestamp": "2026-01-17T10:00:00Z"
        }
        is_valid, error = validate_conversation_event(data)
        assert is_valid is True
        assert error is None
    
    def test_missing_session_id(self):
        data = {"role": "user", "content": "Hello", "timestamp": "2026-01-17T10:00:00Z"}
        is_valid, error = validate_conversation_event(data)
        assert is_valid is False
        assert "session_id" in error
    
    def test_invalid_role(self):
        data = {
            "session_id": "test-123",
            "role": "system",
            "content": "Hello",
            "timestamp": "2026-01-17T10:00:00Z"
        }
        is_valid, error = validate_conversation_event(data)
        assert is_valid is False
        assert "role" in error
    
    def test_empty_content(self):
        data = {
            "session_id": "test-123",
            "role": "user",
            "content": "",
            "timestamp": "2026-01-17T10:00:00Z"
        }
        is_valid, error = validate_conversation_event(data)
        assert is_valid is False
        assert "content" in error


class TestFormatMessagesForLLM:
    """Tests for format_messages_for_llm function."""
    
    def test_format_empty_history(self):
        current = {"role": "user", "content": "Hello"}
        result = format_messages_for_llm([], current)
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "Hello"}
    
    def test_format_with_history(self):
        history = [
            {"role": "user", "content": "Hi", "timestamp": "2026-01-17T10:00:00Z"},
            {"role": "assistant", "content": "Hello!", "timestamp": "2026-01-17T10:00:01Z"}
        ]
        current = {"role": "user", "content": "How are you?"}
        result = format_messages_for_llm(history, current)
        assert len(result) == 3
        assert result[0] == {"role": "user", "content": "Hi"}
        assert result[1] == {"role": "assistant", "content": "Hello!"}
        assert result[2] == {"role": "user", "content": "How are you?"}
    
    def test_format_skips_system_messages(self):
        history = [
            {"role": "system", "content": "Previous summary", "timestamp": "2026-01-17T10:00:00Z"},
            {"role": "user", "content": "New message", "timestamp": "2026-01-17T10:00:01Z"}
        ]
        current = {"role": "user", "content": "Another message"}
        result = format_messages_for_llm(history, current)
        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "New message"}
        assert result[1] == {"role": "user", "content": "Another message"}


class TestStoreMessage:
    """Tests for store_message function."""
    
    @patch('handler.init_redis_client')
    def test_store_message_success(self, mock_init):
        mock_client = MagicMock()
        mock_client.llen.return_value = 5
        mock_client.get.return_value = "100"
        mock_client.hgetall.return_value = {"created_at": "2026-01-17T10:00:00Z"}
        mock_init.return_value = mock_client
        
        result = store_message("test-123", "user", "Hello", "2026-01-17T10:00:00Z", tokens=10)
        
        assert result is True
        mock_client.rpush.assert_called_once()
    
    @patch('handler.init_redis_client')
    def test_store_message_no_redis(self, mock_init):
        mock_init.return_value = None
        result = store_message("test-123", "user", "Hello", "2026-01-17T10:00:00Z")
        assert result is False


class TestCheckSummarizationThreshold:
    """Tests for check_summarization_threshold function."""
    
    @patch('handler.init_redis_client')
    def test_token_threshold_exceeded(self, mock_init):
        mock_client = MagicMock()
        mock_client.get.return_value = "5000"  # Exceeds 4000 threshold
        mock_client.llen.return_value = 10
        mock_init.return_value = mock_client
        
        should_trigger, reason, tokens, messages = check_summarization_threshold("test-123")
        
        assert should_trigger is True
        assert reason == "token_threshold"
        assert tokens == 5000
    
    @patch('handler.init_redis_client')
    def test_message_threshold_exceeded(self, mock_init):
        mock_client = MagicMock()
        mock_client.get.return_value = "100"
        mock_client.llen.return_value = 25  # Exceeds 20 threshold
        mock_init.return_value = mock_client
        
        should_trigger, reason, tokens, messages = check_summarization_threshold("test-123")
        
        assert should_trigger is True
        assert reason == "message_threshold"
        assert messages == 25
    
    @patch('handler.init_redis_client')
    def test_no_threshold_exceeded(self, mock_init):
        mock_client = MagicMock()
        mock_client.get.return_value = "100"
        mock_client.llen.return_value = 5
        mock_init.return_value = mock_client
        
        should_trigger, reason, tokens, messages = check_summarization_threshold("test-123")
        
        assert should_trigger is False
        assert reason is None


class TestTriggerSummarization:
    """Tests for trigger_summarization function."""
    
    @patch('handler.init_kafka_producer')
    def test_trigger_success(self, mock_init):
        mock_producer = MagicMock()
        mock_future = MagicMock()
        mock_future.get.return_value = MagicMock(topic="summarization-triggers", offset=1)
        mock_producer.send.return_value = mock_future
        mock_init.return_value = mock_producer
        
        result = trigger_summarization("test-123", "token_threshold", 5000, 25)
        
        assert result is True
        mock_producer.send.assert_called_once()
    
    @patch('handler.init_kafka_producer')
    def test_trigger_no_kafka(self, mock_init):
        mock_init.return_value = None
        result = trigger_summarization("test-123", "token_threshold", 5000, 25)
        assert result is False


class TestHandle:
    """Tests for main handle function."""
    
    @patch('handler.init_redis_client')
    @patch('handler.init_kafka_producer')
    @patch('handler.call_llm_api')
    def test_handle_valid_user_message(self, mock_llm, mock_kafka, mock_redis):
        # Setup mocks
        mock_client = MagicMock()
        mock_client.llen.return_value = 5
        mock_client.get.return_value = "100"
        mock_client.hgetall.return_value = {}
        mock_client.lrange.return_value = []
        mock_redis.return_value = mock_client
        mock_kafka.return_value = None
        mock_llm.return_value = {
            "content": "Hello! How can I help?",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        }
        
        req = json.dumps({
            "session_id": "test-123",
            "role": "user",
            "content": "Hello",
            "timestamp": "2026-01-17T10:00:00Z"
        })
        
        result = handle(req, None)
        
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "success"
        assert "llm_response" in body
    
    @patch('handler.init_redis_client')
    def test_handle_valid_assistant_message(self, mock_redis):
        mock_client = MagicMock()
        mock_client.llen.return_value = 5
        mock_client.get.return_value = "100"
        mock_client.hgetall.return_value = {}
        mock_redis.return_value = mock_client
        
        req = json.dumps({
            "session_id": "test-123",
            "role": "assistant",
            "content": "Hello!",
            "timestamp": "2026-01-17T10:00:00Z"
        })
        
        result = handle(req, None)
        
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "success"
        assert "llm_response" not in body  # Assistant messages don't trigger LLM
    
    def test_handle_invalid_json(self):
        result = handle("not valid json", None)
        assert result["statusCode"] == 400
    
    def test_handle_missing_field(self):
        req = json.dumps({"session_id": "test-123"})
        result = handle(req, None)
        assert result["statusCode"] == 400
    
    @patch('handler.init_redis_client')
    @patch('handler.init_kafka_producer')
    def test_handle_message_from_query_embedding_retrieval(self, mock_kafka, mock_redis):
        """Test that conversation-manager accepts messages from query-embedding-retrieval format."""
        mock_client = MagicMock()
        mock_client.llen.return_value = 5
        mock_client.get.return_value = "100"
        mock_client.hgetall.return_value = {}
        mock_redis.return_value = mock_client
        mock_kafka.return_value = None
        
        # Simulate the format sent by query-embedding-retrieval
        req = json.dumps({
            "session_id": "test-123",
            "role": "user",
            "content": "What is machine learning?",
            "timestamp": "2026-01-17T10:00:00Z"
            # Note: no metadata field, which is optional
        })
        
        result = handle(req, None)
        
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "success"
        assert body["session_id"] == "test-123"
    
    @patch('handler.init_redis_client')
    @patch('handler.init_kafka_producer')
    def test_handle_assistant_message_from_query_embedding_retrieval(self, mock_kafka, mock_redis):
        """Test that conversation-manager accepts assistant messages from query-embedding-retrieval."""
        mock_client = MagicMock()
        mock_client.llen.return_value = 5
        mock_client.get.return_value = "100"
        mock_client.hgetall.return_value = {}
        mock_redis.return_value = mock_client
        mock_kafka.return_value = None
        
        # Assistant message format from query-embedding-retrieval
        req = json.dumps({
            "session_id": "test-123",
            "role": "assistant",
            "content": "Machine learning is a subset of AI.",
            "timestamp": "2026-01-17T10:00:01Z"
        })
        
        result = handle(req, None)
        
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "success"
        assert "llm_response" not in body  # Assistant messages don't trigger LLM


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
