"""
Tests for context-summarizer handler.
"""

import importlib.util
import json
import os
import pytest

def load_handler():
    handler_path = os.path.join(os.path.dirname(__file__), "handler.py")
    spec = importlib.util.spec_from_file_location("context_summarizer_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

handler = load_handler()
handle = handler.handle
validate_summarization_trigger = handler.validate_summarization_trigger
parse_input = handler.parse_input
generate_summary_placeholder = handler.generate_summary_placeholder


class MockRequest:
    """Mock request object for testing."""
    def __init__(self, body):
        self.body = body


class MockContext:
    """Mock context object for testing."""
    pass


class TestParseInput:
    """Tests for input parsing."""
    
    def test_parse_json_string(self):
        """Test parsing JSON string."""
        req = MockRequest('{"session_id": "test-123", "trigger_reason": "token_threshold", "current_tokens": 4500, "current_messages": 25, "threshold": 4000}')
        result = parse_input(req)
        assert result["session_id"] == "test-123"
        assert result["trigger_reason"] == "token_threshold"
    
    def test_parse_dict(self):
        """Test parsing dictionary."""
        data = {"session_id": "test-123", "trigger_reason": "token_threshold", "current_tokens": 4500, "current_messages": 25, "threshold": 4000}
        req = MockRequest(data)
        result = parse_input(req)
        assert result == data


class TestValidateSummarizationTrigger:
    """Tests for summarization trigger validation."""
    
    def test_valid_trigger(self):
        """Test validation of valid trigger."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is True
        assert error is None
    
    def test_missing_session_id(self):
        """Test validation fails with missing session_id."""
        data = {
            "trigger_reason": "token_threshold",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is False
        assert "session_id" in error
    
    def test_invalid_trigger_reason(self):
        """Test validation fails with invalid trigger_reason."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "invalid_reason",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is False
        assert "trigger_reason" in error
    
    def test_negative_tokens(self):
        """Test validation fails with negative token count."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": -100,
            "current_messages": 25,
            "threshold": 4000
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is False
    
    def test_message_threshold_trigger(self):
        """Test validation accepts message_threshold trigger."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "message_threshold",
            "current_tokens": 3000,
            "current_messages": 25,
            "threshold": 20
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is True
    
    def test_manual_trigger(self):
        """Test validation accepts manual trigger."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "manual",
            "current_tokens": 2000,
            "current_messages": 15,
            "threshold": 0
        }
        is_valid, error = validate_summarization_trigger(data)
        assert is_valid is True


class TestGenerateSummaryPlaceholder:
    """Tests for summary generation."""
    
    def test_generate_summary(self):
        """Test summary generation."""
        summary = generate_summary_placeholder(
            "test-123",
            "token_threshold",
            25,
            4500
        )
        assert "test-123" in summary
        assert "token_threshold" in summary
        assert "25" in summary
        assert "4500" in summary


class TestHandle:
    """Tests for main handler function."""
    
    def test_handle_valid_token_threshold_trigger(self):
        """Test handling valid token threshold trigger."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "token_threshold",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert response_body["status"] == "success"
        assert response_body["session_id"] == "test-123"
        assert "summary" in response_body
        assert response_body["trigger_reason"] == "token_threshold"
        assert response_body["compressed_from"]["messages"] == 25
        assert response_body["compressed_from"]["tokens"] == 4500
    
    def test_handle_message_threshold_trigger(self):
        """Test handling message threshold trigger."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "message_threshold",
            "current_tokens": 3000,
            "current_messages": 25,
            "threshold": 20
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert response_body["status"] == "success"
        assert response_body["trigger_reason"] == "message_threshold"
    
    def test_handle_manual_trigger(self):
        """Test handling manual trigger."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "manual",
            "current_tokens": 2000,
            "current_messages": 15,
            "threshold": 0
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert response_body["status"] == "success"
        assert response_body["trigger_reason"] == "manual"
    
    def test_handle_invalid_json(self):
        """Test handling invalid JSON."""
        req = MockRequest("invalid json")
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 400
        response_body = json.loads(result["body"])
        assert "error" in response_body
    
    def test_handle_missing_required_field(self):
        """Test handling trigger with missing required field."""
        data = {
            "trigger_reason": "token_threshold",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
            # Missing session_id
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 400
        response_body = json.loads(result["body"])
        assert response_body["error"] == "Validation failed"
    
    def test_handle_invalid_trigger_reason(self):
        """Test handling trigger with invalid trigger_reason."""
        data = {
            "session_id": "test-123",
            "trigger_reason": "invalid",
            "current_tokens": 4500,
            "current_messages": 25,
            "threshold": 4000
        }
        req = MockRequest(json.dumps(data))
        context = MockContext()
        
        result = handle(req, context)
        
        assert result["statusCode"] == 400
        response_body = json.loads(result["body"])
        assert "error" in response_body


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
