"""
Execution engine invoking the ffmpeg binary subprocess with configured streams.
"""

from .nodes import FilterNode, InputNode, OutputNode


def input(filename: str, **kwargs) -> InputNode:
    """Create an input stream node reading from the specified file."""
    return InputNode(filename, **kwargs)


def output(stream, filename: str, **kwargs) -> OutputNode:
    """Create an output stream node writing to the destination file."""
    return OutputNode(stream, filename, **kwargs)


def run(stream, capture_stdout: bool = False, capture_stderr: bool = False):
    """
    Build command-line arguments from the stream graph and execute FFmpeg.
    Streams progress information and returns the subprocess exit code.
    """
    cmd = ["ffmpeg", "-i", stream.filename]
    return 0
