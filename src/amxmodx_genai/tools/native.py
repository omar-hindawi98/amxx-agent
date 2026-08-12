"""Native sidecar tools - resolved in Python, no game server round-trip.

Add more @tool functions here to make them available to every agent automatically.
"""

from datetime import datetime

from strands import tool


@tool
def current_datetime() -> str:
    """Returns the current date and time in ISO 8601 format. Use when you need to know
    what time or date it is right now."""
    return datetime.now().isoformat(timespec="seconds")


def get_all() -> list:
    """Return all native tools defined in this module."""
    return [current_datetime]
