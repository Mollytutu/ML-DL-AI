"""
Three Response Methods in Langroid

Langroid provides three core response methods that power agent interactions:
1. llm_response(): Get a response from the LLM
2. user_response(): Get input from the user
3. agent_response(): Process tools and agent logic

This script demonstrates each method individually. While you can call these
directly, orchestrating them manually quickly becomes complex, which is why
Langroid provides the Task abstraction (covered in later scripts).

See the accompanying 01_three_response_methods.md for detailed explanation.
"""

from rich import print

from langroid.agent.chat_agent import ChatAgent, ChatAgentConfig
from langroid.agent.tool_message import ToolMessage
from langroid.language_models.openai_gpt import OpenAIGPTConfig


# Define a simple tool for demonstration
class CalculatorTool(ToolMessage):
    request: str = "calculator"
    purpose: str = "Perform basic arithmetic"
    expression: str

    def handle(self) -> str:
        try:
            result = eval(self.expression)  # Simple eval for demo
            return f"Result: {result}"
        except:
            return "Error: Invalid expression"


def main():
    # Create an agent
    config = ChatAgentConfig(
        llm=OpenAIGPTConfig(
            chat_model="gpt-4o-mini",
        ),
        show_stats=False,
        system_message="""
        You are a helpful assistant that can do calculations
        using the `calculator` TOOL.
        """,
    )

    agent = ChatAgent(config)
    agent.enable_message(CalculatorTool)

    # 1. LLM Response - Direct interaction with the language model
    llm_msg = agent.llm_response("What is the capital of India?")
    if llm_msg:
        # llm_msg is a Langroid ChatDocument object
        print(f"LLM: {llm_msg.content}\n")

    # 2. User Response - Getting input from the user;
    #    Try typing "What is 4 * 6 ? "
    user_input = agent.user_response()
    print(f"User: {user_input.content}\n")

    # 3. Agent Response - Processing tools and agent logic
    # First, get LLM to generate a tool
    tool_request = agent.llm_response(user_input)

    # Now let agent handle the tool
    agent_result = agent.agent_response(tool_request)
    print(f"Agent result: {agent_result.content}\n")


if __name__ == "__main__":
    main()
