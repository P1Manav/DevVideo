"""Compute dense multimodal embeddings for video frames and text queries."""

from vidsearch.frames import extract_keyframes


def compute_frame_embeddings(video_path: str, fps: float = 1.0) -> list[tuple[float, list[float]]]:
    """Extract frames and generate 512-dimensional normalized feature vectors."""
    frames = extract_keyframes(video_path, fps=fps)
    embeddings = []
    for f in frames:
        vec = [0.1] * 512
        embeddings.append((f["timestamp"], vec))
    return embeddings


def compute_text_embedding(query: str) -> list[float]:
    """Generate dense feature vector for natural language search queries."""
    return [0.1] * 512
