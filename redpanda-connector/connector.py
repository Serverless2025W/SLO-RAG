import os
import json
import requests
from kafka import KafkaConsumer
import sys

def log(msg):
    print(msg, flush=True)

BROKER = os.getenv("BROKER", "redpanda:9092")
TOPIC = os.getenv("TOPIC", "events")
TARGET_FUNCTION = os.getenv("TARGET_FUNCTION", "event-processor")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")

log(f"--- Kafka Connector Starting ---")
log(f"Target: {GATEWAY_URL}/function/{TARGET_FUNCTION}")
log(f"Broker: {BROKER} | Topic: {TOPIC}")

try:
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BROKER,
        auto_offset_reset='latest',
        enable_auto_commit=True,
        group_id='faasd-connector-group',
        value_deserializer=lambda x: x.decode('utf-8')
    )
    log("Successfully connected to Redpanda.")
except Exception as e:
    log(f"CRITICAL: Could not connect to Redpanda: {e}")
    sys.exit(1)

for message in consumer:
    try:
        log(f"Received event: {message.value[:50]}...")
        
        url = f"{GATEWAY_URL}/function/{TARGET_FUNCTION}"
        response = requests.post(url, data=message.value)
        
        log(f"Invoked {TARGET_FUNCTION}: {response.status_code}")
        
    except Exception as e:
        log(f"Error forwarding message: {str(e)}")
