"""
Module 12, Lesson 6: Assistant Agent with Calculator Tool

This script demonstrates the complete multi-agent pattern:
1. An Assistant agent that helps users with various tasks
2. The Assistant is enabled with the CalculatorTool
3. When calculation is needed, the tool delegates to the CalculatorAgent
4. The CalculatorAgent maintains its own state across interactions

This shows a practical implementation of multi-agent composition through tools.
"""

import langroid as lr
import langroid.language_models as lm
from langroid.pydantic_v1 import Field
from langroid.agent.tools.orchestration import DoneTool
from fire import Fire


# First, define the Calculator Agent that will handle calculations
class CalculatorAgentConfig(lr.ChatAgentConfig):
    name: str = "CalculatorAgent"
    llm: lm.OpenAIGPTConfig = lm.OpenAIGPTConfig(
        chat_model="gpt-4.1-mini",
    )
    system_message: str = """
    You are a stateful calculator that maintains variables across interactions.
    
    IMPORTANT RULES:
    1. When user sets a variable (e.g., "x = 5"), store it and confirm
    2. Keep track of ALL variables set during the conversation
    3. When asked to compute using variables, use their stored values
    4. Show your work: always display the expression before the result
    5. Maintain a running history of all calculations
    
    Example interaction:
    User: Set x = 5
    You: Variable set: x = 5
    
    User: Set y = 10  
    You: Variable set: y = 10
    Current variables: x = 5, y = 10
    
    User: Calculate x + y
    You: Calculating: x + y = 5 + 10 = 15
    
    Always acknowledge what you're doing and show current state.
    """


# Create the calculator agent and task at module level for persistence
calculator_agent = lr.ChatAgent(CalculatorAgentConfig())
calculator_task = lr.Task(
    calculator_agent,
    interactive=False,
    single_round=True,
    restart=False,  # Maintains state across invocations
)


# Define the Calculator Tool that delegates to the CalculatorAgent
class CalculatorTool(lr.ToolMessage):
    """Tool for performing stateful calculations with persistent variables."""
    
    request: str = "calculator"
    purpose: str = "Perform calculations with persistent variable storage"
    
    expression: str = Field(
        ..., 
        description="Mathematical expression or variable assignment (e.g., 'x=5' or 'x+y')"
    )
    
    def handle(self) -> str:
        """Delegate calculation to the CalculatorAgent via task.run()."""
        result = calculator_task.run(self.expression)
        return result.content


# Now define the Assistant Agent that will use the Calculator Tool
class AssistantAgentConfig(lr.ChatAgentConfig):
    name: str = "Assistant"
    llm: lm.OpenAIGPTConfig = lm.OpenAIGPTConfig(
        chat_model="gpt-4.1-mini",
    )
    system_message: str = f"""
    You are a helpful general-purpose assistant that can help users with various tasks.
    
    You have access to specialized tools for specific tasks. Currently, you have:
    - {CalculatorTool.name()}: For calculations and storing mathematical variables
    
    When users need calculations or want to store mathematical variables,
    use the calculator tool. This tool maintains state across interactions,
    so variables set in one calculation are remembered for later.
    
    For general conversation, questions, explanations, or other non-calculation tasks,
    respond directly without using tools.
    
    IMPORTANT: Use tools one at a time. Never use multiple tools in one response.
    """


def main(model: str = "gpt-4.1-mini"):
    # Update model for all agents if specified
    if model != "gpt-4.1-mini":
        AssistantAgentConfig.llm.chat_model = model
        CalculatorAgentConfig.llm.chat_model = model
    
    # Create the assistant agent
    assistant = lr.ChatAgent(AssistantAgentConfig())
    
    # Enable the calculator tool
    assistant.enable_message(CalculatorTool)
    
    # Create an interactive task with the assistant
    task = lr.Task(
        assistant,
        interactive=True,  # Enable user interaction
    )
    
    # Run the interactive session
    # Example interactions you can try:
    # - "Let's set x = 15"
    # - "Now set y = 20"  
    # - "What's x + y?"
    # - "Calculate x * y - 100"
    # - "What variables do I have stored?"
    # - General questions like "What's the capital of France?"
    # - "How does photosynthesis work?"
    # The calculator will maintain state across the conversation
    task.run()


if __name__ == "__main__":
    Fire(main)