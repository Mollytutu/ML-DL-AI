"""
Tool Handler with Task Invocation

Demonstrates how a tool handler can internally invoke a Langroid task.
The main agent uses a tool to analyze sentiment, and that tool's handler
creates and runs a separate agent task to perform the analysis.
"""

from langroid import Task, TaskConfig
from langroid.agent.chat_agent import ChatAgent, ChatAgentConfig
from langroid.agent.tool_message import ToolMessage
from langroid.language_models.openai_gpt import OpenAIGPTConfig


class SentimentResult(ToolMessage):
    """Tool for returning sentiment analysis results"""
    
    request: str = "sentiment_result"
    purpose: str = "Return the sentiment analysis results"
    
    sentiment: str  # positive, negative, or neutral
    confidence: float  # 0.0 to 1.0
    summary: str


class SentimentAnalysisTool(ToolMessage):
    """Tool for analyzing sentiment of text"""
    
    request: str = "sentiment_analysis"
    purpose: str = "Analyze sentiment of the provided text"
    
    text: str
    
    def handle(self) -> str:
        """Handler that invokes a separate agent task for sentiment analysis"""
        # Configure sentiment analyzer agent
        config = ChatAgentConfig(
            name="SentimentAnalyzer",
            llm=OpenAIGPTConfig(
                chat_model="gpt-4o-mini",
            ),
            system_message="""Analyze the sentiment of the given text.
            Use the sentiment_result tool to return structured results.""",
        )
        
        # Create agent and enable SentimentResult tool
        agent = ChatAgent(config)
        agent.enable_message(SentimentResult)
        
        # Configure task to terminate after tool generation
        task_config = TaskConfig(done_if_tool=True)
        task = Task(
            agent,
            interactive=False,
            config=task_config,
        )
        
        # Run the task
        result = task.run(f"Analyze sentiment: {self.text}")
        
        # Check if result contains tool messages
        if result and hasattr(result, 'tool_messages'):
            for tool in result.tool_messages:
                if isinstance(tool, SentimentResult):
                    return f"{tool.sentiment} (confidence: {tool.confidence:.2f})"
        
        return "Analysis failed"


def main():
    # Configure main agent
    main_config = ChatAgentConfig(
        name="TextProcessor",
        llm=OpenAIGPTConfig(
            chat_model="gpt-4o-mini",
        ),
        system_message="""Process the given text by analyzing its sentiment.
        Use the sentiment_analysis tool for this task.""",
    )
    
    # Create main agent and enable the tool
    main_agent = ChatAgent(main_config)
    main_agent.enable_message(SentimentAnalysisTool)
    
    # Create main task
    main_task = Task(
        main_agent,
        interactive=False,
    )
    
    # Test text
    test_text = "This product is amazing! I love it."
    
    # Run the main task
    result = main_task.run(f"Analyze this: {test_text}")
    print(result.content)


if __name__ == "__main__":
    main()