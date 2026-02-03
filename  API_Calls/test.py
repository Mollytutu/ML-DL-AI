"""
Tests for Module 06 Assignment: Understanding LLM API Calls

Note: These tests use the OpenAI client library to make API calls,
but the actual model and endpoint are configured via environment variables.
"""

import pytest
import json
import os

from assignment import (
    create_simple_request,
    create_conversation_request,
    make_api_call,
    CHAT_MODEL
)


def test_create_simple_request():
    """Test that create_simple_request builds a proper API request."""
    request = create_simple_request()
    
    # Check structure
    assert isinstance(request, dict)
    assert "model" in request
    assert "messages" in request
    
    # Check model uses environment variable
    assert request["model"] == CHAT_MODEL
    
    # Check messages
    messages = request["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert "capital of france" in messages[0]["content"].lower()


def test_create_conversation_request():
    """Test that create_conversation_request includes proper conversation history."""
    request = create_conversation_request()
    
    # Check basic structure
    assert isinstance(request, dict)
    assert "messages" in request
    
    messages = request["messages"]
    assert len(messages) == 4  # system, user, assistant, user
    
    # Check roles in order
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"
    assert messages[3]["role"] == "user"




def test_make_api_call():
    """Test that make_api_call properly calls the API."""
    # Skip if no API key is set
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    # Test with a simple request
    test_request = {
        "model": CHAT_MODEL,
        "messages": [{"role": "user", "content": "Say 'test passed' and nothing else"}],
        "max_tokens": 500
    }
    
    result = make_api_call(test_request)
    
    # Check we got a response
    assert isinstance(result, str)
    assert len(result) > 0
    assert "error" not in result.lower()  # Should not be an error


def test_make_api_call_error_handling():
    """Test that make_api_call handles errors gracefully."""
    # Test with invalid request (missing required fields)
    invalid_request = {"model": CHAT_MODEL}  # Missing messages
    
    result = make_api_call(invalid_request)
    
    # Should return error message, not crash
    assert isinstance(result, str)
    assert "error" in result.lower()


def test_request_structures():
    """Test that all requests have valid JSON structure."""
    # Test each function produces valid JSON
    requests = [
        create_simple_request(),
        create_conversation_request(),
    ]
    
    for req in requests:
        # Should be JSON serializable
        json_str = json.dumps(req)
        assert json_str
        
        # Should have required fields
        assert "model" in req
        assert "messages" in req
        assert isinstance(req["messages"], list)
        assert all(isinstance(msg, dict) for msg in req["messages"])
        assert all("role" in msg and "content" in msg for msg in req["messages"])


# Test result tracking - simple approach
_test_results = {"passed": 0, "total": 0}

@pytest.fixture(autouse=True)
def track_test_results(request):
    """Track test results for summary."""
    _test_results["total"] += 1
    yield
    if not hasattr(request.node, 'rep_call') or request.node.rep_call.passed:
        _test_results["passed"] += 1

@pytest.fixture(scope="session", autouse=True)
def test_summary(request):
    """Print test summary at the end."""
    def print_summary():
        print(f"\nTESTS PASSED: {_test_results['passed']}/{_test_results['total']}")
    request.addfinalizer(print_summary)

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Make test result available to fixtures."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)


# Run tests with: pytest -xvs test.py