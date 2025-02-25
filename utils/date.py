from datetime import datetime
import pytz

def get_montreal_time(timestamp=None):
    """Get current time in Montreal with additional context.
    
    Args:
        timestamp (datetime, optional): A datetime object to convert. If None, uses current time.
    """
    montreal_tz = pytz.timezone('America/Montreal')
    
    if timestamp is None:
        current_time = datetime.now(montreal_tz)
    else:
        # If timestamp is naive (no timezone), assume UTC
        if timestamp.tzinfo is None:
            timestamp = pytz.UTC.localize(timestamp)
        current_time = timestamp.astimezone(montreal_tz)
    
    # Format with day name, date, time, and timezone
    time_context = {
        "datetime": current_time,
        "formatted": current_time.strftime("%A, %B %d, %Y at %I:%M %p, Montreal (EDT/EST)"),
        "day_of_week": current_time.strftime("%A"),
        "date": current_time.strftime("%B %d, %Y"),
        "time": current_time.strftime("%I:%M %p"),
        "timezone": "Montreal (EDT/EST)"
    }
    return time_context