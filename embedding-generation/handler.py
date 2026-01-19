import os
import json
import uuid
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models

def log(message):
    """Log message with flush enabled."""
    print(message, flush=True)

embedding_model = None
client = None

COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "embeddings")
VECTOR_SIZE = 384  # BGE-Small embedding size

def get_embedding_model():
    """Initialize embedding model lazily."""
    global embedding_model
    if embedding_model is None:
        log("Loading FastEmbed Model...")
        embedding_model = TextEmbedding()
    return embedding_model

def get_qdrant_client():
    """Initialize Qdrant client and collection lazily."""
    global client
    if client is not None:
        return client
    qdrant_host = os.environ.get("QDRANT_HOST", "qdrant")
    qdrant_port = int(os.environ.get("QDRANT_PORT", 6333))
    client = QdrantClient(host=qdrant_host, port=qdrant_port)
    try:
        client.get_collection(COLLECTION_NAME)
    except Exception:
        log(f"Creating collection '{COLLECTION_NAME}'...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE,
                distance=models.Distance.COSINE
            )
        )
    return client


def parse_input(req):
    """Parse input from request body."""
    if hasattr(req, 'body'):
        body = req.body
    else:
        body = req

    if isinstance(body, bytes):
        body = body.decode('utf-8')

    event = json.loads(body)

    text_content = event.get('content', '')
    file_name = event.get('file_name', 'unknown')
    chunk_index = event.get('chunk_index', 0)

    return text_content, file_name, chunk_index

def generate_embedding(text_content):
    """Generate embedding vector for text content."""
    model = get_embedding_model()
    embedding_gen = model.embed([text_content])
    vector = list(next(embedding_gen))

    if len(vector) != VECTOR_SIZE:
        log(f"Vector dimension mismatch: {len(vector)} vs {VECTOR_SIZE}")

    return vector

def upsert_to_qdrant(file_name, chunk_index, text_content, vector):
    """Upsert embedding point to Qdrant collection."""
    qdrant_client = get_qdrant_client()
    point_id = str(uuid.uuid4())
    payload = {
        "filename": file_name,
        "chunk_index": chunk_index,
        "text": text_content
    }

    upsert_result = qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload
            )
        ]
    )

    log(f"Saved chunk {chunk_index} to Qdrant.")

    return point_id

def handle(req, context):
    """Main handler function that orchestrates embedding generation and storage."""
    log("FastEmbed Handler Invoked")

    try:
        text_content, file_name, chunk_index = parse_input(req)

        if not text_content:
            return {"status": "skipped"}

    except Exception as e:
        return {"error": f"Input parse error: {e}"}

    try:
        vector = generate_embedding(text_content)
    except Exception as e:
        log(f"Embedding generation error: {e}")
        return {"error": f"Embedding generation error: {e}"}

    try:
        point_id = upsert_to_qdrant(file_name, chunk_index, text_content, vector)
    except Exception as e:
        log(f"Qdrant upsert error: {e}")
        return {"error": f"Qdrant upsert error: {e}"}

    return {"status": "success", "id": point_id}
