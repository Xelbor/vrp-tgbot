import logging
import os
import sys

LOGGING_ENABLED = os.getenv("LOGGING_ENABLED", "true").lower() == "true"

def get_logger(name: str):
    logger = logging.getLogger(name)

    if not LOGGING_ENABLED:
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        return logger

    if logger.handlers:
        return logger  # уже инициализирован

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler("app.log", encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

    return logger
