"""
Redpanda Connector

This connector is a simple Kafka consumer that routes messages to faasd functions.
"""

import os
import json
import requests
from kafka import KafkaConsumer
import sys

def log(msg):
    print(msg, flush=True)

# Configuration
BROKER = os.getenv("BROKER", "redpanda:9092")
TOPICS_STR = os.getenv("TOPICS", "text-chunks")
TOPICS = [t.strip() for t in TOPICS_STR.split(",")]
TARGET_FUNCTION = os.getenv("TARGET_FUNCTION", "embedding-generation")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "faasd-connector-group")

# Topic-to-Function Routing Map
TOPIC_ROUTES = {
    "text-chunks": "embedding-generation",
    "conversation-events": "conversation-manager",
    "llm-responses": "conversation-manager",
    "summarization-triggers": "context-summarizer"
}

def get_target_function(topic: str) -> str:
    """Get target function name for a topic."""
    return TOPIC_ROUTES.get(topic, TARGET_FUNCTION)

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
    
    The function handles all business logic:
    - conversation-manager: stores state, checks thresholds, triggers summarization
    - context-summarizer: generates summary, replaces conversation history
    - embedding-generation: generates and stores embeddings
    """
    topic = message.topic
    try:
        # Parse message value
        if isinstance(message.value, bytes):
            data = json.loads(message.value.decode('utf-8'))
        elif isinstance(message.value, str):
            data = json.loads(message.value)
        else:
            data = message.value
        
        log(f"Received message on topic '{topic}': {str(data)[:100]}...")
        
        # Get target function and invoke
        target_function = get_target_function(topic)
        log(f"Routing to function: {target_function}")
        
        result = invoke_function(target_function, data)
        
        if result:
            log(f"Function {target_function} completed successfully")
        else:
            log(f"WARNING: Function {target_function} returned no result")
        
    except json.JSONDecodeError as e:
        log(f"ERROR: Failed to parse message as JSON: {e}")
    except Exception as e:
        log(f"ERROR: Error processing message: {e}")

def main():
    log("=" * 60)
    log("Redpanda Connector - Thin Message Router")
    log("=" * 60)
    log(f"Gateway: {GATEWAY_URL}")
    log(f"Broker: {BROKER}")
    log(f"Topics: {', '.join(TOPICS)}")
    log(f"Consumer Group: {CONSUMER_GROUP}")
    log(f"Routes: {TOPIC_ROUTES}")
    log("=" * 60)
    
    # Initialize Kafka Consumer
    try:
        consumer = KafkaConsumer(
            *TOPICS,
            bootstrap_servers=BROKER,
            auto_offset_reset='latest',
            enable_auto_commit=True,
            group_id=CONSUMER_GROUP,
            value_deserializer=lambda x: x  # Keep as bytes, decode in process_message
        )
        log("Successfully connected to Redpanda.")
        log(f"Subscribed to topics: {', '.join(TOPICS)}")
    except Exception as e:
        log(f"CRITICAL: Could not connect to Redpanda: {e}")
        sys.exit(1)
    
    # Process messages
    log("Waiting for messages...")
    try:
        for message in consumer:
            process_message(message)
    except KeyboardInterrupt:
        log("Shutting down...")
    except Exception as e:
        log(f"CRITICAL: Consumer error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
