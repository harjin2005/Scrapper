import structlog
import logging
from pathlib import Path
from datetime import datetime


def setup_logging(logs_dir: str = "logs") -> None:
    Path(logs_dir).mkdir(exist_ok=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(component: str) -> structlog.BoundLogger:
    return structlog.get_logger().bind(component=component)
