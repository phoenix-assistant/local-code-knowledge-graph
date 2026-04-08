# Contributing to Local Code Knowledge Graph

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing.

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/phoenix-assistant/local-code-knowledge-graph.git
cd local-code-knowledge-graph
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install development dependencies:
```bash
pip install -e ".[dev]"
```

4. Install pre-commit hooks:
```bash
pre-commit install
```

## Code Style

- We use [ruff](https://github.com/astral-sh/ruff) for linting and formatting
- Type hints are required for all public functions
- Docstrings follow Google style

Run linting:
```bash
ruff check src tests
ruff format src tests
```

Run type checking:
```bash
mypy src
```

## Testing

Run tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=src/ckg --cov-report=html
```

## Adding a New Language Parser

1. Create a new parser in `src/ckg/parsing/`:

```python
# src/ckg/parsing/java_parser.py
import tree_sitter_java as tsjava
from tree_sitter import Language, Parser

from ckg.parsing.base import BaseParser, ParseResult


class JavaParser(BaseParser):
    language = "java"

    def __init__(self):
        self._parser = Parser(Language(tsjava.language()))

    def get_extensions(self) -> list[str]:
        return [".java"]

    def parse(self, source: str, file_id: str, file_path: str) -> ParseResult:
        # Implement parsing logic
        pass
```

2. Register the parser in `src/ckg/parsing/manager.py`:

```python
from ckg.parsing.java_parser import JavaParser

class ParserManager:
    def __init__(self):
        # ...
        self.register(JavaParser())
```

3. Add tests in `tests/test_parsing.py`

4. Update documentation

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Commit Messages

Follow conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `test:` Adding tests
- `refactor:` Code refactoring
- `chore:` Maintenance tasks

## Reporting Issues

When reporting issues, please include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or error messages

## Questions?

Feel free to open a discussion or issue if you have questions!
