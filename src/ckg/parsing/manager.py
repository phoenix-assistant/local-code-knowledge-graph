"""Parser manager for multiple languages."""

from pathlib import Path

from ckg.parsing.base import BaseParser, ParseResult
from ckg.parsing.go_parser import GoParser
from ckg.parsing.python_parser import PythonParser
from ckg.parsing.rust_parser import RustParser
from ckg.parsing.typescript_parser import JavaScriptParser, TypeScriptParser


class ParserManager:
    """Manages parsers for different languages."""

    def __init__(self):
        """Initialize with default parsers."""
        self._parsers: dict[str, BaseParser] = {}
        self._extension_map: dict[str, str] = {}

        # Register default parsers
        self.register(PythonParser())
        self.register(TypeScriptParser())
        self.register(JavaScriptParser())
        self.register(GoParser())
        self.register(RustParser())

    def register(self, parser: BaseParser) -> None:
        """Register a parser."""
        self._parsers[parser.language] = parser
        for ext in parser.get_extensions():
            self._extension_map[ext] = parser.language

    def get_parser(self, language: str) -> BaseParser | None:
        """Get parser for a language."""
        return self._parsers.get(language)

    def get_parser_for_file(self, file_path: str | Path) -> BaseParser | None:
        """Get parser for a file based on extension."""
        path = Path(file_path)
        ext = path.suffix.lower()
        language = self._extension_map.get(ext)
        if language:
            return self._parsers.get(language)
        return None

    def parse_file(self, file_path: str | Path, file_id: str) -> ParseResult | None:
        """Parse a file and return results."""
        path = Path(file_path)
        parser = self.get_parser_for_file(path)
        if not parser:
            return None

        try:
            source = path.read_text(encoding="utf-8")
            return parser.parse(source, file_id, str(path))
        except Exception as e:
            result = ParseResult()
            result.errors.append(f"Failed to parse {path}: {e}")
            return result

    def supported_extensions(self) -> list[str]:
        """Get list of supported file extensions."""
        return list(self._extension_map.keys())

    def supported_languages(self) -> list[str]:
        """Get list of supported languages."""
        return list(self._parsers.keys())
