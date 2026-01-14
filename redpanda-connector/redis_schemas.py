"""
Redis data structure definitions for Workflows 3 & 4.

These schemas define how conversation state is stored in Redis.
The connector uses these structures to manage conversation history,
token counts, and session metadata.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import json


@dataclass
class ConversationMessage:
    """Single message in a conversation history."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str  # ISO 8601 format
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationMessage':
        """Create from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data["timestamp"]
        )
    
    def to_json(self) -> str:
        """Serialize to JSON string for Redis storage."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ConversationMessage':
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class SessionMetadata:
    """Metadata stored for each session."""
    created_at: str  # ISO 8601 format
    last_activity: str  # ISO 8601 format
    message_count: int
    token_count: int  # Total tokens in conversation
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "message_count": self.message_count,
            "token_count": self.token_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionMetadata':
        """Create from dictionary."""
        return cls(
            created_at=data.get("created_at", ""),
            last_activity=data.get("last_activity", ""),
            message_count=int(data.get("message_count", 0)),
            token_count=int(data.get("token_count", 0))
        )
    
    def to_redis_hash(self) -> Dict[str, str]:
        """Convert to Redis hash format (all values as strings)."""
        return {
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "message_count": str(self.message_count),
            "token_count": str(self.token_count)
        }
    
    @classmethod
    def from_redis_hash(cls, hash_data: Dict[str, str]) -> 'SessionMetadata':
        """Create from Redis hash."""
        return cls(
            created_at=hash_data.get("created_at", ""),
            last_activity=hash_data.get("last_activity", ""),
            message_count=int(hash_data.get("message_count", "0")),
            token_count=int(hash_data.get("token_count", "0"))
        )


class RedisKeyPatterns:
    """Redis key patterns for conversation state management."""
    
    @staticmethod
    def conversation_history(session_id: str) -> str:
        """Key for conversation message list (Redis List)."""
        return f"conversation:{session_id}"
    
    @staticmethod
    def session_tokens(session_id: str) -> str:
        """Key for session token count (Redis String/Integer)."""
        return f"session:{session_id}:tokens"
    
    @staticmethod
    def session_metadata(session_id: str) -> str:
        """Key for session metadata (Redis Hash)."""
        return f"session:{session_id}:meta"
    
    @staticmethod
    def query_embedding_cache(query_hash: str) -> str:
        """Key for query embedding cache (Redis String)."""
        return f"query:embedding:{query_hash}"


class RedisConversationStore:
    """
    Interface for Redis conversation storage operations.
    
    This class defines the expected Redis operations for conversation
    state management. The connector implements these operations.
    """
    
    # Key patterns (for reference)
    CONVERSATION_TTL = 86400  # 24 hours in seconds
    
    @staticmethod
    def store_message(redis_client, session_id: str, message: ConversationMessage, ttl: int = CONVERSATION_TTL) -> None:
        """
        Store a message in conversation history.
        
        Args:
            redis_client: Redis client instance
            session_id: Session identifier
            message: Message to store
            ttl: Time-to-live in seconds
        """
        key = RedisKeyPatterns.conversation_history(session_id)
        redis_client.rpush(key, message.to_json())
        redis_client.expire(key, ttl)
    
    @staticmethod
    def get_messages(redis_client, session_id: str, limit: Optional[int] = None) -> List[ConversationMessage]:
        """
        Retrieve messages from conversation history.
        
        Args:
            redis_client: Redis client instance
            session_id: Session identifier
            limit: Maximum number of messages to retrieve (None = all)
        
        Returns:
            List of ConversationMessage objects
        """
        key = RedisKeyPatterns.conversation_history(session_id)
        if limit:
            messages = redis_client.lrange(key, -limit, -1)
        else:
            messages = redis_client.lrange(key, 0, -1)
        
        return [ConversationMessage.from_json(msg) for msg in messages]
    
    @staticmethod
    def update_token_count(redis_client, session_id: str, tokens: int, ttl: int = CONVERSATION_TTL) -> int:
        """
        Update session token count.
        
        Args:
            redis_client: Redis client instance
            session_id: Session identifier
            tokens: Tokens to add (can be negative)
        
        Returns:
            New token count
        """
        key = RedisKeyPatterns.session_tokens(session_id)
        new_count = redis_client.incrby(key, tokens)
        redis_client.expire(key, ttl)
        return new_count
    
    @staticmethod
    def get_token_count(redis_client, session_id: str) -> int:
        """
        Get current token count for session.
        
        Args:
            redis_client: Redis client instance
            session_id: Session identifier
        
        Returns:
            Current token count (0 if not set)
        """
        key = RedisKeyPatterns.session_tokens(session_id)
        result = redis_client.get(key)
        return int(result) if result else 0
    
    @staticmethod
    def update_session_metadata(redis_client, session_id: str, metadata: SessionMetadata, ttl: int = CONVERSATION_TTL) -> None:
        """
        Update session metadata.
        
        Args:
            redis_client: Redis client instance
            session_id: Session identifier
            metadata: Metadata to store
            ttl: Time-to-live in seconds
        """
        key = RedisKeyPatterns.session_metadata(session_id)
        redis_client.hset(key, mapping=metadata.to_redis_hash())
        redis_client.expire(key, ttl)
    
    @staticmethod
    def get_session_metadata(redis_client, session_id: str) -> Optional[SessionMetadata]:
        """
        Get session metadata.
        
        Args:
            redis_client: Redis client instance
            session_id: Session identifier
        
        Returns:
            SessionMetadata if exists, None otherwise
        """
        key = RedisKeyPatterns.session_metadata(session_id)
        hash_data = redis_client.hgetall(key)
        if not hash_data:
            return None
        return SessionMetadata.from_redis_hash(hash_data)
    
    @staticmethod
    def get_message_count(redis_client, session_id: str) -> int:
        """
        Get number of messages in conversation.
        
        Args:
            redis_client: Redis client instance
            session_id: Session identifier
        
        Returns:
            Number of messages
        """
        key = RedisKeyPatterns.conversation_history(session_id)
        return redis_client.llen(key)
    
    @staticmethod
    def reset_session(redis_client, session_id: str) -> None:
        """
        Reset session state (clear messages, tokens, metadata).
        
        Args:
            redis_client: Redis client instance
            session_id: Session identifier
        """
        keys = [
            RedisKeyPatterns.conversation_history(session_id),
            RedisKeyPatterns.session_tokens(session_id),
            RedisKeyPatterns.session_metadata(session_id)
        ]
        for key in keys:
            redis_client.delete(key)
    
    @staticmethod
    def replace_conversation_with_summary(redis_client, session_id: str, summary_message: ConversationMessage, ttl: int = CONVERSATION_TTL) -> None:
        """
        Replace conversation history with a summary message.
        
        Used after summarization to replace old messages with a summary.
        
        Args:
            redis_client: Redis client instance
            session_id: Session identifier
            summary_message: Summary message to store
            ttl: Time-to-live in seconds
        """
        key = RedisKeyPatterns.conversation_history(session_id)
        # Delete old messages
        redis_client.delete(key)
        # Store summary
        redis_client.rpush(key, summary_message.to_json())
        redis_client.expire(key, ttl)
