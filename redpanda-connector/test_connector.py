import importlib.util
import json
import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock

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
    invoke_function = connector.invoke_function
    process_message = connector.process_message


class TestTopicRouting:
    """Unit tests for topic routing logic."""
    
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
        result = get_target_function("unknown-topic")
        assert result == "embedding-generation"  # Default from TARGET_FUNCTION env var


class TestMessageParsing:
    """Unit tests for message parsing and routing."""
    
    @patch('connector.invoke_function')
    def test_process_message_bytes(self, mock_invoke):
        """Test processing message with bytes value."""
        mock_message = Mock()
        mock_message.topic = "text-chunks"
        mock_message.value = b'{"text": "test content"}'
        
        mock_invoke.return_value = {"result": "success"}
        
        process_message(mock_message)
        mock_invoke.assert_called_once_with("embedding-generation", {"text": "test content"})
    
    @patch('connector.invoke_function')
    def test_process_message_string(self, mock_invoke):
        """Test processing message with string value."""
        mock_message = Mock()
        mock_message.topic = "conversation-events"
        mock_message.value = '{"session_id": "123", "content": "test"}'
        
        mock_invoke.return_value = {"result": "success"}
        
        process_message(mock_message)
        mock_invoke.assert_called_once_with(
            "conversation-manager", 
            {"session_id": "123", "content": "test"}
        )
    
    @patch('connector.invoke_function')
    def test_process_message_dict(self, mock_invoke):
        """Test processing message with dict value (already parsed)."""
        mock_message = Mock()
        mock_message.topic = "summarization-triggers"
        mock_message.value = {"session_id": "456", "trigger_reason": "token_threshold"}
        
        mock_invoke.return_value = {"summary": "test summary"}
        
        process_message(mock_message)
        mock_invoke.assert_called_once_with(
            "context-summarizer",
            {"session_id": "456", "trigger_reason": "token_threshold"}
        )
    
    @patch('connector.invoke_function')
    def test_process_message_invalid_json(self, mock_invoke):
        """Test processing message with invalid JSON."""
        mock_message = Mock()
        mock_message.topic = "text-chunks"
        mock_message.value = b'not valid json'
        
        # Should not raise, just log error
        process_message(mock_message)
        mock_invoke.assert_not_called()
    
    @patch('connector.invoke_function')
    def test_process_message_routes_correctly(self, mock_invoke):
        """Test that messages are routed to correct functions."""
        mock_invoke.return_value = {"result": "ok"}
        
        # Test each topic route
        test_cases = [
            ("text-chunks", "embedding-generation"),
            ("conversation-events", "conversation-manager"),
            ("llm-responses", "conversation-manager"),
            ("summarization-triggers", "context-summarizer"),
        ]
        
        for topic, expected_function in test_cases:
            mock_invoke.reset_mock()
            mock_message = Mock()
            mock_message.topic = topic
            mock_message.value = b'{"test": "data"}'
            
            process_message(mock_message)
            
            assert mock_invoke.call_args[0][0] == expected_function, \
                f"Topic {topic} should route to {expected_function}"


class TestFunctionInvocation:
    """Unit tests for function invocation."""
    
    @patch('requests.post')
    def test_invoke_function_success_json(self, mock_post):
        """Test successful function invocation with JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        mock_post.return_value = mock_response
        
        result = invoke_function("test-function", {"data": "test"})
        
        assert result == {"result": "success"}
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "test-function" in call_args[0][0]
        assert call_args[1]["json"] == {"data": "test"}
    
    @patch('requests.post')
    def test_invoke_function_success_text(self, mock_post):
        """Test successful function invocation with text response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "plain text response"
        mock_post.return_value = mock_response
        
        result = invoke_function("test-function", {"data": "test"})
        
        assert result == {"text": "plain text response"}
    
    @patch('requests.post')
    def test_invoke_function_failure(self, mock_post):
        """Test function invocation failure (non-200 status)."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        result = invoke_function("test-function", {"data": "test"})
        
        assert result is None
    
    @patch('requests.post')
    def test_invoke_function_exception(self, mock_post):
        """Test function invocation with connection exception."""
        mock_post.side_effect = Exception("Connection error")
        
        result = invoke_function("test-function", {"data": "test"})
        
        assert result is None
    
    @patch('requests.post')
    def test_invoke_function_timeout(self, mock_post):
        """Test function invocation with timeout."""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")
        
        result = invoke_function("test-function", {"data": "test"})
        
        assert result is None


class TestEndToEnd:
    """End-to-end tests for message processing flow."""
    
    @patch('requests.post')
    def test_full_message_flow_embedding(self, mock_post):
        """Test full flow: message received → function invoked → result returned."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        mock_post.return_value = mock_response
        
        mock_message = Mock()
        mock_message.topic = "text-chunks"
        mock_message.value = b'{"text": "document chunk", "chunk_id": "1"}'
        
        # Process should complete without error
        process_message(mock_message)
        
        # Verify function was called with correct data
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "embedding-generation" in call_args[0][0]
        assert call_args[1]["json"] == {"text": "document chunk", "chunk_id": "1"}
    
    @patch('requests.post')
    def test_full_message_flow_conversation(self, mock_post):
        """Test full flow for conversation events."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "stored", "message_id": "msg-1"}
        mock_post.return_value = mock_response
        
        mock_message = Mock()
        mock_message.topic = "conversation-events"
        mock_message.value = json.dumps({
            "session_id": "session-123",
            "role": "user",
            "content": "Hello, how are you?",
            "timestamp": "2026-01-17T10:00:00Z"
        }).encode()
        
        process_message(mock_message)
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "conversation-manager" in call_args[0][0]
    
    @patch('requests.post')
    def test_full_message_flow_summarization(self, mock_post):
        """Test full flow for summarization triggers."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "summary": "User discussed various topics...",
            "original_messages": 25,
            "original_tokens": 5000
        }
        mock_post.return_value = mock_response
        
        mock_message = Mock()
        mock_message.topic = "summarization-triggers"
        mock_message.value = json.dumps({
            "session_id": "session-456",
            "trigger_reason": "token_threshold",
            "current_tokens": 5000,
            "current_messages": 25
        }).encode()
        
        process_message(mock_message)
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "context-summarizer" in call_args[0][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
