"""
Pytest configuration for setting CHAT_MODEL via command line
"""
import os
import pytest


def pytest_addoption(parser):
    """Add custom command line option for model selection."""
    parser.addoption(
        "--model",
        action="store",
        default=None,
        help="Set the OPENAI_CHAT_MODEL environment variable (e.g., --model gpt-4)"
    )


def pytest_configure(config):
    """Set environment variable based on command line option."""
    model = config.getoption("--model")
    if model:
        os.environ["OPENAI_CHAT_MODEL"] = model
        print(f"\nSetting OPENAI_CHAT_MODEL={model}")