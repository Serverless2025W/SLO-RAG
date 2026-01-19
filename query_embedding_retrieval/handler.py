import os
import json
import requests
import threading
from datetime import datetime, timezone
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models
from kafka import KafkaProducer

def log(message):
    print(message, flush=True)

log("Loading FastEmbed Model...")
embedding_model = TextEmbedding()

QDRANT_HOST = os.environ.get("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", 6333))
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "embeddings")
VECTOR_SIZE = 384  # BGE-Small embedding size

# Lazy client initialization
_qdrant_client = None

def get_qdrant_client():
    """Initialize Qdrant client and ensure collection exists."""
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client

    _qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Ensure collection exists
    try:
        _qdrant_client.get_collection(COLLECTION_NAME)
        log(f"Collection '{COLLECTION_NAME}' exists")
    except Exception:
        log(f"Creating collection '{COLLECTION_NAME}'...")
        _qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE,
                distance=models.Distance.COSINE
            )
        )
        log(f"Collection '{COLLECTION_NAME}' created successfully")

    return _qdrant_client

TOP_K = int(os.environ.get("TOP_K", 5))

ROUTER_URL = os.environ.get("ROUTER_URL", "http://gateway:8080/function/router")
CONVERSATION_MANAGER_URL = os.environ.get("CONVERSATION_MANAGER_URL", "http://gateway:8080/function/conversation-manager")
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "redpanda:9092")
CONVERSATION_EVENTS_TOPIC = os.environ.get("CONVERSATION_EVENTS_TOPIC", "conversation-events")

# Lazy Kafka producer initialization
kafka_producer = None

DEFAULT_PROMPT_TEMPLATE = """Answer the question based on the context below. If the context doesn't contain relevant information, answer based on your general knowledge.

Context:
{context}

Question: {query}

Answer:"""

PROMPT_TEMPLATE = os.environ.get("PROMPT_TEMPLATE", DEFAULT_PROMPT_TEMPLATE)

BACKEND_TO_MODEL = {
    "local-inference": "Llama-3.2-1B-Instruct",
    "remote-inference": "Llama-3.3-70B-Versatile (Groq)",
    "unknown": "Unknown"
}


def parse_input(req):
    if hasattr(req, 'body'):
        body = req.body
    else:
        body = req

    # If body is already a dict, use it directly
    if isinstance(body, dict):
        event = body
    elif isinstance(body, bytes):
        body = body.decode('utf-8')
        event = json.loads(body)
    else:
        # Assume it's a string
        event = json.loads(body)
    
    query = event.get('query', '')
    session_id = event.get('session_id', None)

    return query, session_id


def generate_embedding(text):
    embedding_gen = embedding_model.embed([text])
    vector = [float(x) for x in next(embedding_gen)]
    return vector


def search_similar(query_vector, top_k=TOP_K):
    client = get_qdrant_client()
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k
    )
    return results.points


def format_results(results):
    formatted = []
    for result in results:
        formatted.append({
            "score": float(result.score),
            "text": result.payload.get("text", ""),
            "filename": result.payload.get("filename", ""),
            "chunk_index": result.payload.get("chunk_index", 0)
        })
    return formatted


def get_conversation_history(session_id: str):
    """Fetch conversation history from conversation-manager."""
    if not session_id:
        return []
    
    try:
        response = requests.post(
            CONVERSATION_MANAGER_URL,
            json={
                "action": "get_history",
                "session_id": session_id
            },
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            # Handle different response formats
            messages = data.get('messages', [])
            if not messages and data.get('body'):
                body = data['body']
                if isinstance(body, str):
                    body = json.loads(body)
                messages = body.get('messages', [])
            
            # Filter out system messages (summaries) for context, but keep user/assistant
            conversation_messages = [msg for msg in messages if msg.get('role') in ['user', 'assistant']]
            log(f"Retrieved {len(conversation_messages)} conversation messages for context")
            return conversation_messages
        else:
            log(f"Failed to fetch conversation history: {response.status_code}")
            return []
    except Exception as e:
        log(f"Warning: Could not fetch conversation history: {e}")
        return []


def format_prompt(query, results, conversation_history=None):
    """Format the RAG prompt with query, retrieved context, and conversation history."""
    # Format context from vector DB
    if results:
        context_text = "\n\n".join([chunk['text'] for chunk in results])
    else:
        context_text = "No relevant context found."
    
    # Format conversation history if available
    conversation_context = ""
    if conversation_history:
        conv_lines = []
        for msg in conversation_history[-10:]:  # Last 10 messages for context
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'user':
                conv_lines.append(f"User: {content}")
            elif role == 'assistant':
                conv_lines.append(f"Assistant: {content}")
        if conv_lines:
            conversation_context = "\n\nPrevious Conversation:\n" + "\n".join(conv_lines)
    
    # Combine context and conversation history
    full_context = context_text + conversation_context
    
    return PROMPT_TEMPLATE.format(context=full_context, query=query)


def call_router(prompt):
    """Send the formatted prompt to the router for inference."""
    try:
        response = requests.post(ROUTER_URL, data=prompt, timeout=120)
        return response.text, response.headers.get("X-Routing-Target", "unknown")
    except requests.exceptions.RequestException as e:
        log(f"Router call failed: {e}")
        raise


def get_kafka_producer():
    """Get or create Kafka producer with lazy initialization."""
    global kafka_producer
    if kafka_producer is not None:
        return kafka_producer
    
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BROKER,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            retries=3
        )
        kafka_producer = producer
        log(f"Connected to Kafka at {KAFKA_BROKER}")
        return kafka_producer
    except Exception as e:
        log(f"WARNING: Could not connect to Kafka: {e}")
        return None


def store_message_via_conversation_manager(session_id: str, role: str, content: str):
    """Store a message via conversation-manager service using Kafka.

    Args:
        session_id: The session identifier for the conversation
        role: Message role ('user' or 'assistant')
        content: The message content
    """
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    message_data = {
        "session_id": session_id,
        "role": role,
        "content": content,
        "timestamp": timestamp
    }
    try:
        producer = get_kafka_producer()
        if producer is not None:
            future = producer.send(CONVERSATION_EVENTS_TOPIC, message_data)
            future.get(timeout=10)  # Wait for message to be sent
            log(f"Stored {role} message for session {session_id} via Kafka (topic: {CONVERSATION_EVENTS_TOPIC})")
            return True
        log("WARNING: Kafka producer unavailable, falling back to direct HTTP storage")
    except Exception as e:
        log(f"Error storing message via Kafka: {e}")

    try:
        response = requests.post(CONVERSATION_MANAGER_URL, json=message_data, timeout=5)
        if response.status_code == 200:
            log(f"Stored {role} message for session {session_id} via HTTP")
            return True
        log(f"WARNING: HTTP storage failed: {response.status_code} {response.text[:200]}")
        return False
    except Exception as e:
        log(f"Error storing message via HTTP: {e}")
        return False


def store_conversation_async(session_id: str, user_query: str, assistant_response: str):
    """Asynchronously store both user query and assistant response via conversation-manager.

    This function runs in a background thread to avoid blocking the response.

    Args:
        session_id: The session identifier for the conversation
        user_query: The user's original query
        assistant_response: The model's generated response
    """
    def _store():
        try:
            # Store user message
            store_message_via_conversation_manager(session_id, "user", user_query)
            # Store assistant response
            store_message_via_conversation_manager(session_id, "assistant", assistant_response)
            log(f"Async storage complete for session {session_id}")
        except Exception as e:
            log(f"Async storage failed: {e}")

    thread = threading.Thread(target=_store, daemon=True)
    thread.start()
    log(f"Started async storage thread for session {session_id}")


def handle(req, context):
    log("Query Embedding Retrieval Handler Invoked")

    try:
        query, session_id = parse_input(req)
        if not query:
            return json.dumps({"error": "No query provided"})
        log(f"Query: {query}")
        if session_id:
            log(f"Session ID: {session_id}")
    except Exception as e:
        return json.dumps({"error": f"Input parse error: {e}"})

    try:
        query_vector = generate_embedding(query)
        log(f"Generated embedding with {len(query_vector)} dimensions")
    except Exception as e:
        log(f"Embedding generation error: {e}")
        return json.dumps({"error": f"Embedding generation error: {e}"})

    # Retrieve context from vector DB
    formatted = []
    try:
        results = search_similar(query_vector)
        formatted = format_results(results)
        log(f"Retrieved {len(formatted)} chunks from vector DB")

        for i, chunk in enumerate(formatted):
            log(f"--- Result {i+1} (score: {chunk['score']:.4f}) ---")
            log(f"File: {chunk['filename']}, Chunk: {chunk['chunk_index']}")
            log(f"Text: {chunk['text'][:200]}...")
    except Exception as e:
        log(f"Search error (continuing without context): {e}")

    # Retrieve conversation history if session_id is provided
    conversation_history = []
    if session_id:
        try:
            conversation_history = get_conversation_history(session_id)
            if conversation_history:
                log(f"Using {len(conversation_history)} conversation messages for context")
        except Exception as e:
            log(f"Warning: Could not retrieve conversation history: {e}")

    # Format prompt and call router for inference
    try:
        prompt = format_prompt(query, formatted, conversation_history)
        log(f"Formatted prompt ({len(prompt)} chars), calling router...")

        answer, backend = call_router(prompt)
        log(f"Got response from {backend}")

        # Store conversation via conversation-manager asynchronously if session_id is provided
        if session_id:
            store_conversation_async(session_id, query, answer)

        model_name = BACKEND_TO_MODEL.get(backend, backend)
        return json.dumps({
            "answer": answer,
            "model": model_name,
            "sources": [
                {
                    "filename": chunk["filename"],
                    "chunk_index": chunk["chunk_index"],
                    "score": chunk["score"],
                    "text": chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"]
                }
                for chunk in formatted
            ]
        })
    except Exception as e:
        log(f"Inference error: {e}")
        return json.dumps({"error": f"Inference error: {e}"})
