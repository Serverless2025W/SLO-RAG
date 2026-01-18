"""
Unit tests for query-embedding-retrieval handler
"""

import pytest
import json
import sys
import os
from unittest.mock import patch, MagicMock

# Load handler module directly from file to avoid import conflicts
import importlib.util

_handler_dir = os.path.dirname(os.path.abspath(__file__))
_handler_path = os.path.join(_handler_dir, "handler.py")

# Load handler module with a unique name
spec = importlib.util.spec_from_file_location("query_embedding_retrieval_handler", _handler_path)
handler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler_module)

# Import functions from the loaded module
parse_input = handler_module.parse_input
format_prompt = handler_module.format_prompt
format_results = handler_module.format_results
store_message_via_conversation_manager = handler_module.store_message_via_conversation_manager
store_conversation_async = handler_module.store_conversation_async
handle = handler_module.handle


class TestParseInput:
    """Tests for parse_input function."""
    
    def test_parse_json_string(self):
        req = json.dumps({"query": "test query", "session_id": "test-123"})
        query, session_id = parse_input(req)
        assert query == "test query"
        assert session_id == "test-123"
    
    def test_parse_dict(self):
        req = {"query": "test query", "session_id": "test-123"}
        query, session_id = parse_input(req)
        assert query == "test query"
        assert session_id == "test-123"
    
    def test_parse_bytes(self):
        req = b'{"query": "test query", "session_id": "test-123"}'
        query, session_id = parse_input(req)
        assert query == "test query"
        assert session_id == "test-123"
    
    def test_parse_no_session_id(self):
        req = json.dumps({"query": "test query"})
        query, session_id = parse_input(req)
        assert query == "test query"
        assert session_id is None
    
    def test_parse_empty_query(self):
        req = json.dumps({"query": "", "session_id": "test-123"})
        query, session_id = parse_input(req)
        assert query == ""
        assert session_id == "test-123"


class TestFormatPrompt:
    """Tests for format_prompt function."""
    
    def test_format_with_results(self):
        query = "What is this?"
        results = [
            {"text": "Context 1"},
            {"text": "Context 2"}
        ]
        prompt = format_prompt(query, results)
        assert "Context 1" in prompt
        assert "Context 2" in prompt
        assert query in prompt
    
    def test_format_no_results(self):
        query = "What is this?"
        results = []
        prompt = format_prompt(query, results)
        assert "No relevant context found" in prompt
        assert query in prompt


class TestFormatResults:
    """Tests for format_results function."""
    
    def test_format_single_result(self):
        mock_result = MagicMock()
        mock_result.score = 0.95
        mock_result.payload = {
            "text": "Sample text",
            "filename": "doc.pdf",
            "chunk_index": 0
        }
        
        formatted = format_results([mock_result])
        assert len(formatted) == 1
        assert formatted[0]["score"] == 0.95
        assert formatted[0]["text"] == "Sample text"
        assert formatted[0]["filename"] == "doc.pdf"
        assert formatted[0]["chunk_index"] == 0
    
    def test_format_multiple_results(self):
        mock_results = []
        for i in range(3):
            mock_result = MagicMock()
            mock_result.score = 0.9 - i * 0.1
            mock_result.payload = {
                "text": f"Text {i}",
                "filename": f"doc{i}.pdf",
                "chunk_index": i
            }
            mock_results.append(mock_result)
        
        formatted = format_results(mock_results)
        assert len(formatted) == 3
        assert formatted[0]["score"] == 0.9
        assert formatted[2]["chunk_index"] == 2


class TestStoreMessageViaConversationManager:
    """Tests for store_message_via_conversation_manager function."""
    
    @patch.object(handler_module, 'get_kafka_producer')
    def test_store_message_success(self, mock_get_producer):
        mock_future = MagicMock()
        mock_future.get.return_value = None  # Success
        
        mock_producer = MagicMock()
        mock_producer.send.return_value = mock_future
        mock_get_producer.return_value = mock_producer
        
        result = store_message_via_conversation_manager("test-123", "user", "Hello")
        
        assert result is True
        mock_producer.send.assert_called_once()
        call_args = mock_producer.send.call_args
        # Check topic
        assert call_args[0][0] == handler_module.CONVERSATION_EVENTS_TOPIC
        # Check message data
        message_data = call_args[0][1]
        assert message_data["session_id"] == "test-123"
        assert message_data["role"] == "user"
        assert message_data["content"] == "Hello"
        assert "timestamp" in message_data
    
    @patch.object(handler_module, 'get_kafka_producer')
    def test_store_message_failure(self, mock_get_producer):
        # Simulate producer unavailable
        mock_get_producer.return_value = None
        
        result = store_message_via_conversation_manager("test-123", "user", "Hello")
        
        assert result is False
    
    @patch.object(handler_module, 'get_kafka_producer')
    def test_store_message_exception(self, mock_get_producer):
        mock_future = MagicMock()
        mock_future.get.side_effect = Exception("Kafka error")
        
        mock_producer = MagicMock()
        mock_producer.send.return_value = mock_future
        mock_get_producer.return_value = mock_producer
        
        result = store_message_via_conversation_manager("test-123", "user", "Hello")
        
        assert result is False
    
    @patch.object(handler_module, 'get_kafka_producer')
    def test_store_assistant_message(self, mock_get_producer):
        mock_future = MagicMock()
        mock_future.get.return_value = None
        
        mock_producer = MagicMock()
        mock_producer.send.return_value = mock_future
        mock_get_producer.return_value = mock_producer
        
        result = store_message_via_conversation_manager("test-123", "assistant", "Response")
        
        assert result is True
        call_args = mock_producer.send.call_args
        message_data = call_args[0][1]
        assert message_data["role"] == "assistant"


class TestStoreConversationAsync:
    """Tests for store_conversation_async function."""
    
    @patch.object(handler_module, 'store_message_via_conversation_manager')
    def test_store_both_messages(self, mock_store):
        # Store conversation
        store_conversation_async("test-123", "Hello", "Response")
        
        # Wait a bit for async thread
        import time
        time.sleep(0.1)
        
        # Should be called twice (user + assistant)
        assert mock_store.call_count == 2
        calls = [call[0] for call in mock_store.call_args_list]
        
        # First call should be user message
        assert calls[0][0] == "test-123"
        assert calls[0][1] == "user"
        assert calls[0][2] == "Hello"
        
        # Second call should be assistant message
        assert calls[1][0] == "test-123"
        assert calls[1][1] == "assistant"
        assert calls[1][2] == "Response"


class TestHandle:
    """Tests for main handle function."""
    
    @patch.object(handler_module, 'generate_embedding')
    @patch.object(handler_module, 'search_similar')
    @patch.object(handler_module, 'call_router')
    @patch.object(handler_module, 'store_conversation_async')
    def test_handle_with_session_id(self, mock_store, mock_router, mock_search, mock_embed):
        # Setup mocks
        mock_embed.return_value = [0.1] * 384
        mock_search.return_value = []
        mock_router.return_value = ("Answer text", "local-inference")
        
        req = json.dumps({
            "query": "What is this?",
            "session_id": "test-123"
        })
        
        result = handle(req, None)
        
        result_data = json.loads(result)
        assert "answer" in result_data
        assert "model" in result_data
        assert "sources" in result_data
        assert result_data["answer"] == "Answer text"
        
        # Should store conversation if session_id provided
        mock_store.assert_called_once_with("test-123", "What is this?", "Answer text")
    
    @patch.object(handler_module, 'generate_embedding')
    @patch.object(handler_module, 'search_similar')
    @patch.object(handler_module, 'call_router')
    @patch.object(handler_module, 'store_conversation_async')
    def test_handle_without_session_id(self, mock_store, mock_router, mock_search, mock_embed):
        # Setup mocks
        mock_embed.return_value = [0.1] * 384
        mock_search.return_value = []
        mock_router.return_value = ("Answer text", "local-inference")
        
        req = json.dumps({
            "query": "What is this?"
        })
        
        result = handle(req, None)
        
        result_data = json.loads(result)
        assert "answer" in result_data
        
        # Should NOT store conversation if no session_id
        mock_store.assert_not_called()
    
    def test_handle_no_query(self):
        req = json.dumps({})
        result = handle(req, None)
        
        result_data = json.loads(result)
        assert "error" in result_data
        assert "No query provided" in result_data["error"]
    
    def test_handle_invalid_json(self):
        req = "not valid json"
        result = handle(req, None)
        
        result_data = json.loads(result)
        assert "error" in result_data
    
    @patch.object(handler_module, 'generate_embedding')
    def test_handle_embedding_error(self, mock_embed):
        mock_embed.side_effect = Exception("Embedding error")
        
        req = json.dumps({"query": "test"})
        result = handle(req, None)
        
        result_data = json.loads(result)
        assert "error" in result_data
        assert "Embedding generation error" in result_data["error"]
    
    @patch.object(handler_module, 'generate_embedding')
    @patch.object(handler_module, 'search_similar')
    @patch.object(handler_module, 'call_router')
    def test_handle_router_error(self, mock_router, mock_search, mock_embed):
        mock_embed.return_value = [0.1] * 384
        mock_search.return_value = []
        mock_router.side_effect = Exception("Router error")
        
        req = json.dumps({"query": "test"})
        result = handle(req, None)
        
        result_data = json.loads(result)
        assert "error" in result_data
        assert "Inference error" in result_data["error"]
    
    @patch.object(handler_module, 'generate_embedding')
    @patch.object(handler_module, 'search_similar')
    @patch.object(handler_module, 'call_router')
    def test_handle_with_sources(self, mock_router, mock_search, mock_embed):
        # Setup mocks
        mock_embed.return_value = [0.1] * 384
        
        # Create mock search results
        mock_result = MagicMock()
        mock_result.score = 0.95
        mock_result.payload = {
            "text": "Sample text",
            "filename": "doc.pdf",
            "chunk_index": 0
        }
        mock_search.return_value = [mock_result]
        
        mock_router.return_value = ("Answer text", "remote-inference")
        
        req = json.dumps({"query": "test"})
        result = handle(req, None)
        
        result_data = json.loads(result)
        assert "sources" in result_data
        assert len(result_data["sources"]) == 1
        assert result_data["sources"][0]["filename"] == "doc.pdf"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
