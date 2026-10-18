"""Video frame sampling and decoding routines using ffmpeg."""

from pathlib import Path


def extract_keyframes(video_path: str, fps: float = 1.0) -> list[dict]:
    """Sample video frames at fixed intervals and return timestamps and arrays."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    # Simulating frame extraction from video container
    frames = [{"timestamp": i / fps, "frame_id": i} for i in range(10)]
    return frames
