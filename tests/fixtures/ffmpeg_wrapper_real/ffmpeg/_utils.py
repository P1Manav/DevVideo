"""Internal utilities."""

def escape_chars(text):
    """Escape special characters."""
    return text.replace(":", "\\:")
