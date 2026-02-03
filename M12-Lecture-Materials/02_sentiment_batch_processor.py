"""
Batch Sentiment Processing with Task-in-Tool

Main agent processes multiple paragraphs by invoking a sentiment analysis
tool for each one. The tool handler creates a task to perform the analysis.
"""

from typing import List
from langroid import Task, TaskConfig
from langroid.agent.chat_agent import ChatAgent, ChatAgentConfig
from langroid.agent.tool_message import ToolMessage
from langroid.agent.tools.orchestration import DoneTool
from langroid.language_models.openai_gpt import OpenAIGPTConfig


class SentimentTool(ToolMessage):
    """Tool for sentiment analysis using a sub-task"""
    
    request: str = "analyze_sentiment"
    purpose: str = "Analyze sentiment of a paragraph"
    
    paragraph_id: int
    text: str
    
    def handle(self) -> str:
        """Create and run a sentiment analysis task"""
        sentiment_agent = ChatAgent(
            ChatAgentConfig(
                name="SentimentExpert",
                llm=OpenAIGPTConfig(chat_model="gpt-4o-mini"),
                system_message="Classify sentiment as POSITIVE, NEGATIVE, or NEUTRAL with a score.",
            )
        )
        
        task = Task(sentiment_agent, interactive=False, single_round=True)
        result = task.run(self.text)
        
        return f"Paragraph {self.paragraph_id}: {result.content}"


class BatchResult(ToolMessage):
    """Tool for returning batch processing results"""
    
    request: str = "batch_result"
    purpose: str = "Return all sentiment analysis results"
    
    results: List[str]
    
    def handle(self) -> DoneTool:
        summary = "\n".join(self.results)
        return DoneTool(content=f"Analysis complete:\n{summary}")


def main():
    # Test paragraphs
    paragraphs = [
        "The service was exceptional and the staff were very friendly.",
        "The product broke after one day. Very disappointed.",
        "The weather today is cloudy with a chance of rain.",
    ]
    
    # Configure batch processor agent
    processor_config = ChatAgentConfig(
        name="BatchProcessor",
        llm=OpenAIGPTConfig(chat_model="gpt-4o-mini"),
        system_message=f"""Process {len(paragraphs)} paragraphs:
        1. Use analyze_sentiment tool for each paragraph
        2. Collect all results
        3. Use batch_result tool to return the complete analysis""",
    )
    
    processor = ChatAgent(processor_config)
    processor.enable_message([SentimentTool, BatchResult])
    
    # Create task with termination on BatchResult
    task_config = TaskConfig(done_if_tool=True)
    processor_task = Task(
        processor,
        interactive=False,
        config=task_config,
    )
    
    # Format paragraphs for processing
    input_text = "\n".join([f"Paragraph {i+1}: {p}" for i, p in enumerate(paragraphs)])
    
    # Run batch processing
    result = processor_task.run(input_text)
    print(result.content)


if __name__ == "__main__":
    main()