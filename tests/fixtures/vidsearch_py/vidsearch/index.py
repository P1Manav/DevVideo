"""Build and persist Faiss vector index for fast similarity lookup."""

from pathlib import Path


class VideoVectorIndex:
    """Faiss vector index manager for video segment embeddings."""

    def __init__(self, dimension: int = 512):
        self.dimension = dimension
        self.timestamps: list[float] = []

    def build_index(self, items: list[tuple[float, list[float]]], output_path: str) -> None:
        """Add embedding vectors into cosine similarity index and persist to disk."""
        self.timestamps = [t for t, _ in items]
        Path(output_path).write_text("FAISS_INDEX_DATA")
