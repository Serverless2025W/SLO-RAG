"""
Context Summarizer Handler - Workflow 4

This handler manages conversation summarization:
1. Receives summarization triggers
2. Retrieves full conversation history from Redis
3. Calls LLM to generate summary (TODO: implement)
4. Replaces conversation history with summary in Redis
5. Resets token counts
"""

import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import redis

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
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

def get_conversation_history(session_id: str) -> List[Dict[str, Any]]:
    """Retrieve full conversation history from Redis."""
    client = init_redis_client()
    if client is None:
        return []
    
    try:
        key = f"conversation:{session_id}"
        messages = client.lrange(key, 0, -1)
        
        if messages:
            log(f"Retrieved {len(messages)} messages for summarization")
            return [json.loads(msg) for msg in messages]
        return []
    except Exception as e:
        log(f"WARNING: Failed to read conversation history: {e}")
        return []

def replace_conversation_with_summary(session_id: str, summary: str, timestamp: str) -> bool:
    """Replace entire conversation history with a summary message."""
    client = init_redis_client()
    if client is None:
        return False
    
    try:
        # Delete existing conversation
        conv_key = f"conversation:{session_id}"
        client.delete(conv_key)
        
        # Store summary as system message
        summary_message = {
            "role": "system",
            "content": summary,
            "timestamp": timestamp
        }
        client.rpush(conv_key, json.dumps(summary_message))
        client.expire(conv_key, CONVERSATION_TTL)
        
        # Reset token count
        token_key = f"session:{session_id}:tokens"
        client.delete(token_key)
        
        # Update metadata
        meta_key = f"session:{session_id}:meta"
        client.hset(meta_key, mapping={
            "created_at": timestamp,
            "last_activity": timestamp,
            "message_count": "1",
            "token_count": "0"
        })
        client.expire(meta_key, CONVERSATION_TTL)
        
        log(f"Replaced conversation with summary for session {session_id}")
        return True
    except Exception as e:
        log(f"ERROR: Failed to replace conversation: {e}")
        return False

def format_messages_for_summarization(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Format conversation history for summarization LLM call."""
    messages = []
    
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role != "system":  # Skip previous summaries
            messages.append({"role": role, "content": content})
    
    return messages

def call_llm_for_summarization(messages: List[Dict[str, str]], model: str = None) -> Dict[str, Any]:
    """
    Call LLM API to generate conversation summary.
    
    TODO: Uncomment the LLMClient implementation below.
    """
    if model is None:
        model = os.getenv("SUMMARIZATION_MODEL", "gpt-3.5-turbo")
    
    # ==========================================================================
    # TODO: Uncomment below and add 'from openai import OpenAI' at top
    # ==========================================================================
    # api_key = os.getenv("LLM_API_KEY")
    # if not api_key:
    #     raise ValueError("LLM_API_KEY environment variable not set")
    # 
    # client = OpenAI(api_key=api_key)
    # 
    # system_prompt = {
    #     "role": "system",
    #     "content": "You are a helpful assistant that summarizes conversations. "
    #                "Create a concise summary that captures the key points, context, "
    #                "and important information. Keep it brief but preserve essential context."
    # }
    # 
    # response = client.chat.completions.create(
    #     model=model,
    #     messages=[system_prompt] + messages,
    #     temperature=0.3,
    #     max_tokens=500
    # )
    # 
    # return {
    #     "summary": response.choices[0].message.content,
    #     "usage": {
    #         "prompt_tokens": response.usage.prompt_tokens,
    #         "completion_tokens": response.usage.completion_tokens,
    #         "total_tokens": response.usage.total_tokens
    #     }
    # }
    # ==========================================================================
    
    # TODO: Remove this placeholder block
    log(f"[PLACEHOLDER] Would summarize {len(messages)} messages with model: {model}")
    
    # Create a simple placeholder summary
    msg_count = len(messages)
    return {
        "summary": f"[Summary placeholder] Conversation with {msg_count} messages summarized.",
        "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}
    }

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

def validate_summarization_trigger(data: Dict[str, Any]) -> tuple:
    """Validate summarization trigger message structure."""
    required_fields = ['session_id', 'trigger_reason', 'current_tokens', 'current_messages', 'threshold']
    
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
    
    valid_reasons = ['token_threshold', 'message_threshold', 'manual']
    if data['trigger_reason'] not in valid_reasons:
        return False, f"Invalid trigger_reason: {data['trigger_reason']}"
    
    if not data['session_id']:
        return False, "session_id cannot be empty"
    
    if data['current_tokens'] < 0 or data['current_messages'] < 0:
        return False, "Token and message counts must be non-negative"
    
    return True, None

def handle(req, context):
    """
    Main handler for context summarization.
    
    Flow:
    1. Parse and validate summarization trigger
    2. Retrieve full conversation history from Redis
    3. Call LLM to generate summary
    4. Replace conversation with summary in Redis
    5. Return success response
    """
    log("=" * 50)
    log("Context Summarizer Handler Invoked")
    log("=" * 50)
    
    # Parse input
    try:
        data = parse_input(req)
        log(f"Received trigger for session: {data.get('session_id', 'unknown')}")
    except json.JSONDecodeError as e:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON", "details": str(e)})}
    except Exception as e:
        return {"statusCode": 400, "body": json.dumps({"error": "Parse error", "details": str(e)})}
    
    # Validate
    is_valid, error_msg = validate_summarization_trigger(data)
    if not is_valid:
        log(f"Validation error: {error_msg}")
        return {"statusCode": 400, "body": json.dumps({"error": "Validation failed", "details": error_msg})}
    
    # Extract fields
    session_id = data['session_id']
    trigger_reason = data['trigger_reason']
    current_tokens = data['current_tokens']
    current_messages = data['current_messages']
    threshold = data['threshold']
    
    log(f"Summarizing session {session_id}")
    log(f"Reason: {trigger_reason} (threshold: {threshold})")
    log(f"Current: {current_messages} messages, {current_tokens} tokens")
    
    # Step 1: Retrieve full conversation history
    history = get_conversation_history(session_id)
    
    if not history:
        log(f"WARNING: No conversation history found for session {session_id}")
        return {
            "statusCode": 404,
            "body": json.dumps({
                "error": "No conversation history found",
                "session_id": session_id
            })
        }
    
    log(f"Retrieved {len(history)} messages for summarization")
    
    # Step 2: Format messages for LLM
    formatted_messages = format_messages_for_summarization(history)
    log(f"Formatted {len(formatted_messages)} messages (excluding system)")
    
    # Step 3: Call LLM for summarization
    model = os.getenv("SUMMARIZATION_MODEL", "gpt-3.5-turbo")
    try:
        llm_response = call_llm_for_summarization(formatted_messages, model=model)
        
        summary_text = llm_response.get("summary", "")
        usage = llm_response.get("usage", {})
        
        log(f"Generated summary: {len(summary_text)} characters")
        log(f"Token usage: {usage.get('total_tokens', 0)} total")
    except Exception as e:
        log(f"ERROR: LLM summarization failed: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "LLM summarization failed",
                "details": str(e),
                "session_id": session_id
            })
        }
    
    # Step 4: Replace conversation with summary in Redis
    timestamp = utc_now_iso()
    success = replace_conversation_with_summary(session_id, summary_text, timestamp)
    
    if not success:
        log(f"ERROR: Failed to replace conversation with summary")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Failed to update Redis",
                "session_id": session_id
            })
        }
    
    # Return success
    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "success",
            "session_id": session_id,
            "summary": summary_text,
            "timestamp": timestamp,
            "trigger_reason": trigger_reason,
            "compressed_from": {
                "messages": current_messages,
                "tokens": current_tokens
            },
            "usage": usage
        })
    }
