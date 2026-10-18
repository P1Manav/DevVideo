"""Command line interface for querying images with CLIP embeddings."""

import argparse
from clip_tool.model import load_model, encode_image, encode_text


def parse_args():
    """Parse CLI flags for querying images with CLIP."""
    parser = argparse.ArgumentParser(description="CLIP visual search tool")
    parser.add_argument("--image", type=str, required=True, help="Path to input image frame")
    parser.add_argument("--query", type=str, required=True, help="Natural language search query")
    parser.add_argument("--top-k", type=int, default=5, help="Number of top results to return")
    return parser.parse_args()


def main():
    """Main entry point orchestrating model loading and similarity comparison."""
    args = parse_args()
    model = load_model()
    img_emb = encode_image(model, args.image)
    txt_emb = encode_text(model, args.query)
    return img_emb, txt_emb


if __name__ == "__main__":
    main()
