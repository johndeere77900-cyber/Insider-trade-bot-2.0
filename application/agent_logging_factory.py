"""
Factory for creating the top-level agent logger.
"""

from __future__ import annotations

import logging
from typing import Optional

from application.agent_logging import AgentLogger


def create_agent_logger(
    *,
    logger: Optional[logging.Logger] = None,
) -> AgentLogger:
    """
    Create the agent logging boundary.

    If no logger is supplied, AgentLogger creates its standard named logger.
    """
    return AgentLogger(logger=logger)
