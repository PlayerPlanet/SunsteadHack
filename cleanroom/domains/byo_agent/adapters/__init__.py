"""Adapters for integrating external agents into the byo_agent vertical.

This module provides adapter classes that wrap domain-specific agents
to conform to the byo_agent contract: invoke(input_text, config) -> {result, tokens}.
"""

from .arctal import (
    ArctalReviewAgent,
    ArctalPromptProposer,
    build_arctal_eval,
    write_arctal_eval_jsonl,
)

__all__ = [
    "ArctalReviewAgent",
    "ArctalPromptProposer",
    "build_arctal_eval",
    "write_arctal_eval_jsonl",
]
