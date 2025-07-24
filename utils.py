# utils.py

import logging
import sys
import re
import mimetypes
from pathlib import Path
from queue import Queue
from logging.handlers import QueueHandler # Import QueueHandler
from config import LOG_FILE, LOG_LEVEL, SUPPORTED_MIME_TYPES

# The formatter needs to be defined at the module level
# so the QueueHandler can format the record before putting it in the queue.
log_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s] - %(message)s'
)

class FormattedQueueHandler(QueueHandler):
    """A QueueHandler that formats the record before putting it on the queue."""
    def emit(self, record):
        # Format the record and then enqueue it
        self.enqueue(self.format(record))

def setup_logger(log_queue: Queue):
    """Configures the root logger to send records to a queue."""
    logger = logging.getLogger("DocProcessor")
    if not logger.handlers:
        logger.setLevel(LOG_LEVEL)
        
        # Add a handler that puts formatted log strings onto the queue
        queue_handler = FormattedQueueHandler(log_queue)
        queue_handler.setFormatter(log_formatter)
        logger.addHandler(queue_handler)

        # Optional: Keep file handler for persistent logs
        file_handler = logging.FileHandler(LOG_FILE, mode='a')
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)
        
        # Optional: Keep stdout handler for console output
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(log_formatter)
        logger.addHandler(stdout_handler)
    return logger

# This global 'log' object will be configured by the lifespan manager in main.py
log = logging.getLogger("DocProcessor")


def get_mime_type(file_path):
    """Determines the MIME type of a file."""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type if mime_type in SUPPORTED_MIME_TYPES else "application/octet-stream"

def parse_filename_for_grouping(filename: str) -> tuple[str, int]:
    """
    Parses a filename to extract a base name for grouping and a page number.
    Handles patterns like 'Name 1.pdf', 'Name_1.pdf', 'NamePage1.pdf', 'Name.pdf'
    """
    name_no_ext = Path(filename).stem
    page_number = 1
    base_name = name_no_ext
    match = re.search(r'(.*?)(?:[ _]|Page|-)?(\d+)$', name_no_ext, re.IGNORECASE)
    if match:
        potential_base_name, page_number_str = match.groups()
        if potential_base_name:
            base_name = potential_base_name.strip(' _-')
            page_number = int(page_number_str)
    if not base_name:
        base_name = "unknown_document"
        log.warning(f"Could not determine base name for '{filename}', using default.")
    return base_name, page_number