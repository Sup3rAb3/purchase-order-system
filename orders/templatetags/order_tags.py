from django import template
from datetime import timedelta

register = template.Library()

@register.filter
def add_hours(value, hours):
    """
    Add a specified number of hours to a datetime object.
    
    Args:
        value: A datetime object (timezone-aware or naive).
        hours: Number of hours to add (integer or string convertible to int).
    
    Returns:
        A new datetime object with the specified hours added.
    """
    try:
        hours = int(hours)
        return value + timedelta(hours=hours)
    except (ValueError, TypeError):
        return value