"""Logging helpers for the command-line interface."""

import logging


class ColorFormatter(logging.Formatter):
    """Formatter that adds ANSI color codes to log messages."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "",  # Default color
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        color = self.COLORS.get(levelname, self.RESET)
        record.levelname = f"{color}{levelname}{self.RESET}"
        return super().format(record)
