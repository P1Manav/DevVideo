"""A tiny module with a single utility function."""


def clean_text(text: str) -> str:
    """Normalize input text by removing extraneous whitespace."""
    if not text:
        return ""
    words = text.strip().split()
    return " ".join(words)
