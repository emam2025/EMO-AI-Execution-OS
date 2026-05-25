"""AI Layer Initialization for EMO AI Orchestrator.

This module initializes the AI Code Intelligence Layer, setting up:
- AI-specific logging
- Configuration loading
- Directory structure verification
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .ai_logging import get_ai_logger, log_ai_decision

# AI logger for initialization
ai_logger = get_ai_logger("init")


def load_ai_config() -> Dict[str, Any]:
    """Load AI configuration from .ai/config.json.
    
    Returns:
        Dict containing configuration. Returns default config if file not found or invalid.
    """
    config_path = Path(".ai/config.json")
    default_config = {
        "version": "1.0.0",
        "repository": {
            "name": "Emo AI Orchestrator",
            "root": str(Path.cwd()),
            "ignore_patterns": [
                "node_modules", ".git", "dist", "build", ".next", "coverage",
                "__pycache__", "*.pyc", ".env", ".emo_*", "logs/",
                ".ai/cache/", ".ai/embeddings/", ".ai/summaries/", ".ai/graphs/",
                ".ai/decisions/", ".ai/prompts/", ".ai/index/", ".ai/memory/"
            ]
        },
        "indexing": {
            "enabled": True,
            "incremental": True,
            "file_hash_algorithm": "sha256",
            "batch_size": 100,
            "languages": ["python", "javascript", "typescript", "json", "yaml", "markdown", "txt"]
        },
        "storage": {
            "type": "sqlite",
            "database_path": ".ai/index/repository.db",
            "journal_mode": "WAL",
            "synchronous": "NORMAL",
            "cache_size": -2000,
            "temp_store": "memory"
        },
        "memory": {
            "max_entries": 10000,
            "retention_days": 365,
            "backup_enabled": True,
            "backup_interval_hours": 24
        },
        "logging": {
            "level": "INFO",
            "ai_logger_name": "emo-ai",
            "log_to_file": True,
            "log_file_path": ".ai/logs/ai.log",
            "max_bytes": 10485760,
            "backup_count": 5
        }
    }
    
    if not config_path.exists():
        ai_logger.warning(f"AI config file not found at {config_path}, using defaults")
        return default_config
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        ai_logger.info(f"Loaded AI configuration from {config_path}")
        # Merge with defaults to ensure all keys exist
        return _merge_configs(default_config, config)
    except json.JSONDecodeError as e:
        ai_logger.error(f"Invalid JSON in AI config file: {e}")
        return default_config
    except Exception as e:
        ai_logger.error(f"Failed to load AI config: {e}")
        return default_config


def _merge_configs(default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override dict into default dict.
    
    Args:
        default: Default configuration dictionary
        override: Override configuration dictionary
        
    Returns:
        Merged configuration dictionary
    """
    result = default.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def ensure_directories(config: Dict[str, Any]) -> None:
    """Ensure all required directories exist based on configuration.
    
    Args:
        config: AI configuration dictionary
    """
    repo_root = Path(config.get("repository", {}).get("root", "."))
    ai_base = repo_root / ".ai"
    
    # List of directories to ensure exist
    directories = [
        ai_base / "memory",
        ai_base / "summaries",
        ai_base / "graphs",
        ai_base / "embeddings",
        ai_base / "decisions",
        ai_base / "prompts",
        ai_base / "index",
        ai_base / "cache",
        ai_base / "logs"
    ]
    
    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            ai_logger.debug(f"Ensured directory exists: {directory}")
        except Exception as e:
            ai_logger.error(f"Failed to create directory {directory}: {e}")


def initialize_ai_layer() -> Optional[Dict[str, Any]]:
    """Initialize the AI Code Intelligence Layer.
    
    This function should be called during application startup.
    It sets up logging, loads configuration, and ensures directory structure.
    
    Returns:
        Configuration dictionary if successful, None if failed (but logs error)
    """
    try:
        ai_logger.info("Initializing AI Code Intelligence Layer...")
        
        # Load configuration
        config = load_ai_config()
        
        # Ensure directories exist
        ensure_directories(config)
        
        # Log the initialization decision
        log_ai_decision(
            decision_type="layer_initialization",
            description="AI Code Intelligence Layer initialized",
            context=f"Version: {config.get('version')}, Root: {config.get('repository', {}).get('root')}"
        )
        
        ai_logger.info("AI Code Intelligence Layer initialized successfully")
        return config
        
    except Exception as e:
        ai_logger.error(f"Failed to initialize AI Layer: {e}", exc_info=True)
        return None