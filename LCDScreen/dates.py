#!/usr/bin/env python3
"""
Description
-----------
Reusable functions for date/time manipulation
"""
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "America/Chicago"


def get_current_datetime_at_tz(tzname: str = DEFAULT_TIMEZONE) -> datetime:
    """
    Description
    -----------
    Given a timezone, get the current time according to that timezone as a
    timezone aware datetime object

    Params
    ------
    :tzname: str = "America/Chicago"
    The timezone to get the current time for

    Return
    ------
    datetime
    The timezone aware datetime object
    """
    return datetime.now(tz=ZoneInfo(tzname))
