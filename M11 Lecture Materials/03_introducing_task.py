"""
Introducing the Task Abstraction

This script introduces Langroid's Task abstraction, which handles all the
orchestration complexity we saw in the previous examples. Task wraps an
agent and manages the response cycle automatically.

See the accompanying 03_introducing_task.md for detailed explanation.
"""

from langroid import Task
from langroid.agent.chat_agent import ChatAgent, ChatAgentConfig
from langroid.language_models.openai_gpt import OpenAIGPTConfig


def main():
    # Create a basic agent
    config = ChatAgentConfig(
        name="Bot",
        llm=OpenAIGPTConfig(
            chat_model="gemini/gemini-2.5-flash-lite-preview-06-17",
        ),
        show_stats=False,
        system_message="You are a helpful assistant.",
    )

    agent = ChatAgent(config)

    # Instead of manual orchestration, just use Task
    task = Task(
        agent,
        interactive=True,  # Expects user interaction (this is the default)
    )

    # This single line replaces all the complex orchestration code!
    task.run()

    # Task automatically handles:
    # - User input collection
    # - LLM response generation
    # - Tool execution (none in this case)
    # - Message history
    # - Termination conditions
    # - Error handling


if __name__ == "__main__":
    main()
