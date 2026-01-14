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
ROUTE_MAP_RAW = os.getenv("ROUTE_MAP", "text-chunks:embedding-generation")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")
BROKER = os.getenv("BROKER", "redpanda:9092")

# Parse the mapping
# Result: {'text-chunks': 'embedding-generation', 'rag-query': 'inference', ...}
ROUTES = dict(item.split(":") for item in ROUTE_MAP_RAW.split(";"))
TOPICS = list(ROUTES.keys())

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
    try:
        topic = message.topic
        payload = message.value
        
        # 1. Determine Target Function
        target_function = ROUTES.get(topic)
        if not target_function:
            log(f"Warning: No route defined for topic {topic}")
            continue
        log(f"Received: [{topic}] -> [{target_function}] payload={payload[:50]}...")
        
        # 2. Invoke Function
        url = f"{GATEWAY_URL}/function/{target_function}"
        response = requests.post(url, data=payload)
        
        log(f"Invoked {target_function}: {response.status_code}")
        
    except Exception as e:
        log(f"Error forwarding message: {str(e)}")