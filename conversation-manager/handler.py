"""
Conversation Manager Handler - Workflow 3

This handler receives conversation events and LLM responses.
It validates the messages, retrieves conversation history, and formats for LLM.

Note: The actual conversation state management is handled by the connector
(which stores messages in Redis). This handler retrieves history and formats for LLM.
"""

import json
import os
from typing import Dict, Any, Optional, List
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

def format_messages_for_llm(history: List[Dict[str, Any]], current_message: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Format conversation history for LLM API.
    
    Args:
        history: Previous conversation messages from Redis
        current_message: Current user message being processed
    
    Returns:
        List of messages in LLM API format: [{"role": "user", "content": "..."}, ...]
    """
    messages = []
    
    # Add conversation history
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Skip system messages in history (they're summaries)
        if role != "system":
            messages.append({
                "role": role,
                "content": content
            })
    
    # Add current message
    current_role = current_message.get("role", "user")
    current_content = current_message.get("content", "")
    if current_role == "user":
        messages.append({
            "role": "user",
            "content": current_content
        })
    
    return messages

def call_llm_api(messages: List[Dict[str, str]], model: str = None) -> Dict[str, Any]:
    """
    Call LLM API with formatted messages.
    
    Args:
        messages: Formatted messages for LLM
        model: Model name to use (defaults to LLM_MODEL env var)
    
    Returns:
        Response from LLM API with 'content' and 'usage' fields
    
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
    # response = client.chat.completions.create(
    #     model=model,
    #     messages=messages,
    #     temperature=0.7
    # )
    # 
    # return {
    #     "content": response.choices[0].message.content,
    #     "usage": {
    #         "prompt_tokens": response.usage.prompt_tokens,
    #         "completion_tokens": response.usage.completion_tokens,
    #         "total_tokens": response.usage.total_tokens
    #     }
    # }
    # ==========================================================================
    
    # TODO: Remove this placeholder block
    log(f"[PLACEHOLDER] Would call LLM API with {len(messages)} messages, model: {model}")
    if messages:
        last_msg = messages[-1].get('content', '')
        log(f"[PLACEHOLDER] Last user message: {last_msg[:50]}...")
    
    return {
        "content": "[LLM response placeholder - implement call_llm_api()]",
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
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

def validate_conversation_event(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate conversation event message structure.
    
    Returns:
        (is_valid, error_message)
    """
    required_fields = ['session_id', 'role', 'content', 'timestamp']
    
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
    
    # Validate role
    if data['role'] not in ['user', 'assistant']:
        return False, f"Invalid role: {data['role']}. Must be 'user' or 'assistant'"
    
    # Validate session_id
    if not data['session_id']:
        return False, "session_id cannot be empty"
    
    # Validate content
    if not data.get('content'):
        return False, "content cannot be empty"
    
    return True, None

def handle(req, context):
    """
    Main handler function for conversation management.
    
    Receives conversation events or LLM responses from the connector.
    Validates the message and returns acknowledgment.
    
    Expected input format:
    {
        "event_type": "user_query" | "llm_response" (optional),
        "session_id": "uuid",
        "role": "user" | "assistant",
        "content": "message text",
        "timestamp": "ISO 8601 timestamp",
        "metadata": {
            "query_id": "optional",
            "tokens": 150,
            "model": "gpt-4"
        } (optional)
    }
    """
    log("Conversation Manager Handler Invoked")
    
    try:
        data = parse_input(req)
        log(f"Received conversation event for session: {data.get('session_id', 'unknown')}")
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
    is_valid, error_msg = validate_conversation_event(data)
    if not is_valid:
        log(f"Validation error: {error_msg}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Validation failed", "details": error_msg})
        }
    
    # Extract key information
    session_id = data.get('session_id')
    role = data.get('role')
    content = data.get('content')
    event_type = data.get('event_type', 'conversation_event')
    metadata = data.get('metadata', {})
    
    log(f"Processing {role} message for session {session_id}")
    log(f"Content length: {len(content)} characters")
    if metadata.get('tokens'):
        log(f"Token count: {metadata.get('tokens')}")
    
    # If this is a user query, retrieve history and call LLM
    if role == "user" and event_type in ["user_query", "conversation_event", None]:
        # Retrieve conversation history from Redis
        history = get_conversation_history(session_id, limit=20)  # Get last 20 messages
        log(f"Retrieved {len(history)} previous messages from conversation history")
        
        # Format messages for LLM API
        formatted_messages = format_messages_for_llm(history, data)
        log(f"Formatted {len(formatted_messages)} messages for LLM API")
        
        # Get model from metadata or use default
        model = metadata.get('model', 'gpt-3.5-turbo')
        
        # Call LLM API
        try:
            llm_response = call_llm_api(formatted_messages, model=model)
            
            response_content = llm_response.get("content", "")
            usage = llm_response.get("usage", {})
            
            log(f"LLM response generated: {len(response_content)} characters")
            if usage:
                log(f"Token usage: {usage.get('total_tokens', 0)} total")
            
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "success",
                    "session_id": session_id,
                    "role": role,
                    "event_type": event_type,
                    "message": "Conversation event processed",
                    "llm_response": {
                        "content": response_content,
                        "usage": usage
                    }
                })
            }
        except Exception as e:
            log(f"ERROR: LLM API call failed: {e}")
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "error": "LLM API call failed",
                    "details": str(e)
                })
            }
    
    # For assistant messages or other events, just acknowledge
    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "success",
            "session_id": session_id,
            "role": role,
            "event_type": event_type,
            "message": "Conversation event processed"
        })
    }
