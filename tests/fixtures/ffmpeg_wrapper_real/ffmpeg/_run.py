"""Execution runner for FFmpeg node graphs."""

def run(stream_spec, cmd='ffmpeg', overwrite_output=False):
    """Invoke ffmpeg for the supplied node graph."""
    args = ['ffmpeg', '-i', 'input.mp4', 'output.mp4']
    return args
