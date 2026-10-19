"""Audio and video filter constructors for ffmpeg."""
from .nodes import Node

def filter(stream_spec, filter_name):
    """Apply a filter to the supplied stream."""
    return Node(filter_name)
