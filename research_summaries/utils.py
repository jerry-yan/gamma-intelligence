# research_summaries/utils.py
import re
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def extract_publication_date_from_filename(filename: str) -> Optional[datetime.date]:
    """
    Extract publication date from PDF filename.

    Expected format: "20250529 - BofA Global Research - TSLA - Internet e Commerce Tesla - 7 pages.pdf"
    Date format: YYYYMMDD at the beginning of filename

    Args:
        filename (str): The PDF filename

    Returns:
        datetime.date or None: Extracted date or None if not found/invalid
    """
    try:
        # Remove file extension and get just the base name
        base_name = filename.replace('.pdf', '').replace('.PDF', '')

        # Look for 8 digits at the beginning of the filename (YYYYMMDD)
        date_match = re.match(r'^(\d{8})', base_name)

        if date_match:
            date_str = date_match.group(1)

            # Parse the date string (YYYYMMDD)
            try:
                parsed_date = datetime.strptime(date_str, '%Y%m%d').date()

                # Validate the date is reasonable (not too old, not in future)
                current_date = datetime.now().date()
                min_date = datetime(2000, 1, 1).date()  # Not older than 2000

                if min_date <= parsed_date <= current_date:
                    logger.info(f"Extracted publication date {parsed_date} from filename: {filename}")
                    return parsed_date
                else:
                    logger.warning(f"Date {parsed_date} from filename {filename} is out of reasonable range")
                    return None

            except ValueError as e:
                logger.warning(f"Invalid date format in filename {filename}: {date_str} - {e}")
                return None
        else:
            logger.info(f"No date pattern found at beginning of filename: {filename}")
            return None

    except Exception as e:
        logger.error(f"Error extracting date from filename {filename}: {e}")
        return None