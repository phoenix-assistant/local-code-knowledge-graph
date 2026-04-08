"""Base parser interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ckg.graph.models import ClassNode, Edge, FunctionNode, ImportNode, VariableNode


@dataclass
class ParseResult:
    """Result of parsing a source file."""

    functions: list[FunctionNode] = field(default_factory=list)
    classes: list[ClassNode] = field(default_factory=list)
    imports: list[ImportNode] = field(default_factory=list)
    variables: list[VariableNode] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BaseParser(ABC):
    """Abstract base class for language parsers."""

    language: str

    @abstractmethod
    def parse(self, source: str, file_id: str, file_path: str) -> ParseResult:
        """Parse source code and extract symbols.

        Args:
            source: Source code content
            file_id: Unique file identifier
            file_path: Path to the file

        Returns:
            ParseResult with extracted symbols
        """
        pass

    @abstractmethod
    def get_extensions(self) -> list[str]:
        """Get file extensions handled by this parser."""
        pass
