from django import template

register = template.Library()

@register.filter
def replace_underscores(value):
    """Replace underscores with spaces"""
    return value.replace('_', ' ')


@register.filter
def can_iterate(value):
    """
    Check if a value can be iterated over like a list.
    Returns True for lists, tuples, sets, etc.
    Returns False for strings, numbers, None, and dicts.
    """
    # Exclude strings and dicts even though they're technically iterable
    if isinstance(value, (str, dict)) or value is None:
        return False

    # Check if it's iterable
    try:
        iter(value)
        return True
    except TypeError:
        return False


@register.filter
def get_ordered_fields(summary_data):
    """
    Returns summary_data fields in a specific order, with remaining fields at the end.
    Returns a list of (key, value) tuples.
    """
    FIELD_ORDER = [
        "title", "stock_ticker", "source", "authors", "sentiment",
        "price_target", "stock_rating", "recap", "summary",
        "executive_summary", "expectations", "risk_points",
        "opportunity_points", "bull_points", "bear_points",
        "key_themes", "key_dynamics", "positive_dynamics",
        "negative_dynamics", "upside_valuation",
        "downside_valuation", "valuation_analysis",
        "stock_recaps", "strategic_recommendations",
        "conclusion", "extra_details",
    ]

    if not summary_data:
        return []

    ordered_items = []
    displayed_keys = set()

    # First, add fields in the specified order
    for field in FIELD_ORDER:
        if field in summary_data and summary_data[field]:
            ordered_items.append((field, summary_data[field]))
            displayed_keys.add(field)

    # Then, add any remaining fields
    for key, value in summary_data.items():
        if key not in displayed_keys and value:
            ordered_items.append((key, value))

    return ordered_items


@register.filter
def is_dict(value):
    """Check if value is a dictionary."""
    return isinstance(value, dict)