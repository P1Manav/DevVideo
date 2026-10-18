"""Example script to extract a thumbnail."""
import ffmpeg

def generate_thumbnail(in_filename, out_filename, time):
    """Generate a video thumbnail."""
    ffmpeg.run(in_filename)
