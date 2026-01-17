import importlib.util
import json
import os
import sys

import pytest

def load_handler():
    handler_path = os.path.join(os.path.dirname(__file__), "handler.py")
    spec = importlib.util.spec_from_file_location("embedding_generation_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

handler = load_handler()

class MockRequest:
    def __init__(self, body):
        self.body = body


def test_handle_success(monkeypatch):
    class FakeModel:
        def embed(self, _):
            yield [0.0] * handler.VECTOR_SIZE

    class FakeQdrant:
        def __init__(self):
            self.upserts = []

        def upsert(self, collection_name, points):
            self.upserts.append((collection_name, points))
            return {"result": "ok"}

    fake_client = FakeQdrant()

    monkeypatch.setattr(handler, "get_embedding_model", lambda: FakeModel())
    monkeypatch.setattr(handler, "get_qdrant_client", lambda: fake_client)

    payload = {
        "content": "hello world",
        "file_name": "doc.pdf",
        "chunk_index": 1
    }
    response = handler.handle(MockRequest(json.dumps(payload)), None)

    assert response["status"] == "success"
    assert "id" in response
    assert len(fake_client.upserts) == 1


def test_handle_skips_empty_content():
    payload = {"content": "", "file_name": "doc.pdf", "chunk_index": 1}
    response = handler.handle(MockRequest(json.dumps(payload)), None)
    assert response["status"] == "skipped"
