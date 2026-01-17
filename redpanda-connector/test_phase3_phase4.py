"""
Tests for Phase 3 (Conversation State Management) and Phase 4 (Summarization Triggers).

These tests verify the connector's ability to:
- Store conversation messages in Redis
- Update token counts
- Manage session metadata
- Check thresholds and trigger summarization
- Handle summarization events
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from datetime import datetime

# Add the redpanda-connector directory to the path
sys.path.insert(0, os.path.dirname(__file__))

# Import schemas
from message_schemas import (
    ConversationEvent,
    LLMResponseEvent,
    SummarizationTrigger,
    ConversationEventMetadata
)
from redis_schemas import (
    ConversationMessage,
    SessionMetadata,
    RedisKeyPatterns,
    RedisConversationStore
)


class TestPhase3ConversationStateManagement:
    """Tests for Phase 3: Conversation State Management."""
    
    @patch('connector.init_redis_client')
    def test_store_conversation_event_message(self, mock_init_redis):
        """Test storing a conversation event message in Redis."""
        mock_client = Mock()
        mock_init_redis.return_value = mock_client
        
        # Create test event
        event = ConversationEvent(
            event_type="user_query",
            session_id="session-123",
            role="user",
            content="Hello, how are you?",
            timestamp="2026-01-12T20:00:00Z",
            metadata=ConversationEventMetadata(tokens=10, model="gpt-4")
        )
        
        # Test storing message
        message = ConversationMessage(
            role=event.role,
            content=event.content,
            timestamp=event.timestamp
        )
        RedisConversationStore.store_message(mock_client, event.session_id, message)
        
        # Verify Redis operations
        key = RedisKeyPatterns.conversation_history("session-123")
        mock_client.rpush.assert_called_once()
        mock_client.expire.assert_called_once_with(key, RedisConversationStore.CONVERSATION_TTL)
    
    @patch('connector.init_redis_client')
    def test_update_token_count(self, mock_init_redis):
        """Test updating token count for a session."""
        mock_client = Mock()
        mock_client.incrby.return_value = 150
        mock_init_redis.return_value = mock_client
        
        # Test token update
        new_count = RedisConversationStore.update_token_count(mock_client, "session-123", 150)
        
        assert new_count == 150
        key = RedisKeyPatterns.session_tokens("session-123")
        mock_client.incrby.assert_called_once_with(key, 150)
        mock_client.expire.assert_called_once_with(key, RedisConversationStore.CONVERSATION_TTL)
    
    @patch('connector.init_redis_client')
    def test_get_token_count(self, mock_init_redis):
        """Test retrieving token count."""
        mock_client = Mock()
        mock_client.get.return_value = "4500"
        mock_init_redis.return_value = mock_client
        
        count = RedisConversationStore.get_token_count(mock_client, "session-123")
        
        assert count == 4500
        key = RedisKeyPatterns.session_tokens("session-123")
        mock_client.get.assert_called_once_with(key)
    
    @patch('connector.init_redis_client')
    def test_get_token_count_not_set(self, mock_init_redis):
        """Test retrieving token count when not set."""
        mock_client = Mock()
        mock_client.get.return_value = None
        mock_init_redis.return_value = mock_client
        
        count = RedisConversationStore.get_token_count(mock_client, "session-123")
        
        assert count == 0
    
    @patch('connector.init_redis_client')
    def test_update_session_metadata(self, mock_init_redis):
        """Test updating session metadata."""
        mock_client = Mock()
        mock_init_redis.return_value = mock_client
        
        metadata = SessionMetadata(
            created_at="2026-01-12T19:00:00Z",
            last_activity="2026-01-12T20:00:00Z",
            message_count=10,
            token_count=1500
        )
        
        RedisConversationStore.update_session_metadata(mock_client, "session-123", metadata)
        
        key = RedisKeyPatterns.session_metadata("session-123")
        mock_client.hset.assert_called_once()
        mock_client.expire.assert_called_once_with(key, RedisConversationStore.CONVERSATION_TTL)
    
    @patch('connector.init_redis_client')
    def test_get_messages_from_history(self, mock_init_redis):
        """Test retrieving messages from conversation history."""
        mock_client = Mock()
        mock_messages = [
            ConversationMessage(role="user", content="Hello", timestamp="2026-01-12T20:00:00Z").to_json(),
            ConversationMessage(role="assistant", content="Hi there", timestamp="2026-01-12T20:00:01Z").to_json()
        ]
        mock_client.lrange.return_value = mock_messages
        mock_init_redis.return_value = mock_client
        
        messages = RedisConversationStore.get_messages(mock_client, "session-123", limit=10)
        
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        key = RedisKeyPatterns.conversation_history("session-123")
        mock_client.lrange.assert_called_once_with(key, -10, -1)
    
    @patch('connector.init_redis_client')
    def test_get_message_count(self, mock_init_redis):
        """Test getting message count."""
        mock_client = Mock()
        mock_client.llen.return_value = 15
        mock_init_redis.return_value = mock_client
        
        count = RedisConversationStore.get_message_count(mock_client, "session-123")
        
        assert count == 15
        key = RedisKeyPatterns.conversation_history("session-123")
        mock_client.llen.assert_called_once_with(key)


class TestPhase4SummarizationTriggers:
    """Tests for Phase 4: Summarization Triggers."""
    
    @patch('connector.init_redis_client')
    def test_check_token_threshold_exceeded(self, mock_init_redis):
        """Test checking if token threshold is exceeded."""
        mock_client = Mock()
        mock_client.get.return_value = "4500"  # Exceeds threshold of 4000
        mock_client.llen.return_value = 20
        mock_init_redis.return_value = mock_client
        
        # Test threshold check
        token_count = RedisConversationStore.get_token_count(mock_client, "session-123")
        message_count = RedisConversationStore.get_message_count(mock_client, "session-123")
        
        token_threshold = 4000
        message_threshold = 20
        
        token_exceeded = token_count > token_threshold
        message_exceeded = message_count > message_threshold
        
        assert token_exceeded is True
        assert message_exceeded is False
    
    @patch('connector.init_redis_client')
    def test_check_message_threshold_exceeded(self, mock_init_redis):
        """Test checking if message threshold is exceeded."""
        mock_client = Mock()
        mock_client.get.return_value = "3000"
        mock_client.llen.return_value = 25  # Exceeds threshold of 20
        mock_init_redis.return_value = mock_client
        
        token_count = RedisConversationStore.get_token_count(mock_client, "session-123")
        message_count = RedisConversationStore.get_message_count(mock_client, "session-123")
        
        token_threshold = 4000
        message_threshold = 20
        
        token_exceeded = token_count > token_threshold
        message_exceeded = message_count > message_threshold
        
        assert token_exceeded is False
        assert message_exceeded is True
    
    @patch('connector.init_redis_client')
    def test_check_threshold_not_exceeded(self, mock_init_redis):
        """Test checking thresholds when not exceeded."""
        mock_client = Mock()
        mock_client.get.return_value = "2000"
        mock_client.llen.return_value = 10
        mock_init_redis.return_value = mock_client
        
        token_count = RedisConversationStore.get_token_count(mock_client, "session-123")
        message_count = RedisConversationStore.get_message_count(mock_client, "session-123")
        
        token_threshold = 4000
        message_threshold = 20
        
        token_exceeded = token_count > token_threshold
        message_exceeded = message_count > message_threshold
        
        assert token_exceeded is False
        assert message_exceeded is False
    
    def test_create_summarization_trigger(self):
        """Test creating a summarization trigger message."""
        trigger = SummarizationTrigger(
            session_id="session-123",
            trigger_reason="token_threshold",
            current_tokens=4500,
            current_messages=25,
            threshold=4000
        )
        
        assert trigger.session_id == "session-123"
        assert trigger.trigger_reason == "token_threshold"
        assert trigger.current_tokens == 4500
        assert trigger.validate() is True
    
    @patch('connector.init_redis_client')
    def test_replace_conversation_with_summary(self, mock_init_redis):
        """Test replacing conversation history with summary."""
        mock_client = Mock()
        mock_init_redis.return_value = mock_client
        
        summary_message = ConversationMessage(
            role="system",
            content="Previous conversation summarized: User asked about weather, assistant responded.",
            timestamp="2026-01-12T20:30:00Z"
        )
        
        RedisConversationStore.replace_conversation_with_summary(
            mock_client, "session-123", summary_message
        )
        
        key = RedisKeyPatterns.conversation_history("session-123")
        mock_client.delete.assert_called_once_with(key)
        mock_client.rpush.assert_called_once()
        mock_client.expire.assert_called_once()
    
    @patch('connector.init_redis_client')
    def test_reset_session(self, mock_init_redis):
        """Test resetting session state."""
        mock_client = Mock()
        mock_init_redis.return_value = mock_client
        
        RedisConversationStore.reset_session(mock_client, "session-123")
        
        # Should delete conversation, tokens, and metadata keys
        assert mock_client.delete.call_count == 3


class TestMessageSchemas:
    """Tests for message schema validation."""
    
    def test_conversation_event_validation(self):
        """Test conversation event validation."""
        valid_event = ConversationEvent(
            event_type="user_query",
            session_id="session-123",
            role="user",
            content="Hello",
            timestamp="2026-01-12T20:00:00Z"
        )
        assert valid_event.validate() is True
        
        invalid_event = ConversationEvent(
            event_type="invalid_type",
            session_id="session-123",
            role="user",
            content="Hello",
            timestamp="2026-01-12T20:00:00Z"
        )
        assert invalid_event.validate() is False
    
    def test_llm_response_validation(self):
        """Test LLM response validation."""
        valid_response = LLMResponseEvent(
            session_id="session-123",
            role="assistant",
            content="Hi there",
            timestamp="2026-01-12T20:00:01Z"
        )
        assert valid_response.validate() is True
        
        invalid_response = LLMResponseEvent(
            session_id="session-123",
            role="user",  # Must be assistant
            content="Hi there",
            timestamp="2026-01-12T20:00:01Z"
        )
        assert invalid_response.validate() is False
    
    def test_summarization_trigger_validation(self):
        """Test summarization trigger validation."""
        valid_trigger = SummarizationTrigger(
            session_id="session-123",
            trigger_reason="token_threshold",
            current_tokens=4500,
            current_messages=25,
            threshold=4000
        )
        assert valid_trigger.validate() is True
        
        invalid_trigger = SummarizationTrigger(
            session_id="",
            trigger_reason="token_threshold",
            current_tokens=4500,
            current_messages=25,
            threshold=4000
        )
        assert invalid_trigger.validate() is False
    
    def test_message_serialization(self):
        """Test message serialization to/from JSON."""
        event = ConversationEvent(
            event_type="user_query",
            session_id="session-123",
            role="user",
            content="Hello",
            timestamp="2026-01-12T20:00:00Z",
            metadata=ConversationEventMetadata(tokens=10, model="gpt-4")
        )
        
        # Serialize
        event_dict = event.to_dict()
        assert event_dict["session_id"] == "session-123"
        assert event_dict["metadata"]["tokens"] == 10
        
        # Deserialize
        restored_event = ConversationEvent.from_dict(event_dict)
        assert restored_event.session_id == event.session_id
        assert restored_event.metadata.tokens == event.metadata.tokens


class TestRedisSchemaOperations:
    """Tests for Redis schema operations."""
    
    @patch('connector.init_redis_client')
    def test_session_metadata_serialization(self, mock_init_redis):
        """Test session metadata serialization."""
        mock_client = Mock()
        mock_init_redis.return_value = mock_client
        
        metadata = SessionMetadata(
            created_at="2026-01-12T19:00:00Z",
            last_activity="2026-01-12T20:00:00Z",
            message_count=10,
            token_count=1500
        )
        
        # Test to_redis_hash
        redis_hash = metadata.to_redis_hash()
        assert redis_hash["message_count"] == "10"
        assert redis_hash["token_count"] == "1500"
        
        # Test from_redis_hash
        restored = SessionMetadata.from_redis_hash(redis_hash)
        assert restored.message_count == 10
        assert restored.token_count == 1500
    
    def test_conversation_message_serialization(self):
        """Test conversation message JSON serialization."""
        message = ConversationMessage(
            role="user",
            content="Hello",
            timestamp="2026-01-12T20:00:00Z"
        )
        
        # Serialize
        json_str = message.to_json()
        assert "user" in json_str
        assert "Hello" in json_str
        
        # Deserialize
        restored = ConversationMessage.from_json(json_str)
        assert restored.role == message.role
        assert restored.content == message.content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
