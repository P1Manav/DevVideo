"""Utility functions for shell argument conversion."""

def convert_kwargs_to_cmd_line_args(kwargs):
    """Convert kwargs to cmd line args."""
    args = []
    for k, v in kwargs.items():
        args.extend([f"-{k}", str(v)])
    return args
