"""
Module 06 Assignment: Understanding LLM API Calls

This assignment focuses on:
- Building properly structured API requests
- Understanding message format and roles
- Working with API parameters like temperature
- Making actual API calls using the OpenAI client library

Note: We use the OpenAI client library, but the actual model and endpoint
are configured via environment variables and may not be OpenAI models.

## How to run this file:

1. Make sure you're in the assignment folder:
   cd <assignment-folder>

2. Make sure your virtual environment is activated:
   # On macOS/Linux:
   source .venv/bin/activate
   
   # On Windows:
   .venv\Scripts\activate

3. Run the file:
   python assignment.py

This will execute the main() function at the bottom and show examples of
all the API request structures you're building.
"""

import os
import json
from typing import List, Dict
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get model from environment - this is set by your course instructor
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gemini-2.5-flash")


def create_simple_request() -> Dict:
    """
    Create a simple API request with a single user message.
    
    Returns:
        A dictionary representing the API request payload
    """
    # TODO 1: Create and return a proper API request dictionary
    # It should ask "What is the capital of France?"
    # Include the model and messages fields
    
    request = {
        "model": CHAT_MODEL,
        "messages": [
            # TODO 1: Add a user message here asking about the capital of France
        ]
    }
    
    return request


def create_conversation_request() -> Dict:
    """
    Create an API request with a multi-turn conversation.
    
    Returns:
        A dictionary representing the API request payload
    """
    # Build a conversation about programming
    messages = [
        {"role": "system", "content": "You are a helpful programming assistant."},
        {"role": "user", "content": "What is a variable?"},
        {"role": "assistant", "content": "A variable is a named storage location in memory that holds a value."},
        # TODO 2: Add a follow-up user message asking about variable naming rules
    ]
    
    request = {
        "model": CHAT_MODEL,
        "messages": messages
    }
    
    return request


def create_temperature_request(creativity_needed: bool) -> Dict:
    """
    Create an API request with appropriate temperature setting.
    
    Args:
        creativity_needed: If True, use high temperature; if False, use low temperature
        
    Returns:
        A dictionary representing the API request payload
    """
    messages = [
        {"role": "user", "content": "Generate a haiku about programming"}
    ]
    
    # TODO 3: Set the temperature based on creativity_needed
    # High creativity: temperature around 0.8-1.0
    # Low creativity: temperature around 0.1-0.3
    
    request = {
        "model": CHAT_MODEL,
        "messages": messages,
        # TODO 3: Add the temperature parameter here based on creativity_needed
    }
    
    return request


def make_api_call(request: Dict) -> str:
    """
    Make an actual API call to OpenAI and return the response.
    
    Args:
        request: The API request payload
        
    Returns:
        The assistant's response text
    """
    # Initialize OpenAI client
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
    )
    
    # TODO 4: Make the API call using client.chat.completions.create()
    # Extract and return just the message content from the response
    # Hint: The response structure is response.choices[0].message.content
    
    try:
        # TODO 4: Complete the implementation
        # 1. Make the API call passing **request
        # 2. Extract the message content from the response
        # 3. Return the content
        pass  # Remove this and implement the function
    except Exception as e:
        return f"Error: {str(e)}"


def demonstrate_token_limit() -> Dict:
    """
    Create a request that demonstrates the max_tokens parameter.
    
    Returns:
        A dictionary representing the API request payload
    """
    messages = [
        {"role": "user", "content": "Explain machine learning in detail"}
    ]
    
    # TODO 5: Create a request that limits the response to approximately 50 tokens
    request = {
        "model": CHAT_MODEL,
        "messages": messages,
        # TODO 5: Add the max_tokens parameter here
    }
    
    return request


def main():
    """Demonstrate all the functions."""
    print("=== Module 06: OpenAI API Calls ===\n")
    
    # 1. Simple request
    print("1. Simple Request:")
    simple_req = create_simple_request()
    print(json.dumps(simple_req, indent=2))
    
    # 2. Conversation request
    print("\n2. Conversation Request:")
    conv_req = create_conversation_request()
    print(json.dumps(conv_req, indent=2))
    
    # 3. Temperature examples
    print("\n3. Temperature Requests:")
    creative_req = create_temperature_request(creativity_needed=True)
    factual_req = create_temperature_request(creativity_needed=False)
    print("Creative:", json.dumps(creative_req, indent=2))
    print("Factual:", json.dumps(factual_req, indent=2))
    
    # 4. Make an actual API call (commented out for testing)
    # print("\n4. Actual API Call:")
    # response = make_api_call(simple_req)
    # print(f"Response: {response}")
    
    # 5. Token limit
    print("\n5. Token Limit Request:")
    token_req = demonstrate_token_limit()
    print(json.dumps(token_req, indent=2))


if __name__ == "__main__":
    main()