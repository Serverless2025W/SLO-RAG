import os
import json
import requests
import threading
from datetime import datetime, timezone
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from kafka import KafkaProducer

def log(message):
    print(message, flush=True)

log("Loading FastEmbed Model...")
embedding_model = TextEmbedding()

QDRANT_HOST = os.environ.get("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", 6333))
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "embeddings")
TOP_K = int(os.environ.get("TOP_K", 5))

ROUTER_URL = os.environ.get("ROUTER_URL", "http://gateway:8080/function/router")
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
    try:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        message_data = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": timestamp
        }

        producer = get_kafka_producer()
        if producer is None:
            log(f"WARNING: Cannot store message - Kafka producer unavailable")
            return False

        future = producer.send(CONVERSATION_EVENTS_TOPIC, message_data)
        future.get(timeout=10)  # Wait for message to be sent
        
        log(f"Stored {role} message for session {session_id} via Kafka (topic: {CONVERSATION_EVENTS_TOPIC})")
        return True
    except Exception as e:
        log(f"Error storing message via Kafka: {e}")
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
