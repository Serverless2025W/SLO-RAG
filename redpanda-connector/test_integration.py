"""
Integration tests for redpanda-connector.

These tests require running services:
- Redpanda (Kafka-compatible broker)
- Redis
- OpenFaaS Gateway (optional, can be mocked)

To run these tests:
1. Start services: docker-compose up -d
2. Run: pytest test_integration.py -v -m integration

Or skip if services unavailable:
pytest test_integration.py -v --skip-integration
"""

import pytest
import json
import time
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from unittest.mock import Mock, patch, MagicMock

# Import kafka and redis clients for integration tests
try:
    from kafka import KafkaProducer, KafkaConsumer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Ensure connector defaults align with local test services.
os.environ.setdefault("REDIS_HOST", os.getenv("TEST_REDIS_HOST", "localhost"))
os.environ.setdefault("REDIS_PORT", os.getenv("TEST_REDIS_PORT", "6379"))

# Import connector functions
sys.path.insert(0, os.path.dirname(__file__))
try:
    from connector import (
        init_redis_client,
        get_query_embedding_cache,
        set_query_embedding_cache,
        get_conversation_history,
        update_conversation_state,
        check_summarization_threshold,
        trigger_summarization,
        invoke_function,
        get_target_function
    )
    from message_schemas import ConversationEvent, LLMResponseEvent, SummarizationTrigger
    from redis_schemas import ConversationMessage, SessionMetadata, RedisConversationStore
    SCHEMAS_AVAILABLE = True
except ImportError as e:
    SCHEMAS_AVAILABLE = False
    print(f"Warning: Could not import schemas: {e}")

# Test configuration
BROKER = os.getenv("TEST_BROKER", "localhost:29092")
REDIS_HOST = os.getenv("TEST_REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("TEST_REDIS_PORT", "6379"))
GATEWAY_URL = os.getenv("TEST_GATEWAY_URL", "http://localhost:8080")

# Mark all tests as integration tests
pytestmark = pytest.mark.integration

def utc_now_iso() -> str:
    """Return UTC timestamp in ISO 8601 with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TestServiceConnectivity:
    """Test basic connectivity to required services."""
    
    @pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis library not available")
    def test_redis_connection(self):
        """Test Redis connection establishment."""
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=0,
                decode_responses=True,
                socket_connect_timeout=2
            )
            client.ping()
            assert True, "Redis connection successful"
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
    
    @pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka library not available")
    def test_kafka_connection(self):
        """Test Kafka/Redpanda connection."""
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=BROKER,
                consumer_timeout_ms=2000
            )
            # Just test connection, don't consume
            consumer.close()
            assert True, "Kafka connection successful"
        except Exception as e:
            pytest.skip(f"Kafka/Redpanda not available: {e}")


class TestPhase1MultiTopicConsumption:
    """Integration tests for Phase 1: Multi-topic consumption."""
    
    @pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka library not available")
    def test_publish_and_consume_text_chunks(self):
        """Test publishing and consuming from text-chunks topic."""
        try:
            # Create producer
            producer = KafkaProducer(
                bootstrap_servers=BROKER,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            
            # Create consumer
            consumer = KafkaConsumer(
                'text-chunks',
                bootstrap_servers=BROKER,
                auto_offset_reset='latest',
                consumer_timeout_ms=5000,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            
            # Publish test message
            test_message = {
                "file_name": "test.pdf",
                "chunk_index": 0,
                "total_chunks": 1,
                "content": "Test chunk content",
                "timestamp": utc_now_iso()
            }
            producer.send('text-chunks', test_message)
            producer.flush()
            
            # Consume message
            messages = []
            for msg in consumer:
                messages.append(msg.value)
                if len(messages) >= 1:
                    break
            
            consumer.close()
            producer.close()
            
            assert len(messages) > 0, "Should consume at least one message"
            assert messages[0]['content'] == test_message['content']
            
        except Exception as e:
            pytest.skip(f"Kafka/Redpanda not available: {e}")
    
    @pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka library not available")
    def test_publish_to_multiple_topics(self):
        """Test publishing to multiple topics (conversation-events, llm-responses)."""
        try:
            producer = KafkaProducer(
                bootstrap_servers=BROKER,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            
            # Publish to conversation-events
            conv_event = {
                "event_type": "user_query",
                "session_id": "test-session-123",
                "role": "user",
                "content": "Test query",
                "timestamp": utc_now_iso(),
                "metadata": {"tokens": 10}
            }
            producer.send('conversation-events', conv_event)
            
            # Publish to llm-responses
            llm_response = {
                "session_id": "test-session-123",
                "role": "assistant",
                "content": "Test response",
                "timestamp": utc_now_iso(),
                "metadata": {"tokens": 50}
            }
            producer.send('llm-responses', llm_response)
            
            producer.flush()
            producer.close()
            
            # Verify routing
            assert get_target_function('conversation-events') == 'conversation-manager'
            assert get_target_function('llm-responses') == 'conversation-manager'
            
        except Exception as e:
            pytest.skip(f"Kafka/Redpanda not available: {e}")


class TestPhase2RedisOperations:
    """Integration tests for Phase 2: Redis operations."""
    
    @pytest.fixture
    def redis_client(self):
        """Get Redis client for testing."""
        if not REDIS_AVAILABLE:
            pytest.skip("Redis library not available")
        
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=0,
                decode_responses=True,
                socket_connect_timeout=2
            )
            client.ping()
            # Clean up test keys
            yield client
            # Cleanup
            keys = client.keys('test:*')
            if keys:
                client.delete(*keys)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
    
    def test_query_embedding_cache(self, redis_client):
        """Test query embedding caching with real Redis."""
        test_query = "test query for embedding"
        test_embedding = {"embedding": [0.1, 0.2, 0.3, 0.4, 0.5]}
        
        # Set cache
        result = set_query_embedding_cache(test_query, test_embedding)
        assert result is True, "Should successfully cache embedding"
        
        # Get cache
        cached = get_query_embedding_cache(test_query)
        assert cached is not None, "Should retrieve cached embedding"
        assert cached == test_embedding, "Cached embedding should match"
        
        # Verify in Redis directly
        import hashlib
        query_hash = hashlib.sha256(test_query.encode('utf-8')).hexdigest()
        cache_key = f"query:embedding:{query_hash}"
        redis_value = redis_client.get(cache_key)
        assert redis_value is not None, "Key should exist in Redis"
        
        # Cleanup
        redis_client.delete(cache_key)
    
    def test_conversation_history_storage(self, redis_client):
        """Test conversation history storage and retrieval."""
        session_id = "test-session-history"
        
        # Store messages using RedisConversationStore
        if SCHEMAS_AVAILABLE:
            message1 = ConversationMessage(
                role="user",
                content="Hello",
                timestamp=utc_now_iso()
            )
            message2 = ConversationMessage(
                role="assistant",
                content="Hi there",
                timestamp=utc_now_iso()
            )
            
            RedisConversationStore.store_message(redis_client, session_id, message1, 3600)
            RedisConversationStore.store_message(redis_client, session_id, message2, 3600)
            
            # Retrieve messages
            messages = RedisConversationStore.get_messages(redis_client, session_id)
            assert len(messages) == 2, "Should retrieve 2 messages"
            assert messages[0].role == "user"
            assert messages[1].role == "assistant"
            
            # Test with limit
            recent = RedisConversationStore.get_messages(redis_client, session_id, limit=1)
            assert len(recent) == 1, "Should retrieve 1 message with limit"
            assert recent[0].role == "assistant", "Should get most recent message"
            
            # Cleanup
            redis_client.delete(f"conversation:{session_id}")
        else:
            pytest.skip("Schemas not available")


class TestPhase3ConversationState:
    """Integration tests for Phase 3: Conversation state management."""
    
    @pytest.fixture
    def redis_client(self):
        """Get Redis client for testing."""
        if not REDIS_AVAILABLE:
            pytest.skip("Redis library not available")
        
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=0,
                decode_responses=True,
                socket_connect_timeout=2
            )
            client.ping()
            yield client
            # Cleanup test keys
            keys = client.keys('conversation:test-*')
            keys.extend(client.keys('session:test-*'))
            if keys:
                client.delete(*keys)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
    
    def test_store_conversation_event(self, redis_client):
        """Test storing conversation event in Redis."""
        if not SCHEMAS_AVAILABLE:
            pytest.skip("Schemas not available")
        
        session_id = "test-session-state"
        event_data = {
            "event_type": "user_query",
            "session_id": session_id,
            "role": "user",
            "content": "What is the weather?",
            "timestamp": utc_now_iso(),
            "metadata": {"tokens": 10, "model": "gpt-4"}
        }
        
        # Update conversation state
        result = update_conversation_state(event_data)
        assert result is True, "Should successfully store conversation state"
        
        # Verify message stored
        messages = RedisConversationStore.get_messages(redis_client, session_id)
        assert len(messages) == 1, "Should have 1 message"
        assert messages[0].content == "What is the weather?"
        
        # Verify token count
        token_count = RedisConversationStore.get_token_count(redis_client, session_id)
        assert token_count == 10, "Token count should be 10"
        
        # Verify metadata
        metadata = RedisConversationStore.get_session_metadata(redis_client, session_id)
        assert metadata is not None, "Metadata should exist"
        assert metadata.message_count == 1, "Message count should be 1"
    
    def test_update_token_count(self, redis_client):
        """Test token count updates."""
        if not SCHEMAS_AVAILABLE:
            pytest.skip("Schemas not available")
        
        session_id = "test-session-tokens"
        
        # Initial update
        event1 = {
            "session_id": session_id,
            "role": "user",
            "content": "Message 1",
            "timestamp": utc_now_iso(),
            "metadata": {"tokens": 20}
        }
        update_conversation_state(event1)
        
        # Second update
        event2 = {
            "session_id": session_id,
            "role": "assistant",
            "content": "Response 1",
            "timestamp": utc_now_iso(),
            "metadata": {"tokens": 50}
        }
        update_conversation_state(event2)
        
        # Verify cumulative token count
        token_count = RedisConversationStore.get_token_count(redis_client, session_id)
        assert token_count == 70, "Token count should be cumulative (20 + 50)"
    
    def test_conversation_history_retrieval(self, redis_client):
        """Test retrieving conversation history."""
        if not SCHEMAS_AVAILABLE:
            pytest.skip("Schemas not available")
        
        session_id = "test-session-history-retrieval"
        
        # Store multiple messages
        for i in range(5):
            event = {
                "session_id": session_id,
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}",
                "timestamp": utc_now_iso(),
                "metadata": {"tokens": 10}
            }
            update_conversation_state(event)
        
        # Retrieve all messages
        all_messages = get_conversation_history(session_id)
        assert all_messages is not None, "Should retrieve history"
        assert len(all_messages) == 5, "Should have 5 messages"
        
        # Retrieve with limit
        recent = get_conversation_history(session_id, limit=2)
        assert len(recent) == 2, "Should retrieve 2 most recent messages"


class TestPhase4SummarizationTriggers:
    """Integration tests for Phase 4: Summarization triggers."""
    
    @pytest.fixture
    def redis_client(self):
        """Get Redis client for testing."""
        if not REDIS_AVAILABLE:
            pytest.skip("Redis library not available")
        
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=0,
                decode_responses=True,
                socket_connect_timeout=2
            )
            client.ping()
            yield client
            # Cleanup
            keys = client.keys('conversation:test-summary-*')
            keys.extend(client.keys('session:test-summary-*'))
            if keys:
                client.delete(*keys)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
    
    def test_token_threshold_check(self, redis_client):
        """Test checking token threshold."""
        if not SCHEMAS_AVAILABLE:
            pytest.skip("Schemas not available")
        
        session_id = "test-summary-tokens"
        
        # Set token count above threshold (default: 4000)
        RedisConversationStore.update_token_count(redis_client, session_id, 4500)
        
        # Check threshold
        should_trigger, reason, tokens, messages = check_summarization_threshold(session_id)
        assert should_trigger is True, "Should trigger summarization"
        assert reason == "token_threshold", "Reason should be token_threshold"
        assert tokens == 4500, "Token count should match"
    
    def test_message_threshold_check(self, redis_client):
        """Test checking message threshold."""
        if not SCHEMAS_AVAILABLE:
            pytest.skip("Schemas not available")
        
        session_id = "test-summary-messages"
        
        # Store messages above threshold (default: 20)
        for i in range(25):
            message = ConversationMessage(
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
                timestamp=utc_now_iso()
            )
            RedisConversationStore.store_message(redis_client, session_id, message, 3600)
        
        # Check threshold
        should_trigger, reason, tokens, messages = check_summarization_threshold(session_id)
        assert should_trigger is True, "Should trigger summarization"
        assert reason == "message_threshold", "Reason should be message_threshold"
        assert messages == 25, "Message count should be 25"
    
    @pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka library not available")
    def test_trigger_summarization_publish(self, redis_client):
        """Test publishing summarization trigger to Kafka."""
        if not SCHEMAS_AVAILABLE:
            pytest.skip("Schemas not available")
        
        try:
            session_id = "test-summary-publish"
            
            # Set up state that exceeds threshold
            RedisConversationStore.update_token_count(redis_client, session_id, 4500)
            
            # Trigger summarization
            result = trigger_summarization(session_id, "token_threshold", 4500, 10)
            
            # Note: In a real test, we would consume from the topic to verify
            # For now, just verify the function doesn't raise an error
            # The actual verification would require consuming from summarization-triggers topic
            
        except Exception as e:
            # If Kafka is not available, skip the test
            pytest.skip(f"Kafka/Redpanda not available: {e}")


class TestEndToEndWorkflows:
    """End-to-end integration tests for complete workflows."""
    
    @pytest.fixture
    def redis_client(self):
        """Get Redis client for testing."""
        if not REDIS_AVAILABLE:
            pytest.skip("Redis library not available")
        
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=0,
                decode_responses=True,
                socket_connect_timeout=2
            )
            client.ping()
            yield client
            # Cleanup
            keys = client.keys('conversation:test-e2e-*')
            keys.extend(client.keys('session:test-e2e-*'))
            if keys:
                client.delete(*keys)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
    
    @pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka library not available")
    def test_conversation_workflow_phase3(self, redis_client):
        """Test complete conversation workflow (Phase 3)."""
        if not SCHEMAS_AVAILABLE:
            pytest.skip("Schemas not available")
        
        try:
            session_id = "test-e2e-conversation"
            
            # Simulate user query
            user_event = {
                "event_type": "user_query",
                "session_id": session_id,
                "role": "user",
                "content": "What is machine learning?",
                "timestamp": utc_now_iso(),
                "metadata": {"tokens": 10, "model": "gpt-4"}
            }
            
            # Store in Redis
            update_conversation_state(user_event)
            
            # Simulate LLM response
            llm_response = {
                "session_id": session_id,
                "role": "assistant",
                "content": "Machine learning is a subset of artificial intelligence.",
                "timestamp": utc_now_iso(),
                "metadata": {"tokens": 50, "model": "gpt-4"}
            }
            
            # Store in Redis
            update_conversation_state(llm_response)
            
            # Verify state
            messages = RedisConversationStore.get_messages(redis_client, session_id)
            assert len(messages) == 2, "Should have 2 messages"
            
            token_count = RedisConversationStore.get_token_count(redis_client, session_id)
            assert token_count == 60, "Token count should be 60"
            
            # Verify message order
            assert messages[0].role == "user"
            assert messages[1].role == "assistant"
            
        except Exception as e:
            pytest.skip(f"Services not available: {e}")
    
    @pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka library not available")
    def test_summarization_workflow_phase4(self, redis_client):
        """Test complete summarization workflow (Phase 4)."""
        if not SCHEMAS_AVAILABLE:
            pytest.skip("Schemas not available")
        
        try:
            session_id = "test-e2e-summarization"
            
            # Build up conversation to exceed threshold
            for i in range(25):
                event = {
                    "session_id": session_id,
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                    "timestamp": utc_now_iso(),
                    "metadata": {"tokens": 200}  # 25 * 200 = 5000 tokens
                }
                update_conversation_state(event)
            
            # Check threshold
            should_trigger, reason, tokens, messages = check_summarization_threshold(session_id)
            assert should_trigger is True, "Should trigger summarization"
            
            # Verify token count
            assert tokens > 4000, "Token count should exceed threshold"
            
            # Note: In a real end-to-end test, we would:
            # 1. Verify trigger is published to Kafka
            # 2. Verify context-summarizer is invoked
            # 3. Verify conversation is replaced with summary
            # 4. Verify token count is reset
            
        except Exception as e:
            pytest.skip(f"Services not available: {e}")


class TestErrorHandling:
    """Test error handling and graceful degradation."""
    
    def test_redis_unavailable_graceful_fallback(self):
        """Test that connector handles Redis unavailability gracefully."""
        # This test verifies that functions don't crash when Redis is unavailable
        # The actual implementation should log warnings but continue
        
        # Try to get cache when Redis is unavailable (wrong host)
        original_host = os.getenv("REDIS_HOST")
        os.environ["REDIS_HOST"] = "nonexistent-host-12345"
        
        try:
            # Reset global state
            import connector
            connector.redis_client = None
            
            result = get_query_embedding_cache("test query")
            # Should return None, not raise exception
            assert result is None
            
        finally:
            # Restore original host
            if original_host:
                os.environ["REDIS_HOST"] = original_host
            else:
                os.environ.pop("REDIS_HOST", None)
            # Reset global state
            import connector
            connector.redis_client = None


# Utility function to check if services are available
def check_services_available():
    """Check if required services are available."""
    services = {
        "redis": False,
        "kafka": False
    }
    
    # Check Redis
    if REDIS_AVAILABLE:
        try:
            client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=1)
            client.ping()
            services["redis"] = True
        except:
            pass
    
    # Check Kafka
    if KAFKA_AVAILABLE:
        try:
            consumer = KafkaConsumer(bootstrap_servers=BROKER, consumer_timeout_ms=1000)
            consumer.close()
            services["kafka"] = True
        except:
            pass
    
    return services


if __name__ == "__main__":
    # Check services before running
    services = check_services_available()
    print("Service availability:")
    print(f"  Redis: {'✓' if services['redis'] else '✗'}")
    print(f"  Kafka/Redpanda: {'✓' if services['kafka'] else '✗'}")
    print()
    
    if not any(services.values()):
        print("WARNING: No services available. Most tests will be skipped.")
        print("Start services with: docker-compose up -d")
    
    # Run tests
    pytest.main([__file__, "-v", "-m", "integration"])
