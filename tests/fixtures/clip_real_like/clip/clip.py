"""
Main interface functions for loading CLIP models and tokenizing text queries.
"""

from .model import build_model
from .simple_tokenizer import SimpleTokenizer

_tokenizer = SimpleTokenizer()


def available_models() -> list[str]:
    """Returns the names of available CLIP models."""
    return ["ViT-B/32", "ViT-B/16", "RN50"]


def load(name: str = "ViT-B/32", device: str = "cpu"):
    """
    Load a CLIP model and its visual preprocessing transform.
    Returns the loaded neural network model and torchvision preprocessing pipeline.
    """
    model = build_model(name, device=device)
    preprocess = lambda img: img
    return model, preprocess


def tokenize(texts: list[str]) -> list[list[int]]:
    """
    Tokenize input strings into tensor token sequences for the transformer.
    Returns integer token ids with start and end of sequence markers.
    """
    return [_tokenizer.encode(t) for t in texts]
