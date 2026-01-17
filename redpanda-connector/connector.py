import os
import json
import requests
from kafka import KafkaConsumer
import sys
import threading

def log(msg):
    print(msg, flush=True)

# Configuration: Map Topics to Function Names
# Format: "topic_name:function_name;topic2:function2;..."
# Default includes all topics for Workflows 1, 3, and 4
ROUTE_MAP_RAW = os.getenv(
    "ROUTE_MAP", 
    "text-chunks:embedding-generation;conversation-events:conversation-manager;llm-responses:conversation-manager;summarization-triggers:context-summarizer"
)
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")
BROKER = os.getenv("BROKER", "redpanda:9092")

# Parse the mapping
# Result: {'text-chunks': 'embedding-generation', 'conversation-events': 'conversation-manager', ...}
ROUTES = dict(item.split(":") for item in ROUTE_MAP_RAW.split(";"))
TOPICS = list(ROUTES.keys())

def get_target_function(topic: str) -> str:
    """Get target function name for a topic."""
    # Return the mapped function or default to embedding-generation for unknown topics
    return ROUTES.get(topic, "embedding-generation")

def invoke_function(function_name: str, data: dict) -> dict:
    """
    Invoke OpenFaaS function via HTTP.
    
    Args:
        function_name: Name of the function to invoke
        data: JSON payload to send
    
    Returns:
        Response data as dict, or None on failure
    """
    url = f"{GATEWAY_URL}/function/{function_name}"
    try:
        response = requests.post(url, json=data, timeout=60)
        
        if response.status_code == 200:
            log(f"Successfully invoked {function_name}: HTTP {response.status_code}")
            try:
                return response.json()
            except:
                return {"text": response.text}
        else:
            log(f"ERROR: {function_name} returned HTTP {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        log(f"ERROR: Failed to invoke {function_name}: {e}")
        return None

def process_message(message) -> None:
    """
    Process a single Kafka message by routing to the appropriate function.
    """
    topic = message.topic
    try:
        # Parse message value (may be string from deserializer or bytes)
        payload = message.value
        if isinstance(payload, str):
            data = json.loads(payload)
        elif isinstance(payload, bytes):
            data = json.loads(payload.decode('utf-8'))
        else:
            data = payload
        
        # Determine Target Function
        target_function = get_target_function(topic)
        if not target_function:
            log(f"Warning: No route defined for topic {topic}")
            return
        
        log(f"Received: [{topic}] -> [{target_function}] payload={str(data)[:50]}...")
        
        # Invoke Function
        result = invoke_function(target_function, data)
        
        if result:
            log(f"Function {target_function} completed successfully")
        else:
            log(f"WARNING: Function {target_function} returned no result")
        
    except json.JSONDecodeError as e:
        log(f"ERROR: Failed to parse JSON payload: {e}")
    except Exception as e:
        log(f"Error forwarding message: {str(e)}")

log(f"--- Redpanda Connector Router Starting ---")
log(f"Broker: {BROKER}")
log(f"Routing Map: {json.dumps(ROUTES, indent=2)}")

try:
    consumer = KafkaConsumer(
        bootstrap_servers=BROKER,
        auto_offset_reset='latest',
        enable_auto_commit=True,
        group_id='rag-connector-group',
        value_deserializer=lambda x: x.decode('utf-8')
    )
    # Subscribe to ALL topics in our map
    consumer.subscribe(topics=TOPICS)
    log(f"Subscribed to topics: {TOPICS}")
except Exception as e:
    log(f"CRITICAL: Could not connect to Redpanda: {e}")
    sys.exit(1)

for message in consumer:
    process_message(message)
