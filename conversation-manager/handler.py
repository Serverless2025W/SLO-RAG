"""
Conversation Manager Handler - Workflow 3

This handler receives conversation events and LLM responses.
It validates the messages and provides an interface for LLM services.

Note: The actual conversation state management is handled by the connector
(which stores messages in Redis). This handler serves as an interface/validation layer.
"""

import json
from typing import Dict, Any, Optional

def log(message):
    """Log message with flush enabled."""
    print(message, flush=True)

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
    
    # In a real implementation, this handler would:
    # - Perform additional business logic
    # - Integrate with LLM services
    # - Handle conversation context
    # 
    # For now, this is a placeholder that validates and acknowledges receipt.
    # The actual state management (storing in Redis) is handled by the connector.
    
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
