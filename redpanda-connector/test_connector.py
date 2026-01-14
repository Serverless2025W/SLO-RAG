import importlib.util
import json
import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from typing import Any

def load_connector():
    connector_path = os.path.join(os.path.dirname(__file__), "connector.py")
    spec = importlib.util.spec_from_file_location("connector", connector_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["connector"] = module
    spec.loader.exec_module(module)
    return module

# Mock KafkaConsumer before importing connector
with patch('kafka.KafkaConsumer'):
    connector = load_connector()
    get_target_function = connector.get_target_function
    compute_query_hash = connector.compute_query_hash
    get_query_embedding_cache = connector.get_query_embedding_cache
    set_query_embedding_cache = connector.set_query_embedding_cache
    get_conversation_history = connector.get_conversation_history
    invoke_function = connector.invoke_function
    process_message = connector.process_message
    init_redis_client = connector.init_redis_client


class TestTopicRouting:
    """Unit tests for topic routing logic (Phase 1)."""
    
    def test_get_target_function_text_chunks(self):
        """Test routing for text-chunks topic."""
        assert get_target_function("text-chunks") == "embedding-generation"
    
    def test_get_target_function_conversation_events(self):
        """Test routing for conversation-events topic."""
        assert get_target_function("conversation-events") == "conversation-manager"
    
    def test_get_target_function_llm_responses(self):
        """Test routing for llm-responses topic."""
        assert get_target_function("llm-responses") == "conversation-manager"
    
    def test_get_target_function_summarization_triggers(self):
        """Test routing for summarization-triggers topic."""
        assert get_target_function("summarization-triggers") == "context-summarizer"
    
    def test_get_target_function_unknown_topic(self):
        """Test routing for unknown topic falls back to default."""
        # Should fall back to TARGET_FUNCTION env var (default: "embedding-generation")
        result = get_target_function("unknown-topic")
        assert result == "embedding-generation"  # Default from TARGET_FUNCTION env var


class TestQueryHash:
    """Unit tests for query hash computation."""
    
    def test_compute_query_hash_consistent(self):
        """Test that same query produces same hash."""
        query = "test query"
        hash1 = compute_query_hash(query)
        hash2 = compute_query_hash(query)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length
    
    def test_compute_query_hash_different_queries(self):
        """Test that different queries produce different hashes."""
        hash1 = compute_query_hash("query 1")
        hash2 = compute_query_hash("query 2")
        assert hash1 != hash2


class TestRedisOperations:
    """Unit tests for Redis operations (Phase 2) with mocked Redis."""
    
    @patch('connector.init_redis_client')
    def test_get_query_embedding_cache_hit(self, mock_init_redis):
        """Test cache hit for query embedding."""
        mock_client = Mock()
        mock_client.get.return_value = json.dumps({"embedding": [0.1, 0.2, 0.3]})
        mock_init_redis.return_value = mock_client
        
        result = get_query_embedding_cache("test query")
        assert result == {"embedding": [0.1, 0.2, 0.3]}
        mock_client.get.assert_called_once()
    
    @patch('connector.init_redis_client')
    def test_get_query_embedding_cache_miss(self, mock_init_redis):
        """Test cache miss for query embedding."""
        mock_client = Mock()
        mock_client.get.return_value = None
        mock_init_redis.return_value = mock_client
        
        result = get_query_embedding_cache("test query")
        assert result is None
        mock_client.get.assert_called_once()
    
    @patch('connector.init_redis_client')
    def test_get_query_embedding_cache_redis_unavailable(self, mock_init_redis):
        """Test fallback when Redis is unavailable."""
        mock_init_redis.return_value = None
        
        result = get_query_embedding_cache("test query")
        assert result is None
    
    @patch('connector.init_redis_client')
    def test_set_query_embedding_cache_success(self, mock_init_redis):
        """Test successful cache write."""
        mock_client = Mock()
        mock_client.setex.return_value = True
        mock_init_redis.return_value = mock_client
        
        embedding = {"embedding": [0.1, 0.2, 0.3]}
        result = set_query_embedding_cache("test query", embedding)
        assert result is True
        mock_client.setex.assert_called_once()
    
    @patch('connector.init_redis_client')
    def test_set_query_embedding_cache_redis_unavailable(self, mock_init_redis):
        """Test cache write when Redis is unavailable."""
        mock_init_redis.return_value = None
        
        embedding = {"embedding": [0.1, 0.2, 0.3]}
        result = set_query_embedding_cache("test query", embedding)
        assert result is False
    
    @patch('connector.init_redis_client')
    def test_get_conversation_history_with_limit(self, mock_init_redis):
        """Test retrieving conversation history with limit."""
        mock_client = Mock()
        mock_client.lrange.return_value = [
            json.dumps({"role": "user", "content": "hello", "timestamp": "2026-01-12T20:00:00Z"}),
            json.dumps({"role": "assistant", "content": "hi", "timestamp": "2026-01-12T20:00:01Z"})
        ]
        mock_init_redis.return_value = mock_client
        
        result = get_conversation_history("session-123", limit=10)
        assert result is not None
        assert len(result) == 2
        assert result[0]["role"] == "user"
        mock_client.lrange.assert_called_once_with("conversation:session-123", -10, -1)
    
    @patch('connector.init_redis_client')
    def test_get_conversation_history_no_limit(self, mock_init_redis):
        """Test retrieving conversation history without limit."""
        mock_client = Mock()
        mock_client.lrange.return_value = []
        mock_init_redis.return_value = mock_client
        
        result = get_conversation_history("session-123")
        assert result == []
        mock_client.lrange.assert_called_once_with("conversation:session-123", 0, -1)
    
    @patch('connector.init_redis_client')
    def test_get_conversation_history_redis_unavailable(self, mock_init_redis):
        """Test conversation history when Redis is unavailable."""
        mock_init_redis.return_value = None
        
        result = get_conversation_history("session-123")
        assert result is None


class TestMessageParsing:
    """Unit tests for message parsing."""
    
    def test_process_message_json_dict(self):
        """Test processing message with JSON dict."""
        mock_message = Mock()
        mock_message.topic = "text-chunks"
        mock_message.value = {"text": "test content"}
        
        with patch('connector.invoke_function') as mock_invoke:
            process_message(mock_message)
            mock_invoke.assert_called_once()
    
    def test_process_message_json_string(self):
        """Test processing message with JSON string."""
        mock_message = Mock()
        mock_message.topic = "conversation-events"
        mock_message.value = json.dumps({"session_id": "123", "content": "test"})
        
        with patch('connector.invoke_function') as mock_invoke:
            with patch('connector.get_conversation_history') as mock_history:
                process_message(mock_message)
                mock_invoke.assert_called_once()


class TestFunctionInvocation:
    """Unit tests for function invocation."""
    
    @patch('requests.post')
    def test_invoke_function_success(self, mock_post):
        """Test successful function invocation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        mock_response.headers = {"content-type": "application/json"}
        mock_post.return_value = mock_response
        
        result = invoke_function("test-function", {"data": "test"})
        assert result == {"result": "success"}
        mock_post.assert_called_once()
    
    @patch('requests.post')
    def test_invoke_function_failure(self, mock_post):
        """Test function invocation failure."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        result = invoke_function("test-function", {"data": "test"})
        assert result is None
    
    @patch('requests.post')
    def test_invoke_function_exception(self, mock_post):
        """Test function invocation with exception."""
        mock_post.side_effect = Exception("Connection error")
        
        result = invoke_function("test-function", {"data": "test"})
        assert result is None


class TestRedisInitialization:
    """Unit tests for Redis initialization."""
    
    @patch('redis.Redis')
    def test_init_redis_client_success(self, mock_redis_class):
        """Test successful Redis initialization."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client
        
        # Reset global state
        import connector
        connector.redis_client = None
        
        result = init_redis_client()
        assert result is not None
        mock_redis_class.assert_called_once()
        mock_client.ping.assert_called_once()
    
    @patch('redis.Redis')
    def test_init_redis_client_failure(self, mock_redis_class):
        """Test Redis initialization failure."""
        mock_client = Mock()
        mock_client.ping.side_effect = Exception("Connection failed")
        mock_redis_class.return_value = mock_client
        
        # Reset global state
        import connector
        connector.redis_client = None
        
        result = init_redis_client()
        assert result is None
    
    @patch('redis.Redis')
    def test_init_redis_client_connection_error(self, mock_redis_class):
        """Test Redis initialization with connection error."""
        mock_redis_class.side_effect = Exception("Cannot connect")
        
        # Reset global state
        import connector
        connector.redis_client = None
        
        result = init_redis_client()
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])