"""
Module 12, Lesson 4: Calculator Tool with Delegated Agent

This script demonstrates how a tool handler can use Task.run() to delegate
to a specialized agent. The CalculatorAgent maintains its own state and
conversation history, separate from any main agent that might use this tool.

Key concepts illustrated:
- Tool handler creating a Task with a specialized agent
- Agent maintaining persistent state across interactions
- Clean separation of concerns through delegation
"""

import langroid as lr
import langroid.language_models as lm
from langroid.pydantic_v1 import Field

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


# Create the calculator agent
calculator_agent = lr.ChatAgent(CalculatorAgentConfig())

# Create a task - this encapsulates the agent in its own conversation loop
calculator_task = lr.Task(
    calculator_agent,
    interactive=False,  # Not interactive since it's being called by another agent
    single_round=True,
    restart=False,
)

# Now define the Calculator Tool that delegates to the CalculatorAgent
class CalculatorTool(lr.ToolMessage):
    """Tool for performing stateful calculations with persistent variables."""
    
    request: str = "calculator"
    purpose: str = "Perform calculations with persistent variable storage"
    
    expression: str = Field(
        ..., 
        description="Mathematical expression or variable assignment (e.g., 'x=5' or 'x+y')"
    )

    
    def handle(self) -> str:
        """
        Handle calculation by delegating to a CalculatorAgent.
        
        This creates a new Task with the CalculatorAgent, which maintains
        its own conversation history and state separate from the main agent.
        """
        
        # Run the task with the expression
        # Since restart=False, 
        # the task maintains agent conversation history across multiple calls
        result = calculator_task.run(self.expression)
        
        # Return the calculator's response
        return result.content


# Example of how this tool would be used (demonstration only)
def demonstrate_calculator_tool():
    """
    This function demonstrates how the CalculatorTool maintains state
    across multiple invocations. In practice, this tool would be used
    by a main agent, not called directly.
    """
    # Create calculator tool instances
    tool1 = CalculatorTool(expression="Set x = 5")
    print(tool1.handle())
    print()
    
    tool2 = CalculatorTool(expression="Set y = 10")
    print(tool2.handle())
    print()
    
    tool3 = CalculatorTool(expression="Calculate x + y")
    print(tool3.handle())
    print()
    
    # Note: Each tool invocation creates a NEW task, so state is NOT preserved
    # This is why we need the tool to be used within a persistent agent context


if __name__ == "__main__":
    demonstrate_calculator_tool()