"""
Manual Orchestration Challenges

This script demonstrates the complexity of manually orchestrating the three
response methods. Even a seemingly simple chatbot with tool support quickly
becomes a tangled mess of conditionals and error handling.

See the accompanying 02_manual_orchestration.md for detailed explanation.
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
            result = eval(self.expression)
            return f"Result: {result}"
        except:
            return "Error: Invalid expression"


def manual_orchestration_loop():
    """Demonstrate manual orchestration with all its complexity"""

    # Create an agent with calculator tool
    config = ChatAgentConfig(
        llm=OpenAIGPTConfig(
            chat_model="gpt-4o-mini",
        ),
        show_stats=False,
        system_message="""
        You are a helpful assistant that can do calculations. 
        Use the `calculator` TOOL when asked to compute math expressions.
        """,
    )

    agent = ChatAgent(config)
    agent.enable_message(CalculatorTool)

    print("Type 'quit' to exit.\n")

    # Manual orchestration loop - see how complex this gets!
    max_rounds = 20
    round = 0

    while round < max_rounds:
        # Step 1: Get user input
        user_input = agent.user_response()

        # Handle user input edge cases
        if user_input.content.strip().lower() in ["x", "q"]:
            print("\nGoodbye!")
            break

        if not user_input.content.strip():
            continue

        # Step 2: Send to LLM
        ai_msg = agent.llm_response(user_input.content)

        # Handle LLM response edge cases
        if ai_msg is None:
            continue

        # Step 3: Check if LLM wants to use a tool
        tool_messages = agent.get_tool_messages(ai_msg)

        if tool_messages:
            # We have a tool request!

            # Step 4: Execute the tool
            tool_result = agent.agent_response(ai_msg)

            if tool_result is None:
                continue

            # Step 5: Send tool result back to LLM for final response
            final_response = agent.llm_response(
                f"""
                The calculation result is: {tool_result.content}. 
                Please provide a nice response to the user.
                """
            )

            if final_response.metadata.cached:
                print(f"AI: {final_response.content}")
        else:
            if ai_msg.metadata.cached:
                # No tool needed, just show the response
                print(f"AI: {ai_msg.content}")

        # Increment round counter
        round += 1

        # Check if we're approaching max rounds
        if round >= max_rounds - 1:
            print("\nReaching conversation limit...")
            break


if __name__ == "__main__":
    manual_orchestration_loop()
