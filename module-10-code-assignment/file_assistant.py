"""
Task 1-2 Part 2: File Assistant Agent

Create an agent that can use the file tools to perform operations
based on natural language requests. This agent will interpret user
intent and use the appropriate tools.

Complete the TODOs below to implement the file assistant.
"""

import os
from dotenv import load_dotenv
import langroid as lr
import langroid.language_models as lm
from langroid.agent.tools.orchestration import DoneTool
from file_tools import ListDirTool, ReadFileTool, WriteFileTool

# Load environment variables from .env file
load_dotenv()

# Get model from environment, default to Gemini if not set
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gemini/gemini-2.5-flash")


class FileAssistantConfig(lr.ChatAgentConfig):
    """Configuration for the File Assistant agent."""
    
    # TODO 1: Set a descriptive name for the agent
    name: str = "FileAssistantAgent"
    
    # TODO 2: Configure the LLM
    # Hint: Use lm.OpenAIGPTConfig with chat_model=CHAT_MODEL
    llm: lm.OpenAIGPTConfig = lm.OpenAIGPTConfig(chat_model=CHAT_MODEL)

    # TODO 3: Nudge the LLM to use tools when it forgets
    # IMPORTANT: This nudges the LLM to use a tool when it forgets
    handle_llm_no_tool:str  = f"""
        You FORGOT to use one of your TOOLs! Remember that:
        - Use '{ListDirTool.name()}' to list directory contents.
        - Use '{ReadFileTool.name()}' to read file contents. 
        - Use '{WriteFileTool.name()}' to write contents to a files. 
        - Use '{DoneTool.name()}' to finish and return results. 
        Always pick EXACTLY one tool to use based on the user's request. wait for its result, then decide next steps. 
        """

    # TODO 4: Write a system message that:
    # - Explains the agent is a helpful file assistant
    # - Lists available tools (use tool.name() to get actual names):
    #   - ListDirTool for listing directory contents
    #   - ReadFileTool for reading files
    #   - WriteFileTool for writing files
    #   - DoneTool to signal completion and return results in `content` field
    # - Provides guidance on how to use tools appropriately
    # - Instructs to provide clear, helpful responses
    # - IMPORTANT: Must use DoneTool to return the summary
    # Regarding naming the tools, note that  the agent is unaware of the class names of
    # the tools, so you have to get the `name()` method of the tool class to
    # get the actual name, e.g. `ReadFileTool.name()`.
    # (Do not change the last two paragraphs of the system message!)
    system_message: str = f"""
    You are a helpful file assistant. You can perform file operations using the following tools:
    - `{ListDirTool.name()}`: Use this tool to list the contents of a directory.
    - `{ReadFileTool.name()}`: Use this tool to read the contents of a file.
    - `{WriteFileTool.name()}`: Use this tool to write text content to a file.
    - `{DoneTool.name()}`: Use this tool to indicate that you have completed the user's request, and to return any results.      
    
    Use these tools to assist users with their file-related requests.
    Always choose the most appropriate tool based on the user's needs, 
    and provide clear and helpful responses.
    
    IMPORTANT: You CANNOT use multiple tools at once! Use one tool at a time,
        wait for the result, and THEN decide what to do next.
    
    When your task is complete, you MUST use the `{DoneTool.name()}` tool to 
    indicate completion, and use the `content` field to return any response you wish to 
    provide. It is CRITICAL to use the `content` field to return any results 
    sought by the user, since they will NOT be able to see anything outside of this tool!
    """


def run_file_assistant(prompt: str) -> str:
    """
    Create and run a file assistant agent with the given prompt.
    
    Args:
        prompt: The user's request to the file assistant
        
    Returns:
        str: The agent's response
    """
    # TODO 5: Create the agent configuration
    config = FileAssistantConfig()
    # Replace with FileAssistantConfig instance
    
    # TODO 6: Create the ChatAgent
    agent = lr.ChatAgent(config)
    # Replace with lr.ChatAgent instance
    
    # TODO 7: Enable the agent to use all file tools and the DoneTool
    agent.enable_message(ListDirTool)
    agent.enable_message(ReadFileTool)
    agent.enable_message(WriteFileTool)
    agent.enable_message(DoneTool)
    
    # TODO 8: Create a Task with the agent
    # Hint: Set interactive=False for automated operation
    task = lr.Task(agent, interactive=False)
    # Replace with lr.Task instance
    
    # TODO 9: Run the task with the prompt
    result = task.run(prompt)
    # Replace with task run result
    
    # TODO 10: Return the string representation of the result
    # Note: result is a ChatDocument, which has a content attribute of type str
    return result.content if result else ""


if __name__ == "__main__":
  # Test listing files
    response = run_file_assistant("List all files in the myfiles directory")
    print("List response:")
    print(response)
    
    # Test reading a file
    response = run_file_assistant("Read the file myfiles/beethoven.md")
    print("\nRead response:")
    print(response)
    
    # Test writing a file
    response = run_file_assistant("Write 'Hello, World!' to myfiles/test.txt")
    print("\nWrite response:")
    print(response)