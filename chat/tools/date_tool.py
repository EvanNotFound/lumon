from datetime import datetime
import pytz
from langchain_core.tools import tool
from typing import Optional, Union
from dateutil import parser
from utils.date import get_montreal_time

@tool
def parse_date(date_input: Optional[Union[str, datetime]] = None) -> dict:
    """Parse a date string or datetime object and return formatted date information.
    
    Args:
        date_input: Can be:
            - None (returns current time)
            - datetime object
            - ISO format string (2024-02-20)
            - Natural language (tomorrow, next friday, feb 20)
            - Full datetime string (2024-02-20 15:30:00)
    
    Returns:
        Dictionary containing formatted date information
    """
    try:
        if date_input is None:
            return get_montreal_time()
            
        if isinstance(date_input, datetime):
            return get_montreal_time(date_input)
            
        if isinstance(date_input, str):
            # Try to parse the string into a datetime object
            parsed_date = parser.parse(date_input)
            return get_montreal_time(parsed_date)
            
    except (ValueError, TypeError) as e:
        return {
            "error": f"Could not parse date input: {str(e)}",
            "valid_formats": [
                "2024-02-20",
                "2024-02-20 15:30:00",
                "tomorrow",
                "next friday",
                "feb 20"
            ]
        } 