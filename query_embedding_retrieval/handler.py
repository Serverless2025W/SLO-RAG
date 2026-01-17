import os
import json
import requests
import threading
from datetime import datetime, timezone
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
import redis

def log(message):
    print(message, flush=True)

# Redis configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)
CONVERSATION_TTL = int(os.environ.get("CONVERSATION_TTL", 86400))  # 24 hours

# Lazy Redis client initialization
_redis_client = None

def get_redis_client():
    """Get or create Redis client with lazy initialization."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            _redis_client.ping()
            log("Redis client connected successfully")
        except redis.ConnectionError as e:
            log(f"Redis connection failed: {e}")
            _redis_client = None
    return _redis_client

log("Loading FastEmbed Model...")
embedding_model = TextEmbedding()

QDRANT_HOST = os.environ.get("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", 6333))
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "embeddings")
TOP_K = int(os.environ.get("TOP_K", 5))

ROUTER_URL = os.environ.get("ROUTER_URL", "http://gateway:8080/function/router")

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

    if isinstance(body, bytes):
        body = body.decode('utf-8')

    event = json.loads(body)
    query = event.get('query', '')
    session_id = event.get('session_id', None)

    return query, session_id


def generate_embedding(text):
    embedding_gen = embedding_model.embed([text])
    vector = [float(x) for x in next(embedding_gen)]
    return vector


def search_similar(query_vector, top_k=TOP_K):
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


def format_prompt(query, results):
    """Format the RAG prompt with query and retrieved context."""
    if results:
        context_text = "\n\n".join([chunk['text'] for chunk in results])
    else:
        context_text = "No relevant context found."

    return PROMPT_TEMPLATE.format(context=context_text, query=query)


def call_router(prompt):
    """Send the formatted prompt to the router for inference."""
    try:
        response = requests.post(ROUTER_URL, data=prompt, timeout=120)
        return response.text, response.headers.get("X-Routing-Target", "unknown")
    except requests.exceptions.RequestException as e:
        log(f"Router call failed: {e}")
        raise


def store_message_to_redis(session_id: str, role: str, content: str):
    """Store a message to Redis conversation history.

    Args:
        session_id: The session identifier for the conversation
        role: Message role ('user' or 'assistant')
        content: The message content
    """
    try:
        client = get_redis_client()
        if client is None:
            log(f"Cannot store message: Redis client unavailable")
            return False

        timestamp = datetime.now(timezone.utc).isoformat()
        message_data = {
            "role": role,
            "content": content,
            "timestamp": timestamp
        }

        conversation_key = f"conversation:{session_id}"
        client.rpush(conversation_key, json.dumps(message_data))
        client.expire(conversation_key, CONVERSATION_TTL)

        log(f"Stored {role} message for session {session_id}")
        return True
    except Exception as e:
        log(f"Error storing message to Redis: {e}")
        return False


def store_conversation_async(session_id: str, user_query: str, assistant_response: str):
    """Asynchronously store both user query and assistant response to Redis.

    This function runs in a background thread to avoid blocking the response.

    Args:
        session_id: The session identifier for the conversation
        user_query: The user's original query
        assistant_response: The model's generated response
    """
    def _store():
        try:
            # Store user message
            store_message_to_redis(session_id, "user", user_query)
            # Store assistant response
            store_message_to_redis(session_id, "assistant", assistant_response)
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
        log(f"Retrieved {len(formatted)} chunks")

        for i, chunk in enumerate(formatted):
            log(f"--- Result {i+1} (score: {chunk['score']:.4f}) ---")
            log(f"File: {chunk['filename']}, Chunk: {chunk['chunk_index']}")
            log(f"Text: {chunk['text'][:200]}...")
    except Exception as e:
        log(f"Search error (continuing without context): {e}")

    # Format prompt and call router for inference
    try:
        prompt = format_prompt(query, formatted)
        log(f"Formatted prompt ({len(prompt)} chars), calling router...")

        answer, backend = call_router(prompt)
        log(f"Got response from {backend}")

        # Store conversation to Redis asynchronously if session_id is provided
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
