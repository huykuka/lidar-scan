import os
import logging
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "logs")
LOG_FILE = os.path.join(LOG_DIR, "lidar_standalone.log")

os.makedirs(LOG_DIR, exist_ok=True)

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Python 'logging' root config
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            LOG_FILE,
            maxBytes=(10 * 1024 * 1024),   # 10MB per file
            backupCount=7,                 # Last 7 rotated logs kept
            encoding="utf-8"
        )
    ]
)

def get_logger(name: str) -> logging.Logger:
    """Return a configured logger with the given module name."""
    return logging.getLogger(name)
