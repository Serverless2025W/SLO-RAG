import os
import json
import requests
from kafka import KafkaConsumer, KafkaProducer
import sys
import hashlib
import redis
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# Import schemas for message validation and creation
try:
    from message_schemas import ConversationEvent, LLMResponseEvent, SummarizationTrigger
    from redis_schemas import ConversationMessage, SessionMetadata, RedisConversationStore, RedisKeyPatterns
except ImportError:
    # Fallback if schemas not available
    ConversationEvent = None
    LLMResponseEvent = None
    SummarizationTrigger = None
    ConversationMessage = None
    SessionMetadata = None
    RedisConversationStore = None
    RedisKeyPatterns = None

def log(msg):
    print(msg, flush=True)

def utc_now_iso() -> str:
    """Return UTC timestamp in ISO 8601 with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# Configuration
BROKER = os.getenv("BROKER", "redpanda:9092")
TOPICS_STR = os.getenv("TOPICS", "text-chunks")
TOPICS = [t.strip() for t in TOPICS_STR.split(",")]
TARGET_FUNCTION = os.getenv("TARGET_FUNCTION", "embedding-generation")  # Legacy support
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "faasd-connector-group")

# Redis Configuration (Phase 2)
# Allow test overrides without changing runtime defaults.
REDIS_HOST = os.getenv("TEST_REDIS_HOST", os.getenv("REDIS_HOST", "redis"))
REDIS_PORT = int(os.getenv("TEST_REDIS_PORT", os.getenv("REDIS_PORT", "6379")))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Phase 3 & 4 Configuration
SUMMARIZATION_TOKEN_THRESHOLD = int(os.getenv("SUMMARIZATION_TOKEN_THRESHOLD", "4000"))
SUMMARIZATION_MESSAGE_THRESHOLD = int(os.getenv("SUMMARIZATION_MESSAGE_THRESHOLD", "20"))
CONVERSATION_TTL = int(os.getenv("CONVERSATION_TTL", "86400"))  # 24 hours

# Topic-to-Function Routing Map
TOPIC_ROUTES = {
    "text-chunks": "embedding-generation",
    "conversation-events": "conversation-manager",
    "llm-responses": "conversation-manager",
    "summarization-triggers": "context-summarizer"
}

# Redis client (initialized lazily)
redis_client: Optional[redis.Redis] = None

# Kafka Producer for publishing summarization triggers (initialized lazily)
kafka_producer: Optional[KafkaProducer] = None

def init_redis_client() -> Optional[redis.Redis]:
    """Initialize Redis client with graceful fallback."""
    global redis_client
    if redis_client is not None:
        return redis_client
    
    try:
        host = os.getenv("TEST_REDIS_HOST", os.getenv("REDIS_HOST", "redis"))
        port = int(os.getenv("TEST_REDIS_PORT", os.getenv("REDIS_PORT", "6379")))
        client = redis.Redis(
            host=host,
            port=port,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2
        )
        # Test connection
        client.ping()
        redis_client = client
        log(f"Successfully connected to Redis at {host}:{port}")
        return redis_client
    except Exception as e:
        log(f"WARNING: Could not connect to Redis: {e}. Continuing without Redis.")
        return None

def get_target_function(topic: str) -> str:
    """Get target function name for a topic."""
    return TOPIC_ROUTES.get(topic, TARGET_FUNCTION)

def compute_query_hash(query: str) -> str:
    """Compute hash for query embedding cache key."""
    return hashlib.sha256(query.encode('utf-8')).hexdigest()

def get_query_embedding_cache(query: str) -> Optional[Any]:
    """Get cached query embedding from Redis (Phase 2)."""
    client = init_redis_client()
    if client is None:
        return None
    
    try:
        query_hash = compute_query_hash(query)
        cache_key = f"query:embedding:{query_hash}"
        cached = client.get(cache_key)
        if cached:
            log(f"Cache HIT for query embedding: {query_hash[:8]}...")
            return json.loads(cached)
        else:
            log(f"Cache MISS for query embedding: {query_hash[:8]}...")
            return None
    except Exception as e:
        log(f"WARNING: Redis cache read failed: {e}")
        return None

def set_query_embedding_cache(query: str, embedding: Any, ttl: int = 3600) -> bool:
    """Cache query embedding in Redis (Phase 2)."""
    client = init_redis_client()
    if client is None:
        return False
    
    try:
        query_hash = compute_query_hash(query)
        cache_key = f"query:embedding:{query_hash}"
        client.setex(cache_key, ttl, json.dumps(embedding))
        log(f"Cached query embedding: {query_hash[:8]}...")
        return True
    except Exception as e:
        log(f"WARNING: Redis cache write failed: {e}")
        return False

def get_conversation_history(session_id: str, limit: Optional[int] = None) -> Optional[list]:
    """Read conversation history from Redis if available (Phase 2)."""
    client = init_redis_client()
    if client is None:
        return None
    
    try:
        if RedisConversationStore:
            messages = RedisConversationStore.get_messages(client, session_id, limit)
            if messages:
                log(f"Retrieved {len(messages)} messages from Redis for session {session_id}")
                return [msg.to_dict() for msg in messages]
            return []
        else:
            # Fallback to direct Redis access
            key = f"conversation:{session_id}"
            if limit:
                messages = client.lrange(key, -limit, -1)
            else:
                messages = client.lrange(key, 0, -1)
            
            if messages:
                log(f"Retrieved {len(messages)} messages from Redis for session {session_id}")
                return [json.loads(msg) for msg in messages]
            return []
    except Exception as e:
        log(f"WARNING: Failed to read conversation history from Redis: {e}")
        return None

def init_kafka_producer() -> Optional[KafkaProducer]:
    """Initialize Kafka producer for publishing summarization triggers."""
    global kafka_producer
    if kafka_producer is not None:
        return kafka_producer
    
    try:
        producer = KafkaProducer(
            bootstrap_servers=BROKER,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            retries=3
        )
        kafka_producer = producer
        log(f"Successfully initialized Kafka producer for broker {BROKER}")
        return kafka_producer
    except Exception as e:
        log(f"WARNING: Could not initialize Kafka producer: {e}")
        return None

def update_conversation_state(data: Dict[str, Any]) -> bool:
    """
    Phase 3: Store conversation message and update state in Redis.
    
    Args:
        data: Message data containing session_id, role, content, timestamp, metadata
    
    Returns:
        True if successful, False otherwise
    """
    client = init_redis_client()
    if client is None:
        log("WARNING: Redis not available, skipping conversation state update")
        return False
    
    try:
        session_id = data.get("session_id")
        if not session_id:
            log("WARNING: No session_id in message, skipping state update")
            return False
        
        role = data.get("role", "user")
        content = data.get("content", "")
        timestamp = data.get("timestamp", utc_now_iso())
        metadata = data.get("metadata", {})
        tokens = metadata.get("tokens", 0) if isinstance(metadata, dict) else 0
        
        # Create conversation message
        if ConversationMessage:
            message = ConversationMessage(
                role=role,
                content=content,
                timestamp=timestamp
            )
            RedisConversationStore.store_message(client, session_id, message, CONVERSATION_TTL)
        else:
            # Fallback: direct Redis access
            key = f"conversation:{session_id}"
            message_data = {
                "role": role,
                "content": content,
                "timestamp": timestamp
            }
            client.rpush(key, json.dumps(message_data))
            client.expire(key, CONVERSATION_TTL)
        
        # Update token count
        if tokens > 0:
            if RedisConversationStore:
                RedisConversationStore.update_token_count(client, session_id, tokens)
            else:
                # Fallback
                token_key = f"session:{session_id}:tokens"
                client.incrby(token_key, tokens)
                client.expire(token_key, CONVERSATION_TTL)
        
        # Update session metadata
        if RedisConversationStore:
            # Get current message count
            message_count = RedisConversationStore.get_message_count(client, session_id)
            token_count = RedisConversationStore.get_token_count(client, session_id)
            
            # Get or create metadata
            existing_metadata = RedisConversationStore.get_session_metadata(client, session_id)
            if existing_metadata:
                created_at = existing_metadata.created_at
            else:
                created_at = timestamp
            
            metadata_obj = SessionMetadata(
                created_at=created_at,
                last_activity=timestamp,
                message_count=message_count,
                token_count=token_count
            )
            RedisConversationStore.update_session_metadata(client, session_id, metadata_obj, CONVERSATION_TTL)
        else:
            # Fallback: update metadata hash
            meta_key = f"session:{session_id}:meta"
            message_count = client.llen(f"conversation:{session_id}")
            token_count = int(client.get(f"session:{session_id}:tokens") or 0)
            
            existing_meta = client.hgetall(meta_key)
            created_at = existing_meta.get("created_at", timestamp) if existing_meta else timestamp
            
            client.hset(meta_key, mapping={
                "created_at": created_at,
                "last_activity": timestamp,
                "message_count": str(message_count),
                "token_count": str(token_count)
            })
            client.expire(meta_key, CONVERSATION_TTL)
        
        log(f"Updated conversation state for session {session_id}: +{tokens} tokens")
        return True
        
    except Exception as e:
        log(f"ERROR: Failed to update conversation state: {e}")
        return False

def check_summarization_threshold(session_id: str) -> tuple[bool, Optional[str], int, int]:
    """
    Phase 4: Check if summarization threshold is exceeded.
    
    Args:
        session_id: Session identifier
    
    Returns:
        (should_trigger, reason, current_tokens, current_messages)
    """
    client = init_redis_client()
    if client is None:
        return False, None, 0, 0
    
    try:
        if RedisConversationStore:
            token_count = RedisConversationStore.get_token_count(client, session_id)
            message_count = RedisConversationStore.get_message_count(client, session_id)
        else:
            # Fallback
            token_count = int(client.get(f"session:{session_id}:tokens") or 0)
            message_count = client.llen(f"conversation:{session_id}")
        
        token_exceeded = token_count > SUMMARIZATION_TOKEN_THRESHOLD
        message_exceeded = message_count > SUMMARIZATION_MESSAGE_THRESHOLD
        
        if token_exceeded:
            return True, "token_threshold", token_count, message_count
        elif message_exceeded:
            return True, "message_threshold", token_count, message_count
        else:
            return False, None, token_count, message_count
            
    except Exception as e:
        log(f"WARNING: Failed to check summarization threshold: {e}")
        return False, None, 0, 0

def trigger_summarization(session_id: str, trigger_reason: str, current_tokens: int, current_messages: int) -> bool:
    """
    Phase 4: Publish summarization trigger to Kafka topic.
    
    Args:
        session_id: Session identifier
        trigger_reason: Reason for summarization ("token_threshold" or "message_threshold")
        current_tokens: Current token count
        current_messages: Current message count
    
    Returns:
        True if published successfully, False otherwise
    """
    producer = init_kafka_producer()
    if producer is None:
        log("WARNING: Kafka producer not available, cannot trigger summarization")
        return False
    
    try:
        if SummarizationTrigger:
            trigger = SummarizationTrigger(
                session_id=session_id,
                trigger_reason=trigger_reason,
                current_tokens=current_tokens,
                current_messages=current_messages,
                threshold=SUMMARIZATION_TOKEN_THRESHOLD if trigger_reason == "token_threshold" else SUMMARIZATION_MESSAGE_THRESHOLD
            )
            trigger_data = trigger.to_dict()
        else:
            # Fallback
            trigger_data = {
                "session_id": session_id,
                "trigger_reason": trigger_reason,
                "current_tokens": current_tokens,
                "current_messages": current_messages,
                "threshold": SUMMARIZATION_TOKEN_THRESHOLD if trigger_reason == "token_threshold" else SUMMARIZATION_MESSAGE_THRESHOLD
            }
        
        # Publish to summarization-triggers topic
        future = producer.send("summarization-triggers", trigger_data)
        # Wait for confirmation (with timeout)
        record_metadata = future.get(timeout=10)
        
        log(f"Published summarization trigger for session {session_id} (reason: {trigger_reason})")
        log(f"  Topic: {record_metadata.topic}, Partition: {record_metadata.partition}, Offset: {record_metadata.offset}")
        return True
        
    except Exception as e:
        log(f"ERROR: Failed to publish summarization trigger: {e}")
        return False

def finalize_conversation_update(data: Dict[str, Any]) -> None:
    """
    Phase 3: Finalize conversation update after successful function invocation.
    
    This can be used for any post-processing after the function call.
    Currently, the main work is done in update_conversation_state().
    """
    # Additional post-processing can be added here if needed
    pass

def handle_summarization_result(session_id: str, summary_response: Dict[str, Any]) -> bool:
    """
    Phase 4: Handle summarization result from context-summarizer function.
    
    Replaces conversation history with summary in Redis.
    
    Args:
        session_id: Session identifier
        summary_response: Response from context-summarizer function
    
    Returns:
        True if successful, False otherwise
    """
    client = init_redis_client()
    if client is None:
        log("WARNING: Redis not available, cannot update conversation with summary")
        return False
    
    try:
        summary_text = summary_response.get("summary", "")
        timestamp = summary_response.get("timestamp", utc_now_iso())
        
        if ConversationMessage:
            summary_message = ConversationMessage(
                role="system",
                content=summary_text,
                timestamp=timestamp
            )
            RedisConversationStore.replace_conversation_with_summary(
                client, session_id, summary_message, CONVERSATION_TTL
            )
            
            # Reset token count (summary replaces old messages)
            RedisConversationStore.update_token_count(client, session_id, -RedisConversationStore.get_token_count(client, session_id))
            
            # Update metadata
            metadata = SessionMetadata(
                created_at=timestamp,  # Reset created_at to summary time
                last_activity=timestamp,
                message_count=1,  # Only summary message now
                token_count=0  # Reset token count
            )
            RedisConversationStore.update_session_metadata(client, session_id, metadata, CONVERSATION_TTL)
        else:
            # Fallback: direct Redis access
            key = f"conversation:{session_id}"
            summary_data = {
                "role": "system",
                "content": summary_text,
                "timestamp": timestamp
            }
            client.delete(key)
            client.rpush(key, json.dumps(summary_data))
            client.expire(key, CONVERSATION_TTL)
            
            # Reset token count
            token_key = f"session:{session_id}:tokens"
            client.delete(token_key)
        
        log(f"Replaced conversation history with summary for session {session_id}")
        return True
        
    except Exception as e:
        log(f"ERROR: Failed to handle summarization result: {e}")
        return False

def invoke_function(function_name: str, data: Any, use_cache: bool = False) -> Optional[Dict[str, Any]]:
    """
    Invoke OpenFaaS function with optional Redis caching for queries.
    
    Returns:
        Response data as dict if successful, None otherwise
    """
    # For text-chunks/embedding-generation, check cache first
    if use_cache and function_name == "embedding-generation":
        # Extract query from data
        if isinstance(data, str):
            try:
                data_dict = json.loads(data)
                query = data_dict.get("text", data_dict.get("query", ""))
            except:
                query = data
        else:
            query = data.get("text", data.get("query", "")) if isinstance(data, dict) else str(data)
        
        if query:
            cached_embedding = get_query_embedding_cache(query)
            if cached_embedding:
                # Return cached result (in a real scenario, you might publish this back)
                log(f"Using cached embedding for query")
                return {"cached": True, "embedding": cached_embedding}
    
    # Invoke function via HTTP
    url = f"{GATEWAY_URL}/function/{function_name}"
    try:
        if isinstance(data, str):
            response = requests.post(url, data=data, timeout=30)
        else:
            response = requests.post(url, json=data, timeout=30)
        
        if response.status_code == 200:
            log(f"Successfully invoked {function_name}: {response.status_code}")
            
            # Parse response
            try:
                if response.headers.get('content-type', '').startswith('application/json'):
                    result = response.json()
                else:
                    result = {"text": response.text}
            except:
                result = {"text": response.text}
            
            # Cache the result if it's an embedding (Phase 2)
            if use_cache and function_name == "embedding-generation":
                try:
                    if isinstance(data, str):
                        try:
                            data_dict = json.loads(data)
                            query = data_dict.get("text", data_dict.get("query", ""))
                        except:
                            query = data
                    else:
                        query = data.get("text", data.get("query", "")) if isinstance(data, dict) else str(data)
                    
                    if query and result:
                        set_query_embedding_cache(query, result)
                except Exception as e:
                    log(f"WARNING: Failed to cache result: {e}")
            
            return result
        else:
            log(f"ERROR: Function {function_name} returned status {response.status_code}")
            return None
    except Exception as e:
        log(f"ERROR: Failed to invoke {function_name}: {str(e)}")
        return None

def process_message(message) -> None:
    """
    Process a single Kafka message with Phase 3 & 4 support.
    
    Flow:
    - conversation-events/llm-responses: Update Redis state → Invoke function → Check threshold → Trigger summarization if needed
    - summarization-triggers: Invoke summarizer → Replace conversation with summary
    - text-chunks: Use cache → Invoke function
    """
    topic = message.topic
    try:
        # Parse message value
        if isinstance(message.value, bytes):
            data = json.loads(message.value.decode('utf-8'))
        elif isinstance(message.value, str):
            data = json.loads(message.value)
        else:
            data = message.value
        
        log(f"Received message on topic '{topic}': {str(data)[:100]}...")
        
        # Get target function for this topic
        target_function = get_target_function(topic)
        log(f"Routing to function: {target_function}")
        
        # Phase 3: Handle conversation-events and llm-responses
        if topic in ["conversation-events", "llm-responses"]:
            session_id = data.get("session_id") if isinstance(data, dict) else None
            if session_id:
                # Read existing history (for context)
                history = get_conversation_history(session_id, limit=10)
                if history:
                    log(f"Retrieved {len(history)} messages from conversation history for session {session_id}")
                
                # Update Redis state BEFORE invoking function (Phase 3)
                update_conversation_state(data)
                
                # Invoke conversation-manager function
                use_cache = False
                result = invoke_function(target_function, data, use_cache=use_cache)
                
                # Finalize conversation update (Phase 3)
                if result:
                    finalize_conversation_update(data)
                
                # Phase 4: Check if summarization is needed
                should_trigger, reason, current_tokens, current_messages = check_summarization_threshold(session_id)
                if should_trigger:
                    log(f"Summarization threshold exceeded for session {session_id}: {reason}")
                    log(f"  Current: {current_messages} messages, {current_tokens} tokens")
                    trigger_summarization(session_id, reason, current_tokens, current_messages)
        
        # Phase 4: Handle summarization-triggers
        elif topic == "summarization-triggers":
            session_id = data.get("session_id") if isinstance(data, dict) else None
            if session_id:
                # Invoke context-summarizer function
                result = invoke_function(target_function, data, use_cache=False)
                
                # Handle summarization result: replace conversation with summary
                if result:
                    try:
                        # Parse result (could be dict or JSON string)
                        if isinstance(result, str):
                            summary_response = json.loads(result)
                        elif isinstance(result, dict):
                            summary_response = result
                        else:
                            summary_response = {"summary": str(result), "timestamp": utc_now_iso()}
                        
                        # Replace conversation history with summary
                        handle_summarization_result(session_id, summary_response)
                    except Exception as e:
                        log(f"ERROR: Failed to process summarization result: {e}")
        
        # Phase 1 & 2: Handle text-chunks (existing workflow)
        else:
            # Ingestion chunks are not query embeddings; skip cache.
            invoke_function(target_function, data, use_cache=False)
        
    except json.JSONDecodeError as e:
        log(f"ERROR: Failed to parse message as JSON: {e}")
    except Exception as e:
        log(f"ERROR: Error processing message: {str(e)}")

def main():
    log("--- Redpanda Connector Starting (Phases 1, 2, 3 & 4) ---")
    log(f"Gateway: {GATEWAY_URL}")
    log(f"Broker: {BROKER}")
    log(f"Topics: {', '.join(TOPICS)}")
    log(f"Consumer Group: {CONSUMER_GROUP}")
    log(f"Summarization Thresholds: {SUMMARIZATION_TOKEN_THRESHOLD} tokens, {SUMMARIZATION_MESSAGE_THRESHOLD} messages")
    log(f"Conversation TTL: {CONVERSATION_TTL} seconds ({CONVERSATION_TTL // 3600} hours)")
    
    # Initialize Redis client - graceful failure
    init_redis_client()
    
    # Initialize Kafka Producer - graceful failure
    init_kafka_producer()
    
    # Initialize Kafka Consumer
    try:
        consumer = KafkaConsumer(
            *TOPICS,
            bootstrap_servers=BROKER,
            auto_offset_reset='latest',
            enable_auto_commit=True,
            group_id=CONSUMER_GROUP,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')) if isinstance(x, bytes) else x
        )
        log("Successfully connected to Redpanda.")
        log(f"Subscribed to topics: {', '.join(TOPICS)}")
    except Exception as e:
        log(f"CRITICAL: Could not connect to Redpanda: {e}")
        sys.exit(1)
    
    # Process messages
    try:
        for message in consumer:
            process_message(message)
    except KeyboardInterrupt:
        log("Shutting down...")
        # Cleanup
        if kafka_producer:
            kafka_producer.close()
    except Exception as e:
        log(f"CRITICAL: Consumer error: {e}")
        if kafka_producer:
            kafka_producer.close()
        sys.exit(1)

if __name__ == "__main__":
    main()