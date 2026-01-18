"""
Conversation Manager Handler - Workflow 3

This handler manages the complete conversation lifecycle:
1. Validates incoming conversation events
2. Stores messages in Redis
3. Updates token counts and session metadata
4. Checks summarization thresholds
5. Triggers summarization via Kafka if needed
6. Calls LLM for response (TODO: implement)
7. Returns response
"""

import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import redis

# Lazy imports for Kafka (only when needed)
kafka_producer = None

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "redpanda:9092")
SUMMARIZATION_TOKEN_THRESHOLD = int(os.getenv("SUMMARIZATION_TOKEN_THRESHOLD", "4000"))
SUMMARIZATION_MESSAGE_THRESHOLD = int(os.getenv("SUMMARIZATION_MESSAGE_THRESHOLD", "20"))
CONVERSATION_TTL = int(os.getenv("CONVERSATION_TTL", "86400"))  # 24 hours

# Redis client (initialized lazily)
redis_client: Optional[redis.Redis] = None

def log(message):
    """Log message with flush enabled."""
    print(message, flush=True)

def utc_now_iso() -> str:
    """Return UTC timestamp in ISO 8601 with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def init_redis_client() -> Optional[redis.Redis]:
    """Initialize Redis client with graceful fallback."""
    global redis_client
    if redis_client is not None:
        return redis_client
    
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        client.ping()
        redis_client = client
        log(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        return redis_client
    except Exception as e:
        log(f"WARNING: Could not connect to Redis: {e}")
        return None

def init_kafka_producer():
    """Initialize Kafka producer for publishing summarization triggers."""
    global kafka_producer
    if kafka_producer is not None:
        return kafka_producer
    
    try:
        from kafka import KafkaProducer
        kafka_producer = KafkaProducer(
            bootstrap_servers=KAFKA_BROKER,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            retries=3
        )
        log(f"Connected to Kafka at {KAFKA_BROKER}")
        return kafka_producer
    except Exception as e:
        log(f"WARNING: Could not connect to Kafka: {e}")
        return None

def get_conversation_history(session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Retrieve conversation history from Redis."""
    client = init_redis_client()
    if client is None:
        return []
    
    try:
        key = f"conversation:{session_id}"
        if limit:
            messages = client.lrange(key, -limit, -1)
        else:
            messages = client.lrange(key, 0, -1)
        
        if messages:
            log(f"Retrieved {len(messages)} messages for session {session_id}")
            return [json.loads(msg) for msg in messages]
        return []
    except Exception as e:
        log(f"WARNING: Failed to read conversation history: {e}")
        return []

def store_message(session_id: str, role: str, content: str, timestamp: str, tokens: int = 0) -> bool:
    """Store a message in Redis and update session state."""
    client = init_redis_client()
    if client is None:
        return False
    
    try:
        # Store message
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
            token_key = f"session:{session_id}:tokens"
            client.incrby(token_key, tokens)
            client.expire(token_key, CONVERSATION_TTL)
        
        # Update metadata
        meta_key = f"session:{session_id}:meta"
        message_count = client.llen(key)
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
        
        log(f"Stored message for session {session_id}: {role}, +{tokens} tokens")
        return True
    except Exception as e:
        log(f"ERROR: Failed to store message: {e}")
        return False

def check_summarization_threshold(session_id: str) -> tuple:
    """Check if summarization threshold is exceeded."""
    client = init_redis_client()
    if client is None:
        return False, None, 0, 0
    
    try:
        token_count = int(client.get(f"session:{session_id}:tokens") or 0)
        message_count = client.llen(f"conversation:{session_id}")
        
        if token_count > SUMMARIZATION_TOKEN_THRESHOLD:
            return True, "token_threshold", token_count, message_count
        elif message_count > SUMMARIZATION_MESSAGE_THRESHOLD:
            return True, "message_threshold", token_count, message_count
        else:
            return False, None, token_count, message_count
    except Exception as e:
        log(f"WARNING: Failed to check threshold: {e}")
        return False, None, 0, 0

def trigger_summarization(session_id: str, reason: str, tokens: int, messages: int) -> bool:
    """Publish summarization trigger to Kafka topic."""
    producer = init_kafka_producer()
    if producer is None:
        log("WARNING: Cannot trigger summarization - Kafka not available")
        return False
    
    try:
        trigger_data = {
            "session_id": session_id,
            "trigger_reason": reason,
            "current_tokens": tokens,
            "current_messages": messages,
            "threshold": SUMMARIZATION_TOKEN_THRESHOLD if reason == "token_threshold" else SUMMARIZATION_MESSAGE_THRESHOLD
        }
        
        future = producer.send("summarization-triggers", trigger_data)
        record = future.get(timeout=10)
        
        log(f"Published summarization trigger for session {session_id}")
        log(f"  Reason: {reason}, Topic: {record.topic}, Offset: {record.offset}")
        return True
    except Exception as e:
        log(f"ERROR: Failed to trigger summarization: {e}")
        return False

def format_messages_for_llm(history: List[Dict[str, Any]], current_message: Dict[str, Any]) -> List[Dict[str, str]]:
    """Format conversation history for LLM API."""
    messages = []
    
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role != "system":  # Skip system summaries
            messages.append({"role": role, "content": content})
    
    current_role = current_message.get("role", "user")
    current_content = current_message.get("content", "")
    if current_role == "user":
        messages.append({"role": "user", "content": current_content})
    
    return messages

def parse_input(req) -> Dict[str, Any]:
    """Parse input from request body."""
    if hasattr(req, 'body'):
        body = req.body
    else:
        body = req
    
    if isinstance(body, bytes):
        body = body.decode('utf-8')
    
    if isinstance(body, str):
        body = json.loads(body)
    
    return body

def validate_conversation_event(data: Dict[str, Any]) -> tuple:
    """Validate conversation event message structure."""
    required_fields = ['session_id', 'role', 'content', 'timestamp']
    
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
    
    if data['role'] not in ['user', 'assistant']:
        return False, f"Invalid role: {data['role']}"
    
    if not data['session_id']:
        return False, "session_id cannot be empty"
    
    if not data.get('content'):
        return False, "content cannot be empty"
    
    return True, None

def handle(req, context):
    """
    Main handler for conversation management.
    
    Flow:
    1. Parse and validate input
    2. Store message in Redis
    3. Check summarization threshold
    4. Trigger summarization if needed
    """
    log("=" * 50)
    log("Conversation Manager Handler Invoked")
    log("=" * 50)
    
    # Parse input
    try:
        data = parse_input(req)
        log(f"Received event for session: {data.get('session_id', 'unknown')}")
    except json.JSONDecodeError as e:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON", "details": str(e)})}
    except Exception as e:
        return {"statusCode": 400, "body": json.dumps({"error": "Parse error", "details": str(e)})}

    # Handle history retrieval action
    if data.get("action") == "get_history":
        session_id = data.get("session_id")
        if not session_id:
            return {"statusCode": 400, "body": json.dumps({"error": "session_id required"})}
        history = get_conversation_history(session_id)
        log(f"Returning {len(history)} messages for session {session_id}")
        return {"statusCode": 200, "body": json.dumps({"messages": history})}

    # Validate
    is_valid, error_msg = validate_conversation_event(data)
    if not is_valid:
        log(f"Validation error: {error_msg}")
        return {"statusCode": 400, "body": json.dumps({"error": "Validation failed", "details": error_msg})}
    
    # Extract fields
    session_id = data['session_id']
    role = data['role']
    content = data['content']
    timestamp = data.get('timestamp', utc_now_iso())
    metadata = data.get('metadata', {})
    tokens = metadata.get('tokens', 0) if isinstance(metadata, dict) else 0
    
    log(f"Processing {role} message for session {session_id}")
    
    # Step 1: Store message in Redis
    store_message(session_id, role, content, timestamp, tokens)
    
    # Step 2: Check summarization threshold
    should_trigger, reason, current_tokens, current_messages = check_summarization_threshold(session_id)
    
    if should_trigger:
        log(f"Threshold exceeded: {reason} ({current_messages} msgs, {current_tokens} tokens)")
        # Step 3: Trigger summarization
        trigger_summarization(session_id, reason, current_tokens, current_messages)
    
    # For assistant messages, just acknowledge storage
    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "success",
            "session_id": session_id,
            "message": "Message stored",
            "state": {
                "messages": current_messages,
                "tokens": current_tokens,
                "summarization_triggered": should_trigger
            }
        })
    }
