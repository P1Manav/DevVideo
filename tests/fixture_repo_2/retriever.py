"""Core retrieval module for VideoRetriever."""


class VideoIndex:
    @staticmethod
    def load(path: str) -> "VideoIndex":
        """Load index file."""
        return VideoIndex()

    def query(self, text: str) -> list[str]:
        """Search the video index."""
        return [f"result_for_{text}"]
