"""Command-line interface for VidSearch video retrieval engine."""

import argparse
from vidsearch.search import search_video_index


def parse_args():
    """Parse CLI flags for indexing and querying videos."""
    parser = argparse.ArgumentParser(description="VidSearch CLI query tool")
    parser.add_argument("--query", type=str, required=True, help="Natural language search query")
    parser.add_argument("--index", type=str, default="index.faiss", help="Path to Faiss vector index")
    parser.add_argument("--fps", type=float, default=1.0, help="Frames per second sampling rate")
    parser.add_argument("--top-k", type=int, default=5, help="Number of top video segments to return")
    return parser.parse_args()


def main():
    """Run CLI search execution."""
    args = parse_args()
    results = search_video_index(args.query, index_path=args.index, top_k=args.top_k)
    for rank, (timestamp, score) in enumerate(results, start=1):
        print(f"[{rank}] Match at {timestamp:.2f}s (score: {score:.3f})")


if __name__ == "__main__":
    main()
