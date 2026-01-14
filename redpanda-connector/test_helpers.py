"""
Helper utilities for integration tests.

These utilities help with:
- Creating test data
- Verifying service states
- Checking logs
- Setting up test environments
"""

import json
import time
from datetime import datetime, timezone
def utc_now_iso() -> str:
    """Return UTC timestamp in ISO 8601 with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
from typing import Dict, Any, Optional, List
import os

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


class TestDataGenerator:
    """Generate test data for integration tests."""
    
    @staticmethod
    def create_conversation_event(session_id: str, role: str = "user", content: str = "Test message", tokens: int = 10) -> Dict[str, Any]:
        """Create a conversation event message."""
        return {
            "event_type": "user_query" if role == "user" else "llm_response",
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": utc_now_iso(),
            "metadata": {
                "tokens": tokens,
                "model": "gpt-4"
            }
        }
    
    @staticmethod
    def create_llm_response(session_id: str, content: str = "Test response", tokens: int = 50) -> Dict[str, Any]:
        """Create an LLM response message."""
        return {
            "session_id": session_id,
            "role": "assistant",
            "content": content,
            "timestamp": utc_now_iso(),
            "metadata": {
                "tokens": tokens,
                "model": "gpt-4"
            }
        }
    
    @staticmethod
    def create_text_chunk(file_name: str = "test.pdf", chunk_index: int = 0, content: str = "Test chunk") -> Dict[str, Any]:
        """Create a text chunk message."""
        return {
            "file_name": file_name,
            "bucket": "documents",
            "chunk_index": chunk_index,
            "total_chunks": 1,
            "content": content,
            "timestamp": utc_now_iso()
        }
    
    @staticmethod
    def create_summarization_trigger(session_id: str, reason: str = "token_threshold", tokens: int = 4500, messages: int = 25) -> Dict[str, Any]:
        """Create a summarization trigger message."""
        return {
            "session_id": session_id,
            "trigger_reason": reason,
            "current_tokens": tokens,
            "current_messages": messages,
            "threshold": 4000 if reason == "token_threshold" else 20
        }


class KafkaTestHelper:
    """Helper for Kafka/Redpanda operations in tests."""
    
    def __init__(self, broker: str = "localhost:29092"):
        self.broker = broker
        self.producer: Optional[KafkaProducer] = None
    
    def get_producer(self) -> KafkaProducer:
        """Get or create Kafka producer."""
        if not KAFKA_AVAILABLE:
            raise ImportError("kafka-python not available")
        
        if self.producer is None:
            self.producer = KafkaProducer(
                bootstrap_servers=self.broker,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
        return self.producer
    
    def publish_message(self, topic: str, message: Dict[str, Any]) -> None:
        """Publish message to topic."""
        producer = self.get_producer()
        producer.send(topic, message)
        producer.flush()
    
    def consume_messages(self, topic: str, timeout_ms: int = 5000, max_messages: int = 10) -> List[Dict[str, Any]]:
        """Consume messages from topic."""
        if not KAFKA_AVAILABLE:
            raise ImportError("kafka-python not available")
        
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=self.broker,
            auto_offset_reset='latest',
            consumer_timeout_ms=timeout_ms,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        messages = []
        for msg in consumer:
            messages.append(msg.value)
            if len(messages) >= max_messages:
                break
        
        consumer.close()
        return messages
    
    def close(self):
        """Close producer."""
        if self.producer:
            self.producer.close()
            self.producer = None


class RedisTestHelper:
    """Helper for Redis operations in tests."""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.host = host
        self.port = port
        self.db = db
        self.client: Optional[redis.Redis] = None
    
    def get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if not REDIS_AVAILABLE:
            raise ImportError("redis not available")
        
        if self.client is None:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=2
            )
            self.client.ping()
        return self.client
    
    def cleanup_test_keys(self, pattern: str = "test:*"):
        """Clean up test keys."""
        client = self.get_client()
        keys = client.keys(pattern)
        if keys:
            client.delete(*keys)
    
    def get_conversation_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get conversation messages for session."""
        client = self.get_client()
        key = f"conversation:{session_id}"
        messages = client.lrange(key, 0, -1)
        return [json.loads(msg) for msg in messages]
    
    def get_token_count(self, session_id: str) -> int:
        """Get token count for session."""
        client = self.get_client()
        key = f"session:{session_id}:tokens"
        result = client.get(key)
        return int(result) if result else 0
    
    def close(self):
        """Close Redis client."""
        if self.client:
            self.client.close()
            self.client = None


class ServiceChecker:
    """Check service availability and health."""
    
    @staticmethod
    def check_redis(host: str = "localhost", port: int = 6379) -> bool:
        """Check if Redis is available."""
        if not REDIS_AVAILABLE:
            return False
        
        try:
            client = redis.Redis(host=host, port=port, socket_connect_timeout=1)
            client.ping()
            return True
        except:
            return False
    
    @staticmethod
    def check_kafka(broker: str = "localhost:29092") -> bool:
        """Check if Kafka/Redpanda is available."""
        if not KAFKA_AVAILABLE:
            return False
        
        try:
            consumer = KafkaConsumer(bootstrap_servers=broker, consumer_timeout_ms=1000)
            consumer.close()
            return True
        except:
            return False
    
    @staticmethod
    def check_all_services() -> Dict[str, bool]:
        """Check all services."""
        return {
            "redis": ServiceChecker.check_redis(),
            "kafka": ServiceChecker.check_kafka()
        }


def wait_for_service(check_func, timeout: int = 10, interval: float = 0.5) -> bool:
    """Wait for a service to become available."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_func():
            return True
        time.sleep(interval)
    return False


if __name__ == "__main__":
    # Test service availability
    print("Checking service availability...")
    services = ServiceChecker.check_all_services()
    
    print(f"Redis: {'✓' if services['redis'] else '✗'}")
    print(f"Kafka/Redpanda: {'✓' if services['kafka'] else '✗'}")
    
    if all(services.values()):
        print("\nAll services are available!")
    else:
        print("\nSome services are not available.")
        print("Start services with: docker-compose up -d")
