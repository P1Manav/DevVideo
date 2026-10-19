"""
Data models and constants for semantic repository analysis.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from ..schema import SourceSpan

RELEVANCE_KEYWORDS = [
    "video", "frame", "frames", "clip", "clips",
    "embedding", "embeddings", "retrieval", "index", "vector",
    "vectors", "faiss", "whisper", "ffmpeg", "transcript",
    "transcripts", "multimodal",
]

EXTENSION_LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".html": "HTML",
    ".css": "CSS",
    ".md": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".sh": "Shell",
    ".bash": "Shell",
}

DEPENDENCY_ROLES = {
    "faiss": "vector index",
    "faiss-cpu": "vector index",
    "faiss-gpu": "vector index",
    "ffmpeg": "video decoding",
    "ffmpeg-python": "video decoding",
    "opencv-python": "frame processing",
    "opencv": "frame processing",
    "cv2": "frame processing",
    "torch": "neural network",
    "torchvision": "computer vision",
    "torchaudio": "audio processing",
    "transformers": "embeddings",
    "clip": "embeddings",
    "whisper": "speech transcription",
    "openai-whisper": "speech transcription",
    "numpy": "array math",
    "scipy": "scientific computing",
    "flask": "web API",
    "fastapi": "web API",
    "pytest": "tests",
    "pillow": "image processing",
    "pil": "image processing",
    "tqdm": "progress bars",
    "playwright": "browser automation",
    "pydantic": "data validation",
}

STAGE_KEYWORDS = {
    "decode": ["decode", "decoding", "decoder", "frame", "frames"],
    "embed": ["embed", "embedding", "embeddings"],
    "index": ["index", "indexing"],
    "query": ["query", "search", "retrieval", "retrieve"],
    "transcribe": ["transcribe", "transcription", "speech-to-text", "speech recognition"],
    "serve": ["serve", "serving", "server"],
}


class ReadmeSentence(BaseModel):
    """Cleaned sentence from README with source line span."""
    text: str
    start_line: int
    end_line: int
    raw_text: str = ""


class CleanedReadme(BaseModel):
    """Sanitized and structured README data."""
    title: str = ""
    tagline: str = ""
    description: str = ""
    description_sentences: list[ReadmeSentence] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    feature_sentences: list[ReadmeSentence] = Field(default_factory=list)
    sections: dict[str, str] = Field(default_factory=dict)
    code_fences: list[str] = Field(default_factory=list)
    install_commands: list[str] = Field(default_factory=list)
    usage_commands: list[str] = Field(default_factory=list)
    raw_lines: list[str] = Field(default_factory=list)


class CliFlag(BaseModel):
    """CLI flag with its help documentation."""
    flag: str
    help: str = ""


class TopSymbol(BaseModel):
    """Function or class symbol extracted from source code."""
    name: str
    kind: str  # "function" | "class"
    file: str  # relative POSIX path
    docstring: str = ""
    docstring_span: SourceSpan | None = None
    start_line: int
    end_line: int
    def_line: str = ""
    code_excerpt: str = ""
    calls: list[str] = Field(default_factory=list)


class ModuleDocstring(BaseModel):
    """Top-level module docstring with source span."""
    file: str
    docstring: str
    span: SourceSpan

    @property
    def start_line(self) -> int:
        return self.span.start_line

    @property
    def end_line(self) -> int:
        return self.span.end_line


class ImportEdge(BaseModel):
    """Directed dependency edge between internal modules."""
    source: str
    target: str
    raw_line: str = ""
    line_number: int = 1


class RepoFacts(BaseModel):
    """Comprehensive semantic facts about a repository."""
    repo_name: str
    owner: str | None = None
    commit_sha: str = ""
    languages_by_bytes: dict[str, int] = Field(default_factory=dict)
    tree: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    entry_module: str = ""
    ranked_top_modules: list[str] = Field(default_factory=list)
    import_graph: list[ImportEdge] = Field(default_factory=list)
    top_symbols: list[TopSymbol] = Field(default_factory=list)
    module_docstrings: list[ModuleDocstring] = Field(default_factory=list)
    cli_flags: list[str] = Field(default_factory=list)
    cli_flag_details: list[CliFlag] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    dependency_roles: dict[str, str] = Field(default_factory=dict)
    pipeline_stages: dict[str, str] = Field(default_factory=dict)
    readme: CleanedReadme = Field(default_factory=CleanedReadme)
    readme_file: str = ""
    relevance_score: float = 0.0
    matched_relevance_terms: list[str] = Field(default_factory=list)
    is_video_relevant: bool = False
