"""
Module 12, Lesson 4: Calculator Agent with Task

This script demonstrates the basic pattern of:
1. Creating a specialized agent (CalculatorAgent)
2. Wrapping it in a Task
3. Using task.run() to interact with the agent

This shows Task as an AI primitive - a single function call that encapsulates
an entire agent conversation loop.
"""

import langroid as lr
import langroid.language_models as lm


# Define the Calculator Agent configuration
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


def main():
    # Create the calculator agent
    calculator = lr.ChatAgent(CalculatorAgentConfig())
    
    # Wrap the agent in a Task
    # This creates our AI primitive - a complete conversation loop in one call
    task = lr.Task(
        calculator,
        single_round=True,
        interactive=False,  # We'll control it programmatically
        restart=False,  # IMPORTANT: Maintain conversation history across task.run() calls
    )
    
    # Now we can use task.run() as a single operation
    # Each call maintains conversation history
    
    # Set first variable
    result1 = task.run("Set x = 5")
    print(result1.content)
    print()
    
    # Set second variable
    result2 = task.run("Set y = 10")
    print(result2.content)
    print()
    
    # Perform calculation using stored variables
    result3 = task.run("Calculate x + y")
    print(result3.content)
    print()
    
    # More complex calculation
    result4 = task.run("Now calculate x * y - 15")
    print(result4.content)
    print()
    
    # Check current state
    result5 = task.run("What variables do I have stored?")
    print(result5.content)


if __name__ == "__main__":
    main()