import importlib.util
import json
import os
import sys
import types

fake_minio = types.ModuleType("minio")
fake_minio.Minio = object
sys.modules.setdefault("minio", fake_minio)

fake_kafka = types.ModuleType("kafka")
fake_kafka.KafkaProducer = object
fake_kafka.KafkaConsumer = object
sys.modules.setdefault("kafka", fake_kafka)

fake_pypdf2 = types.ModuleType("PyPDF2")
class _FakePdfReader:
    def __init__(self, *_args, **_kwargs):
        self.pages = []
fake_pypdf2.PdfReader = _FakePdfReader
sys.modules.setdefault("PyPDF2", fake_pypdf2)

def load_handler():
    handler_path = os.path.join(os.path.dirname(__file__), "handler.py")
    spec = importlib.util.spec_from_file_location("text_extraction_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

handler = load_handler()


class MockRequest:
    def __init__(self, body):
        self.body = body


def test_handle_happy_path(monkeypatch):
    event = {
        "Records": [{
            "eventTime": "2026-01-12T20:00:00Z",
            "s3": {
                "bucket": {"name": "documents"},
                "object": {"key": "test.txt"}
            }
        }]
    }

    monkeypatch.setattr(handler, "download_file_from_minio", lambda *_: b"hello world")
    monkeypatch.setattr(handler, "extract_text", lambda *_: "hello world")
    monkeypatch.setattr(handler, "publish_chunks_to_redpanda", lambda *_: 1)

    response = handler.handle(MockRequest(json.dumps(event)), None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["status"] == "success"
    assert body["chunks_processed"] == 1


def test_handle_invalid_event():
    response = handler.handle(MockRequest(json.dumps({"not": "minio"})), None)
    assert response["statusCode"] == 500
