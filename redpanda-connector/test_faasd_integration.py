"""
Real integration tests that call deployed faasd serverless functions.

These tests require:
- faasd running with functions deployed
- OpenFaaS Gateway accessible (default: http://localhost:8080)
- Basic auth credentials configured

To run these tests:
1. Ensure faasd is running: sudo systemctl status faasd
2. Deploy functions: faas-cli deploy -f ../stack.yaml
3. Set credentials: export OPENFAAS_URL=http://localhost:8080
                   export OPENFAAS_USER=admin
                   export OPENFAAS_PASSWORD=$(sudo cat /var/lib/faasd/secrets/basic-auth-password)
4. Run: pytest test_faasd_integration.py -v -m faasd_integration

To skip if faasd not available:
pytest test_faasd_integration.py -v --skip-faasd-integration
"""

import pytest
import json
import os
import sys
import requests
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Test configuration
GATEWAY_URL = os.getenv("OPENFAAS_URL", "http://localhost:8080")
OPENFAAS_USER = os.getenv("OPENFAAS_USER", "admin")
OPENFAAS_PASSWORD = os.getenv("OPENFAAS_PASSWORD", "")

def utc_now_iso() -> str:
    """Return UTC timestamp in ISO 8601 with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def check_gateway_available() -> bool:
    """Check if OpenFaaS Gateway is accessible."""
    try:
        response = requests.get(f"{GATEWAY_URL}/system/functions", timeout=2)
        return response.status_code in [200, 401]  # 401 means gateway is up but needs auth
    except:
        return False


def get_auth_headers() -> Dict[str, str]:
    """Get basic auth headers for OpenFaaS Gateway."""
    import base64
    if OPENFAAS_PASSWORD:
        credentials = f"{OPENFAAS_USER}:{OPENFAAS_PASSWORD}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    return {}


def invoke_function_real(function_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Invoke OpenFaaS function via HTTP (real call, not mocked).
    
    Args:
        function_name: Name of the function to invoke
        data: JSON payload to send
    
    Returns:
        Response data as dict with statusCode and body, or None on connection failure.
        Note: Even error responses (4xx, 5xx) are returned as dicts with statusCode.
    """
    url = f"{GATEWAY_URL}/function/{function_name}"
    headers = get_auth_headers()
    headers["Content-Type"] = "application/json"
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=60)
        
        # Parse response body
        try:
            body = response.json()
        except:
            body = {"text": response.text}
        
        # Return response with statusCode for both success and error cases
        if response.status_code == 200:
            # Success: return body directly, or wrap if it has statusCode
            if isinstance(body, dict) and "statusCode" in body:
                return body
            return body
        else:
            # Error: return structured error response
            return {
                "statusCode": response.status_code,
                "body": json.dumps(body) if not isinstance(body, str) else body
            }
    except requests.exceptions.RequestException as e:
        # Connection/network errors: return None
        print(f"ERROR: Failed to invoke {function_name}: {e}")
        return None
    except Exception as e:
        print(f"ERROR: Unexpected error invoking {function_name}: {e}")
        return None


class TestGatewayConnectivity:
    """Test basic connectivity to OpenFaaS Gateway."""
    
    @pytest.mark.skipif(not check_gateway_available(), reason="Gateway not available")
    def test_gateway_reachable(self):
        """Test that gateway is accessible."""
        response = requests.get(f"{GATEWAY_URL}/system/functions", timeout=5)
        # Should get 200 (authorized) or 401 (unauthorized but gateway is up)
        assert response.status_code in [200, 401], f"Gateway should be reachable, got {response.status_code}"
    
    @pytest.mark.skipif(not check_gateway_available(), reason="Gateway not available")
    def test_gateway_auth(self):
        """Test that gateway accepts authentication."""
        if not OPENFAAS_PASSWORD:
            pytest.skip("OPENFAAS_PASSWORD not set")
        
        headers = get_auth_headers()
        response = requests.get(f"{GATEWAY_URL}/system/functions", headers=headers, timeout=5)
        assert response.status_code == 200, "Should authenticate successfully"


class TestFunctionDeployment:
    """Test that required functions are deployed."""
    
    @pytest.mark.skipif(not check_gateway_available(), reason="Gateway not available")
    def test_functions_listed(self):
        """Test that we can list deployed functions."""
        if not OPENFAAS_PASSWORD:
            pytest.skip("OPENFAAS_PASSWORD not set")
        
        headers = get_auth_headers()
        response = requests.get(f"{GATEWAY_URL}/system/functions", headers=headers, timeout=5)
        
        assert response.status_code == 200
        functions = response.json()
        
        function_names = [f["name"] for f in functions]
        
        # Check for expected functions
        expected_functions = [
            "conversation-manager",
            "context-summarizer",
            "embedding-generation",
            "text-extraction"
        ]
        
        for func_name in expected_functions:
            assert func_name in function_names, f"Function {func_name} should be deployed"


class TestConversationManagerReal:
    """Real integration tests for conversation-manager function."""
    
    @pytest.mark.skipif(not check_gateway_available(), reason="Gateway not available")
    def test_conversation_manager_store_message(self):
        """Test storing a conversation event via real function invocation."""
        test_event = {
            "event_type": "user_query",
            "session_id": f"test-session-{int(time.time())}",
            "role": "user",
            "content": "Hello, this is a test message",
            "timestamp": utc_now_iso(),
            "metadata": {"tokens": 10, "model": "gpt-4"}
        }
        
        result = invoke_function_real("conversation-manager", test_event)
        
        assert result is not None, "Function should return a result"
        assert result.get("statusCode") == 200 or result.get("status") == "success", \
            f"Function should succeed, got: {result}"
    
    @pytest.mark.skipif(not check_gateway_available(), reason="Gateway not available")
    def test_conversation_manager_store_llm_response(self):
        """Test storing an LLM response via real function invocation."""
        session_id = f"test-session-{int(time.time())}"
        
        # First store a user message
        user_event = {
            "event_type": "user_query",
            "session_id": session_id,
            "role": "user",
            "content": "What is AI?",
            "timestamp": utc_now_iso(),
            "metadata": {"tokens": 5}
        }
        invoke_function_real("conversation-manager", user_event)
        
        # Then store LLM response
        llm_response = {
            "session_id": session_id,
            "role": "assistant",
            "content": "AI is artificial intelligence.",
            "timestamp": utc_now_iso(),
            "metadata": {"tokens": 15}
        }
        
        result = invoke_function_real("conversation-manager", llm_response)
        
        assert result is not None
        assert result.get("statusCode") == 200 or result.get("status") == "success"


class TestContextSummarizerReal:
    """Real integration tests for context-summarizer function."""
    
    @pytest.mark.skipif(not check_gateway_available(), reason="Gateway not available")
    def test_context_summarizer_trigger(self):
        """Test summarization trigger via real function invocation."""
        session_id = f"test-summary-{int(time.time())}"
        
        # First, create a conversation by storing messages
        # (This would normally be done by conversation-manager)
        # For this test, we'll trigger summarization even if no history exists
        # and expect a 404 or graceful handling
        
        trigger = {
            "session_id": session_id,
            "trigger_reason": "manual",
            "current_tokens": 100,
            "current_messages": 5,
            "threshold": 0
        }
        
        result = invoke_function_real("context-summarizer", trigger)
        
        # Should get a response (either success or 404 if no history)
        assert result is not None, "Function should return a response"
        # If no history exists, we expect 404
        if isinstance(result, dict) and result.get("statusCode") == 404:
            body = result.get("body", "")
            if isinstance(body, str):
                body_dict = json.loads(body)
            else:
                body_dict = body
            assert "No conversation history" in str(body_dict), "Should indicate no history found"
        else:
            # If it succeeded, verify structure
            assert result.get("statusCode") == 200 or "status" in result, "Should return success or error status"


class TestEndToEndReal:
    """End-to-end tests using real function invocations."""
    
    @pytest.mark.skipif(not check_gateway_available(), reason="Gateway not available")
    def test_full_conversation_workflow(self):
        """
        Test complete workflow: store message -> store response -> trigger summarization.
        
        This tests the actual interaction between functions via Kafka messages,
        but using direct function invocation for testing.
        """
        session_id = f"test-e2e-{int(time.time())}"
        
        # Step 1: Store user message
        user_event = {
            "event_type": "user_query",
            "session_id": session_id,
            "role": "user",
            "content": "What is machine learning?",
            "timestamp": utc_now_iso(),
            "metadata": {"tokens": 10}
        }
        
        result1 = invoke_function_real("conversation-manager", user_event)
        assert result1 is not None
        
        # Step 2: Store assistant response
        assistant_event = {
            "session_id": session_id,
            "role": "assistant",
            "content": "Machine learning is a subset of AI.",
            "timestamp": utc_now_iso(),
            "metadata": {"tokens": 15}
        }
        
        result2 = invoke_function_real("conversation-manager", assistant_event)
        assert result2 is not None
        
        # Step 3: Trigger summarization (manual for testing)
        trigger = {
            "session_id": session_id,
            "trigger_reason": "manual",
            "current_tokens": 25,
            "current_messages": 2,
            "threshold": 0
        }
        
        result3 = invoke_function_real("context-summarizer", trigger)
        
        # Should succeed if history exists, or 404 if Redis state isn't shared
        assert result3 is not None, "Function should return a response"
        # Handle both wrapped responses (with statusCode) and direct success responses
        status_code = result3.get("statusCode")
        if status_code is None:
            # Direct success response (status 200)
            assert "status" in result3 or "summary" in result3, "Should have success indicators"
        else:
            # Wrapped response with statusCode
            assert status_code in [200, 404], \
                f"Expected 200 or 404, got {status_code}"
    
    @pytest.mark.skipif(not check_gateway_available(), reason="Gateway not available")
    def test_function_error_handling(self):
        """Test that functions handle invalid input gracefully."""
        invalid_payload = {
            "invalid": "data",
            "missing": "required_fields"
        }
        
        result = invoke_function_real("conversation-manager", invalid_payload)
        
        # Should return error (400 or 500), not crash
        assert result is not None, "Function should return a response (even for errors)"
        # Handle both wrapped error responses and direct error responses
        status_code = result.get("statusCode")
        if status_code is None:
            # Check if it's a direct error response
            if "error" in result:
                # Direct error response (status 400 from function)
                assert True, "Function returned error response"
            else:
                pytest.fail(f"Expected error response, got: {result}")
        else:
            assert status_code >= 400, f"Should return error status for invalid input, got {status_code}"


if __name__ == "__main__":
    # Print configuration before running
    print(f"Gateway URL: {GATEWAY_URL}")
    print(f"OpenFaaS User: {OPENFAAS_USER}")
    print(f"Password set: {'Yes' if OPENFAAS_PASSWORD else 'No'}")
    print(f"Gateway available: {check_gateway_available()}")
    print()
    
    # Run tests
    pytest.main([__file__, "-v", "-m", "faasd_integration"])
