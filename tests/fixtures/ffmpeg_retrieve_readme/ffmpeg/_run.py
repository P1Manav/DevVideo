"""Execution runner for FFmpeg node graphs."""
import subprocess
from ._utils import convert_kwargs_to_cmd_line_args

def run(stream_spec, **kwargs):
    """Invoke ffmpeg for the supplied node graph."""
    args = convert_kwargs_to_cmd_line_args(kwargs)
    return subprocess.run(["ffmpeg"] + args)
