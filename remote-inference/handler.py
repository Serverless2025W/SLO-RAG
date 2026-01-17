import os
from groq import Groq


def handle(event, context):
    # 1. Extract the prompt from the event body
    # The template puts the raw string body into event.body
    req = event.body

    # 2. Get API Key
    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        return {
            "statusCode": 500,
            "body": "Error: GROQ_API_KEY environment variable is missing."
        }

    client = Groq(api_key=api_key)

    try:
        # Default prompt if empty
        prompt = req.decode("utf-8") if isinstance(req, bytes) else req
        if not prompt:
            prompt = "Hello!"

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.5,
        )

        response_text = chat_completion.choices[0].message.content

        # Return a dictionary compatible with the template
        return {
            "statusCode": 200,
            "body": response_text,
            "headers": {"Content-Type": "text/plain"}
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": f"Groq API Error: {str(e)}"
        }