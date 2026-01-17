import requests
import random
import os

GATEWAY_URL = "http://gateway:8080/function"
TARGETS = ["local-inference", "remote-inference"]


def handle(event, context):
    req_body = event.body

    selected_target = random.choice(TARGETS)


    try:
        resp = requests.post(f"{GATEWAY_URL}/{selected_target}", data=req_body)

        return {
            "statusCode": resp.status_code,
            "body": resp.text,
            "headers": {
                "Content-Type": "text/plain",
                "X-Routing-Target": selected_target
            }
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": f"Router Error: Failed to reach {selected_target}. Error: {str(e)}"
        }