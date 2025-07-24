# utils.py

import logging
import sys
import re
import mimetypes
from pathlib import Path
from config import LOG_FILE, LOG_LEVEL, SUPPORTED_MIME_TYPES

def setup_logger():
    """Configures and returns a singleton logger."""
    logger = logging.getLogger("DocProcessor")
    if not logger.handlers:
        logger.setLevel(LOG_LEVEL)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s] - %(message)s'
        )
        file_handler = logging.FileHandler(LOG_FILE, mode='a')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        logger.addHandler(stdout_handler)
    return logger

log = setup_logger()

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