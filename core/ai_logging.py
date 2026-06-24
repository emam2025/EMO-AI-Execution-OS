"""AI-specific logging configuration for the AI Code Intelligence Layer."""

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional

# Import the main logging config to reuse formatters and handlers
from .logging_config import ColoredFormatter

# AI-specific log directory
AI_LOG_DIR = Path(os.getenv("EMO_AI_LOG_DIR", ".ai/logs"))
AI_LOG_DIR.mkdir(exist_ok=True)

# AI log file paths
AI_MAIN_LOG = AI_LOG_DIR / "ai.log"
AI_ERROR_LOG = AI_LOG_DIR / "ai_error.log"
AI_DEBUG_LOG = AI_LOG_DIR / "ai_debug.log"

# Log rotation settings (smaller files for AI logs)
AI_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
AI_BACKUP_COUNT = 3


def setup_ai_logging(level: str = "INFO") -> None:
    """Configure AI-specific logging system.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # AI root logger
    ai_logger = logging.getLogger("emo-ai")
    ai_logger.setLevel(log_level)
    
    # Clear existing handlers to avoid duplication
    ai_logger.handlers.clear()
    
    # Console handler with colors (reuse from main logging)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = ColoredFormatter(
        "%(asctime)s [%(levelname)s] emo-ai: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    ai_logger.addHandler(console_handler)
    
    # Main AI log file handler with rotation
    ai_file_handler = logging.handlers.RotatingFileHandler(
        AI_MAIN_LOG,
        maxBytes=AI_MAX_BYTES,
        backupCount=AI_BACKUP_COUNT,
        encoding="utf-8",
    )
    ai_file_handler.setLevel(logging.DEBUG)
    
    # Use simple formatter for AI logs
    ai_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ai_file_handler.setFormatter(ai_formatter)
    ai_logger.addHandler(ai_file_handler)
    
    # Error log file handler
    ai_error_handler = logging.handlers.RotatingFileHandler(
        AI_ERROR_LOG,
        maxBytes=AI_MAX_BYTES,
        backupCount=AI_BACKUP_COUNT,
        encoding="utf-8",
    )
    ai_error_handler.setLevel(logging.ERROR)
    ai_error_handler.setFormatter(ai_formatter)
    ai_logger.addHandler(ai_error_handler)
    
    # Debug log file handler (for detailed tracing)
    ai_debug_handler = logging.handlers.RotatingFileHandler(
        AI_DEBUG_LOG,
        maxBytes=AI_MAX_BYTES,
        backupCount=AI_BACKUP_COUNT,
        encoding="utf-8",
    )
    ai_debug_handler.setLevel(logging.DEBUG)
    ai_debug_handler.setFormatter(ai_formatter)
    ai_logger.addHandler(ai_debug_handler)
    
    # Prevent propagation to root logger to avoid duplicate logs
    ai_logger.propagate = False


def get_ai_logger(name: str) -> logging.Logger:
    """Get an AI-specific logger.
    
    Args:
        name: Logger name (usually __name__).
        
    Returns:
        logging.Logger: Configured AI logger instance.
    """
    full_name = f"emo-ai.{name}" if not name.startswith("emo-ai.") else name
    return logging.getLogger(full_name)


def log_ai_decision(
    decision_type: str,
    description: str,
    context: Optional[str] = None,
    actor: str = "ai-system",
) -> None:
    """Log an AI system decision for audit and traceability.
    
    Args:
        decision_type: Type of decision (indexing, summarization, graph_update, etc.)
        description: Human-readable description of the decision
        context: Additional context (JSON string preferred)
        actor: Who/what made the decision
    """
    ai_logger = get_ai_logger("decisions")
    parts = [
        f"decision_type={decision_type}",
        f"description={description}",
        f"actor={actor}"
    ]
    if context:
        parts.append(f"context={context}")
    
    ai_logger.info(" | ".join(parts))


# Initialize AI logging on import
setup_ai_logging(os.getenv("EMO_AI_LOG_LEVEL", "INFO"))