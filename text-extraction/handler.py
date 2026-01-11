import os
import json
import io
from minio import Minio
from PyPDF2 import PdfReader
from kafka import KafkaProducer

minio_client = None
kafka_producer = None

CHUNK_SIZE = int(os.environ.get('CHUNK_SIZE', '1000'))
REDPANDA_BROKER = os.environ.get('REDPANDA_BROKER', 'redpanda:9092')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'text-chunks')

def log(message):
    """Log message with flush enabled."""
    print(message, flush=True)

def get_minio_client():
    """Get existing MinIO client or create a new one."""
    global minio_client
    if minio_client is None:
        log("Initializing MinIO client...")
        endpoint = os.environ['MINIO_ENDPOINT']
        secure = False
        if endpoint.startswith("https://"):
            secure = True
            endpoint = endpoint.replace("https://", "")
        elif endpoint.startswith("http://"):
            endpoint = endpoint.replace("http://", "")
            
        minio_client = Minio(
            endpoint,
            access_key=os.environ['MINIO_ACCESS_KEY'],
            secret_key=os.environ['MINIO_SECRET_KEY'],
            secure=secure
        )
    return minio_client

def get_kafka_producer():
    """Get existing Kafka producer or create a new one."""
    global kafka_producer
    if kafka_producer is None:
        log(f"Initializing Redpanda producer at {REDPANDA_BROKER}...")
        try:
            kafka_producer = KafkaProducer(
                bootstrap_servers=[REDPANDA_BROKER],
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                request_timeout_ms=5000
            )
        except Exception as e:
            log(f"FAILED to connect to Redpanda: {e}")
            raise e
    return kafka_producer

def extract_text_from_pdf(file_data):
    try:
        reader = PdfReader(io.BytesIO(file_data))
        text = ""
        for page in reader.pages:
            text_extracted = page.extract_text()
            if text_extracted:
                text += text_extracted + "\n"
        return text
    except Exception as e:
        return f"Error reading PDF: {str(e)}"

def chunk_text(text, size):
    """Yield successive chunks of size."""
    if not text:
        return []
    for i in range(0, len(text), size):
        yield text[i:i + size]

def parse_webhook_event(raw_body):
    """Parse MinIO webhook event and extract bucket and file information."""
    import urllib.parse
    
    if isinstance(raw_body, bytes):
        body_str = raw_body.decode('utf-8')
    else:
        body_str = raw_body
        
    webhook_data = json.loads(body_str)
    
    if 'Records' not in webhook_data:
        raise ValueError("Not a valid MinIO event")
        
    record = webhook_data['Records'][0]
    bucket_name = record['s3']['bucket']['name']
    file_key = urllib.parse.unquote_plus(record['s3']['object']['key'])
    
    return record, bucket_name, file_key

def download_file_from_minio(bucket_name, file_key):
    """Download file from MinIO bucket."""
    client = get_minio_client()
    response = client.get_object(bucket_name, file_key)
    file_data = response.read()
    response.close()
    response.release_conn()
    return file_data

def extract_text(file_key, file_data):
    """Extract text from file based on file type."""
    if file_key.lower().endswith('.pdf'):
        return extract_text_from_pdf(file_data)
    else:
        return file_data.decode('utf-8', errors='ignore')

def publish_chunks_to_redpanda(file_key, bucket_name, chunks, event_time):
    """Publish text chunks to Redpanda topic."""
    producer = get_kafka_producer()
    total_chunks = len(chunks)
    
    log(f"Split text into {total_chunks} chunks (Size: {CHUNK_SIZE})")
    
    for index, chunk_content in enumerate(chunks):
        message = {
            "file_name": file_key,
            "bucket": bucket_name,
            "chunk_index": index,
            "total_chunks": total_chunks,
            "content": chunk_content,
            "timestamp": event_time
        }
        producer.send(KAFKA_TOPIC, value=message)
    
    producer.flush()
    log(f"Successfully published {total_chunks} chunks to topic '{KAFKA_TOPIC}'")
    
    return total_chunks

def handle(req, context):
    """Main handler function that orchestrates text extraction and publishing."""
    try:
        raw_body = req.body if hasattr(req, 'body') else req
        record, bucket_name, file_key = parse_webhook_event(raw_body)
        log(f"Processing file: {file_key} from bucket: {bucket_name}")
    except Exception as e:
        log(f"Error parsing event: {e}")
        return {"statusCode": 500, "body": f"Error parsing event: {str(e)}"}

    try:
        file_data = download_file_from_minio(bucket_name, file_key)
    except Exception as e:
        log(f"MinIO Download Error: {e}")
        return {"statusCode": 500, "body": f"Failed to fetch file: {str(e)}"}

    try:
        extracted_text = extract_text(file_key, file_data)
        
        if not extracted_text:
            log("Warning: No text extracted.")
            return {"statusCode": 200, "body": "No text content found"}
    except Exception as e:
        log(f"Text Extraction Error: {e}")
        return {"statusCode": 500, "body": f"Failed to extract text: {str(e)}"}

    try:
        chunks = list(chunk_text(extracted_text, CHUNK_SIZE))
        total_chunks = publish_chunks_to_redpanda(file_key, bucket_name, chunks, record['eventTime'])
    except Exception as e:
        log(f"Redpanda Publish Error: {e}")
        return {"statusCode": 500, "body": f"Failed to publish to Redpanda: {str(e)}"}

    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "success", 
            "file": file_key,
            "chunks_processed": total_chunks
        })
    }