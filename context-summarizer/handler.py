"""
Context Summarizer Handler - Workflow 4

This handler receives summarization trigger events and generates summaries
of conversation history when thresholds are exceeded.
"""

import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import redis

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

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
            socket_connect_timeout=2,
            socket_timeout=2
        )
        # Test connection
        client.ping()
        redis_client = client
        log(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        return redis_client
    except Exception as e:
        log(f"WARNING: Could not connect to Redis: {e}. Continuing without Redis.")
        return None

def get_conversation_history(session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Retrieve conversation history from Redis.
    
    Args:
        session_id: Session identifier
        limit: Maximum number of messages to retrieve (None = all)
    
    Returns:
        List of message dictionaries with role, content, timestamp
    """
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
            log(f"Retrieved {len(messages)} messages from conversation history for session {session_id}")
            return [json.loads(msg) for msg in messages]
        return []
    except Exception as e:
        log(f"WARNING: Failed to read conversation history from Redis: {e}")
        return []

def format_messages_for_summarization(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Format conversation history for summarization LLM call.
    
    Args:
        history: Conversation messages from Redis
    
    Returns:
        List of messages in LLM API format, excluding system messages
    """
    messages = []
    
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Skip system messages (they're previous summaries)
        if role != "system":
            messages.append({
                "role": role,
                "content": content
            })
    
    return messages

def call_llm_for_summarization(messages: List[Dict[str, str]], model: str = None) -> Dict[str, Any]:
    """
    Call LLM API to generate conversation summary.
    
    Args:
        messages: Formatted conversation messages
        model: Model name to use (defaults to SUMMARIZATION_MODEL env var)
    
    Returns:
        Response from LLM API with 'summary' text
    
    TODO: Replace placeholder with actual LLM implementation
    """
    if model is None:
        model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    
    # ==========================================================================
    # TODO: Uncomment below and add 'from llm_service import LLMClient' at top
    # ==========================================================================
    # api_key = os.getenv("LLM_API_KEY")
    # if not api_key:
    #     raise ValueError("LLM_API_KEY environment variable not set")
    # 
    # client = LLMClient(api_key=api_key)
    # 
    # system_prompt = {
    #     "role": "system",
    #     "content": "You are a helpful assistant that summarizes conversations. "
    #                "Create a concise summary that captures the key points, context, "
    #                "and important information from the conversation. "
    #                "The summary should be brief but preserve essential context for future reference."
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
    log(f"[PLACEHOLDER] Would call LLM API for summarization with {len(messages)} messages, model: {model}")
    
    return {
        "summary": f"[Summary placeholder - implement call_llm_for_summarization()]. Original conversation had {len(messages)} messages.",
        "usage": {
            "prompt_tokens": 200,
            "completion_tokens": 100,
            "total_tokens": 300
        }
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

def validate_summarization_trigger(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate summarization trigger message structure.
    
    Returns:
        (is_valid, error_message)
    """
    required_fields = ['session_id', 'trigger_reason', 'current_tokens', 'current_messages', 'threshold']
    
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
    
    # Validate trigger_reason
    valid_reasons = ['token_threshold', 'message_threshold', 'manual']
    if data['trigger_reason'] not in valid_reasons:
        return False, f"Invalid trigger_reason: {data['trigger_reason']}. Must be one of {valid_reasons}"
    
    # Validate session_id
    if not data['session_id']:
        return False, "session_id cannot be empty"
    
    # Validate numeric fields
    if data['current_tokens'] < 0 or data['current_messages'] < 0:
        return False, "Token and message counts must be non-negative"
    
    return True, None


def handle(req, context):
    """
    Main handler function for context summarization.
    
    Receives summarization trigger events from the connector.
    Validates the trigger and returns a summary.
    
    Expected input format:
    {
        "session_id": "uuid",
        "trigger_reason": "token_threshold" | "message_threshold" | "manual",
        "current_tokens": 4500,
        "current_messages": 25,
        "threshold": 4000
    }
    
    Returns:
    {
        "status": "success",
        "session_id": "uuid",
        "summary": "summary text",
        "timestamp": "ISO 8601 timestamp"
    }
    """
    log("Context Summarizer Handler Invoked")
    
    try:
        data = parse_input(req)
        log(f"Received summarization trigger for session: {data.get('session_id', 'unknown')}")
    except json.JSONDecodeError as e:
        log(f"JSON parse error: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON", "details": str(e)})
        }
    except Exception as e:
        log(f"Input parse error: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Input parse error", "details": str(e)})
        }
    
    # Validate message structure
    is_valid, error_msg = validate_summarization_trigger(data)
    if not is_valid:
        log(f"Validation error: {error_msg}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Validation failed", "details": error_msg})
        }
    
    # Extract key information
    session_id = data.get('session_id')
    trigger_reason = data.get('trigger_reason')
    current_tokens = data.get('current_tokens')
    current_messages = data.get('current_messages')
    threshold = data.get('threshold')
    
    log(f"Summarizing session {session_id}")
    log(f"Trigger reason: {trigger_reason}")
    log(f"Current: {current_messages} messages, {current_tokens} tokens")
    log(f"Threshold: {threshold}")
    
    # Retrieve conversation history from Redis
    history = get_conversation_history(session_id)  # Get all messages
    log(f"Retrieved {len(history)} messages from conversation history")
    
    if not history:
        log(f"WARNING: No conversation history found for session {session_id}")
        return {
            "statusCode": 404,
            "body": json.dumps({
                "error": "No conversation history found",
                "session_id": session_id
            })
        }
    
    # Format messages for summarization
    formatted_messages = format_messages_for_summarization(history)
    log(f"Formatted {len(formatted_messages)} messages for summarization (excluding system messages)")
    
    # Get model from environment or use default
    model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    
    # Call LLM API for summarization (TODO: Replace with actual LLM call)
    try:
        llm_response = call_llm_for_summarization(formatted_messages, model=model)
        
        summary_text = llm_response.get("summary", "")
        usage = llm_response.get("usage", {})
        
        log(f"Generated summary: {len(summary_text)} characters")
        if usage:
            log(f"Token usage: {usage.get('total_tokens', 0)} total")
        
        timestamp = utc_now_iso()
        
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
