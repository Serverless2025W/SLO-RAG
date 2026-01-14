"""
Message schema definitions for Kafka topics used in Workflows 3 & 4.

These schemas define the expected message formats that LLM services
will send to the connector. The connector validates and processes
these messages according to these interfaces.
"""

from typing import Dict, Any, Optional, Literal
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class ConversationEventMetadata:
    """Metadata for conversation events."""
    query_id: Optional[str] = None
    tokens: int = 0
    model: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query_id": self.query_id,
            "tokens": self.tokens,
            "model": self.model
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationEventMetadata':
        """Create from dictionary."""
        return cls(
            query_id=data.get("query_id"),
            tokens=data.get("tokens", 0),
            model=data.get("model")
        )


@dataclass
class ConversationEvent:
    """
    Schema for conversation-events topic.
    
    Published by LLM service when user sends a query.
    """
    event_type: Literal["user_query", "llm_response"]
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    timestamp: str  # ISO 8601 format
    metadata: Optional[ConversationEventMetadata] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp
        }
        if self.metadata:
            result["metadata"] = self.metadata.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationEvent':
        """Create from dictionary."""
        metadata = None
        if "metadata" in data and data["metadata"]:
            metadata = ConversationEventMetadata.from_dict(data["metadata"])
        
        return cls(
            event_type=data["event_type"],
            session_id=data["session_id"],
            role=data["role"],
            content=data["content"],
            timestamp=data["timestamp"],
            metadata=metadata
        )
    
    def validate(self) -> bool:
        """Validate message structure."""
        if self.event_type not in ["user_query", "llm_response"]:
            return False
        if self.role not in ["user", "assistant"]:
            return False
        if not self.session_id:
            return False
        if not self.content:
            return False
        return True


@dataclass
class LLMResponseEvent:
    """
    Schema for llm-responses topic.
    
    Published by LLM service after generating a response.
    """
    session_id: str
    role: Literal["assistant"]
    content: str
    timestamp: str  # ISO 8601 format
    metadata: Optional[ConversationEventMetadata] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp
        }
        if self.metadata:
            result["metadata"] = self.metadata.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMResponseEvent':
        """Create from dictionary."""
        metadata = None
        if "metadata" in data and data["metadata"]:
            metadata = ConversationEventMetadata.from_dict(data["metadata"])
        
        return cls(
            session_id=data["session_id"],
            role=data["role"],
            content=data["content"],
            timestamp=data["timestamp"],
            metadata=metadata
        )
    
    def validate(self) -> bool:
        """Validate message structure."""
        if self.role != "assistant":
            return False
        if not self.session_id:
            return False
        if not self.content:
            return False
        return True


@dataclass
class SummarizationTrigger:
    """
    Schema for summarization-triggers topic.
    
    Published by connector when thresholds are reached.
    Consumed by context-summarizer function.
    """
    session_id: str
    trigger_reason: Literal["token_threshold", "message_threshold", "manual"]
    current_tokens: int
    current_messages: int
    threshold: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "trigger_reason": self.trigger_reason,
            "current_tokens": self.current_tokens,
            "current_messages": self.current_messages,
            "threshold": self.threshold
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SummarizationTrigger':
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            trigger_reason=data["trigger_reason"],
            current_tokens=data["current_tokens"],
            current_messages=data["current_messages"],
            threshold=data["threshold"]
        )
    
    def validate(self) -> bool:
        """Validate message structure."""
        if self.trigger_reason not in ["token_threshold", "message_threshold", "manual"]:
            return False
        if not self.session_id:
            return False
        if self.current_tokens < 0 or self.current_messages < 0:
            return False
        return True


# Example message payloads for reference (for LLM implementers)

EXAMPLE_CONVERSATION_EVENT = {
    "event_type": "user_query",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "role": "user",
    "content": "What is the weather like today?",
    "timestamp": "2026-01-12T20:00:00Z",
    "metadata": {
        "query_id": "query-123",
        "tokens": 10,
        "model": "gpt-4"
    }
}

EXAMPLE_LLM_RESPONSE = {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "role": "assistant",
    "content": "The weather today is sunny with a high of 75°F.",
    "timestamp": "2026-01-12T20:00:01Z",
    "metadata": {
        "query_id": "query-123",
        "tokens": 150,
        "model": "gpt-4"
    }
}

EXAMPLE_SUMMARIZATION_TRIGGER = {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "trigger_reason": "token_threshold",
    "current_tokens": 4500,
    "current_messages": 25,
    "threshold": 4000
}
