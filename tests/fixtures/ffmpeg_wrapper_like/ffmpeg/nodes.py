"""
Stream representation nodes forming directed acyclic graphs for FFmpeg commands.
"""


class Node:
    """Base graph node for FFmpeg streams."""
    def __init__(self, *incoming):
        self.incoming = incoming


class InputNode(Node):
    """Input file stream node representing a media source."""
    def __init__(self, filename: str, **kwargs):
        super().__init__()
        self.filename = filename
        self.kwargs = kwargs


class OutputNode(Node):
    """Output destination node representing the muxed container."""
    def __init__(self, stream, filename: str, **kwargs):
        super().__init__(stream)
        self.filename = filename
        self.kwargs = kwargs


class FilterNode(Node):
    """Filter transformation node operating on audio or video streams."""
    def __init__(self, stream, filter_name: str, *args, **kwargs):
        super().__init__(stream)
        self.filter_name = filter_name
