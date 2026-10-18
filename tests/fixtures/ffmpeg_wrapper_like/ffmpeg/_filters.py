"""
Audio and video filter constructors for assembling complex ffmpeg filtergraphs.
"""

from .nodes import FilterNode


def filter(stream, filter_name: str, *args, **kwargs) -> FilterNode:
    """Apply a custom filter to an incoming audio or video stream."""
    return FilterNode(stream, filter_name, *args, **kwargs)


def hflip(stream) -> FilterNode:
    """Horizontally flip the video stream frames."""
    return filter(stream, "hflip")
