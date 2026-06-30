from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


LOG_DIR = Path("logs")


def _enable_file_logging() -> bool:
    try:
        LOG_DIR.mkdir(exist_ok=True)
        return True
    except PermissionError:
        return False


logger.remove()

logger.add(
    sys.stdout,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    level="INFO",
)

if _enable_file_logging():
    try:
        logger.add(
            "logs/app.log",
            rotation="500 MB",
            retention="10 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            level="INFO",
            encoding="utf-8",
        )
        logger.add(
            "logs/error.log",
            rotation="100 MB",
            retention="30 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            level="ERROR",
            encoding="utf-8",
        )
    except PermissionError:
        pass


def get_logger(service: str):
    return logger.bind(service=service)


def log_structured(event_type: str, data: dict):
    logger.info({"event_type": event_type, "data": data})
