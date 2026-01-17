from llama_cpp import Llama
from huggingface_hub import hf_hub_download
import os

REPO_ID="bartowski/Llama-3.2-1B-Instruct-GGUF"
FILENAME="Llama-3.2-1B-Instruct-Q8_0.gguf"

model_path = None
llm = None

def init_model():
    global model_path, llm
    if llm is None:
        print("Loading model...")
        model_path = hf_hub_download(REPO_ID, FILENAME)
        llm = Llama(
            model_path=model_path,
            n_gpu_layers=-1,
            n_ctx=2048,
            verbose=False
        )
        print("Model loaded.")

try:
    init_model()
except Exception as e:
    print(f"Init failed: {e}")

def handle(event, context):

    global llm

    if llm is None:
        init_model()

    user_query = event.body.decode("utf-8") if isinstance(event.body, bytes) else str(event.body)

    prompt = (
        f"<|begin_of_text|>"
        f"<|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_query}<|eot_id|>"
        f"<|start_header_id|>assistant<|end_header_id|>\n\n"
    )

    output = llm(
        prompt,
        max_tokens=200,
        stop=["<|eot_id|>"],  # Stop generating when it's done
        echo=False
    )

    return {
        "statusCode": 200,
        "body": output['choices'][0]['text'],
        "headers": {"Content-Type": "text/plain"}
    }
