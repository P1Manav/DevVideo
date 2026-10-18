"""Example script demonstrating extracting a video thumbnail."""
import ffmpeg


def generate_thumbnail(in_filename: str, out_filename: str, time: int = 1):
    """Generate a single thumbnail JPEG frame at the given timestamp."""
    (
        ffmpeg
        .input(in_filename, ss=time)
        .filter('scale', 320, -1)
        .output(out_filename, vframes=1)
        .run()
    )
