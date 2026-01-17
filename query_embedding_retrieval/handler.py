import os
import json
import requests
from fastembed import TextEmbedding
from qdrant_client import QdrantClient

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

    return query


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


def handle(req, context):
    log("Query Embedding Retrieval Handler Invoked")

    try:
        query = parse_input(req)
        if not query:
            return json.dumps({"error": "No query provided"})
        log(f"Query: {query}")
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
