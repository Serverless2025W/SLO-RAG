import os
import json
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


def build_inference_payload(query, results):
    """Build a minimal payload for LLM inference."""
    context_chunks = [chunk['text'] for chunk in results]

    return {
        "query": query,
        "context": context_chunks
    }


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

    try:
        results = search_similar(query_vector)
        formatted = format_results(results)
        log(f"Retrieved {len(formatted)} chunks")

        for i, chunk in enumerate(formatted):
            log(f"--- Result {i+1} (score: {chunk['score']:.4f}) ---")
            log(f"File: {chunk['filename']}, Chunk: {chunk['chunk_index']}")
            log(f"Text: {chunk['text'][:200]}...")

        payload = build_inference_payload(query, formatted)

        return json.dumps(payload)
    except Exception as e:
        log(f"Search error: {e}")
        return json.dumps({"error": f"Search error: {e}"})
