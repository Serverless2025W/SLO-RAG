"""
Context Summarizer Handler - Workflow 4

This handler receives summarization trigger events and generates summaries
of conversation history when thresholds are exceeded.

Note: Since LLMs are not included, this returns a placeholder summary.
In a real implementation, this would use an LLM to summarize the conversation.
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone

def log(message):
    """Log message with flush enabled."""
    print(message, flush=True)

def utc_now_iso() -> str:
    """Return UTC timestamp in ISO 8601 with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

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

def generate_summary_placeholder(session_id: str, trigger_reason: str, message_count: int, token_count: int) -> str:
    """
    Generate a placeholder summary (for testing).
    
    In a real implementation, this would:
    1. Retrieve conversation history from Redis
    2. Use an LLM to generate a concise summary
    3. Return the summary text
    
    Args:
        session_id: Session identifier
        trigger_reason: Reason for summarization
        message_count: Number of messages in conversation
        token_count: Total tokens in conversation
    
    Returns:
        Summary text (placeholder)
    """
    return f"Conversation summary for session {session_id}. " \
           f"Triggered by {trigger_reason}. " \
           f"Compressed {message_count} messages ({token_count} tokens) " \
           f"into a summary."

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
    
    # In a real implementation, this handler would:
    # 1. Retrieve conversation history from Redis (via connector or direct access)
    # 2. Use an LLM service to generate a summary
    # 3. Return the summary text
    #
    # For now, this returns a placeholder summary.
    # The connector will replace the conversation history with this summary.
    
    summary_text = generate_summary_placeholder(
        session_id, trigger_reason, current_messages, current_tokens
    )
    
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
            }
        })
    }
