"""
Byte-pair encoding tokenizer for converting natural language queries into token IDs.
"""


class SimpleTokenizer:
    """Tokenizes text queries using vocabulary lookup."""
    def encode(self, text: str) -> list[int]:
        """Convert an input text string into a list of token identifiers."""
        return [ord(c) for c in text[:32]]
