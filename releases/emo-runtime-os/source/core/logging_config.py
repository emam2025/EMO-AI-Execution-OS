"""Centralized logging configuration for EMO AI Orchestrator.

Provides:
- Console logging with colored output
- File logging with rotation
- Structured JSON logging option
- Per-module log levels
- GDPR-compliant audit logging
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional


# Log directory
LOG_DIR = Path(os.getenv("EMO_LOG_DIR", "logs"))
LOG_DIR.mkdir(exist_ok=True)

# Log file paths
MAIN_LOG = LOG_DIR / "emo_ai.log"
ERROR_LOG = LOG_DIR / "emo_ai_error.log"
AUDIT_LOG = LOG_DIR / "emo_ai_audit.log"

# Log rotation settings
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5


class ColoredFormatter(logging.Formatter):
    """Colored console formatter."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    json_format: bool = False,
) -> None:
    """Configure the logging system.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional custom log file path.
        json_format: If True, use JSON format for file logs.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = ColoredFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Main log file handler with rotation
    main_log = log_file or MAIN_LOG
    file_handler = logging.handlers.RotatingFileHandler(
        main_log,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    if json_format:
        file_formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"module": "%(name)s", "message": "%(message)s"}'
        )
    else:
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Error log file handler
    error_handler = logging.handlers.RotatingFileHandler(
        ERROR_LOG,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    root_logger.addHandler(error_handler)

    # Audit logger (separate file for GDPR/SOC2 compliance)
    audit_logger = logging.getLogger("emo-audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False  # Don't duplicate to root logger

    audit_handler = logging.handlers.RotatingFileHandler(
        AUDIT_LOG,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    audit_formatter = logging.Formatter(
        "%(asctime)s [AUDIT] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    audit_handler.setFormatter(audit_formatter)
    audit_logger.addHandler(audit_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the EMO AI prefix.

    Args:
        name: Logger name (usually __name__).

    Returns:
        logging.Logger: Configured logger instance.
    """
    full_name = f"emo-{name}" if not name.startswith("emo-") else name
    return logging.getLogger(full_name)


def log_audit(
    action: str,
    user_id: Optional[str] = None,
    resource: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Log an audit event for GDPR/SOC2 compliance.

    Args:
        action: The action performed (login, logout, delete, etc.).
        user_id: The user who performed the action.
        resource: The resource affected.
        details: Additional details (JSON string).
        ip_address: The IP address of the request.
    """
    audit_logger = logging.getLogger("emo-audit")
    parts = [f"action={action}"]
    if user_id:
        parts.append(f"user_id={user_id}")
    if resource:
        parts.append(f"resource={resource}")
    if details:
        parts.append(f"details={details}")
    if ip_address:
        parts.append(f"ip={ip_address}")
    audit_logger.info(" | ".join(parts))
