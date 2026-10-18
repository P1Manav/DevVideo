"""Filter nodes and operations for ffmpeg-python."""

def filter(stream_spec, filter_name, *args, **kwargs):
    """Apply a filter to the supplied stream."""
    return {'filter': filter_name, 'args': args}
