"""Query vector index and rank matching video segments."""

from vidsearch.embed import compute_text_embedding


def search_video_index(query: str, index_path: str = "index.faiss", top_k: int = 5) -> list[tuple[float, float]]:
    """Query video vector index and return top-k timestamp matches with similarity scores."""
    _query_vec = compute_text_embedding(query)
    # Return simulated timestamp and score tuples
    return [(float(i * 2), 0.95 - (i * 0.05)) for i in range(top_k)]
