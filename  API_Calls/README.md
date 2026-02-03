# Module 06 Assignment: Understanding OpenAI API Calls

## Overview

This assignment focuses on understanding the fundamentals of LLM API calls using the OpenAI client library.

**Important Note**: Although we use the OpenAI client library, the actual LLM model 
and API endpoint are configured through environment variables. 
Your course instructor will provide the specific model and endpoint URL to use, which may not be OpenAI services.

## Assignment Focus

This assignment focuses on:
- Building properly structured API requests
- Understanding message roles (system, user, assistant)
- Working with API parameters (temperature, max_tokens)
- Making actual API calls using the OpenAI client library

## Learning Objectives

By completing this assignment, you will:
- Learn the structure of OpenAI API requests
- Understand how to build multi-turn conversations
- Practice using API parameters to control output
- Make real API calls and handle responses

## Environment Setup

### Prerequisites

1. **Install UV** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Configure environment variables**:
   
   Create a `.env` file with the API credentials provided by your course instructor:
   ```bash
   # Model configuration (provided by your instructor)
   OPENAI_CHAT_MODEL=your-model-name-here
   
   # API credentials (provided by your instructor)
   OPENAI_API_KEY=your-api-key-here
   OPENAI_API_BASE=your-api-base-url-here  # Optional, depending on your setup
   ```

### Project Setup

1. **Navigate to the assignment folder and create a virtual environment**:

   **⚠️ CRITICAL**: All scripts and tests MUST be run from the assignment folder. Do not run them from parent directories or other locations.

   ```bash
   # First, navigate to the assignment folder
   cd <assignment-folder>
   
   # Create virtual environment with Python 3.11
   uv venv --python 3.11
   
   # Activate it
   # On macOS/Linux:
   source .venv/bin/activate
   
   # On Windows:
   .venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

## API Reference

For detailed information about the Chat Completions API format and parameters, see:
- [OpenAI Chat Completions API Reference](https://platform.openai.com/docs/api-reference/chat)
- [Chat Completions Guide](https://platform.openai.com/docs/guides/chat-completions)

## Assignment Tasks

You need to complete **5 simple TODOs** indicated in `assignment.py`:


## Running the Assignment

Once you've completed the TODOs:

```bash
python assignment.py
```

The output will show:
1. Your simple request structure
2. A multi-turn conversation request
3. Requests with different temperature settings
4. A token-limited request

To test the actual API call (TODO 4), uncomment the section in main().

## Testing Your Implementation

You must continue implementing your code until all tests pass.

Run the tests to verify your work:

```bash
pytest test.py -v
```

The tests verify:
- Proper request structure
- Correct message formatting
- Appropriate parameter values
- API call implementation

## API Request Structure

A typical OpenAI API request looks like:

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 100
}
```

## Tips

1. **Messages Format**: Each message needs `role` and `content` fields
2. **Temperature**: 0.0 = deterministic, 1.0 = creative
3. **API Response**: Access content via `response.choices[0].message.content`
4. **Error Handling**: Always wrap API calls in try-except blocks

## Grading Rubric

- **TODO 1** (20%): Simple request structure
- **TODO 2** (20%): Multi-turn conversation
- **TODO 3** (20%): Temperature parameter
- **TODO 4** (20%): API call implementation
- **TODO 5** (20%): Token limit parameter

## Common Issues

- **API Key**: Ensure OPENAI_API_KEY is set in your environment
- **Dependencies**: Make sure you're in the activated virtual environment
- **Request Structure**: Messages must be a list of dictionaries

## Submission

Submit your completed `assignment.py` file with all TODOs implemented and tests passing.

Good luck!