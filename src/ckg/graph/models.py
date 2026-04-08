"""Graph node and edge models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Types of nodes in the code knowledge graph."""

    FILE = "file"
    FUNCTION = "function"
    CLASS = "class"
    IMPORT = "import"
    VARIABLE = "variable"


class EdgeType(str, Enum):
    """Types of edges in the code knowledge graph."""

    DEFINES = "defines"  # File → Function/Class
    CONTAINS = "contains"  # Class → Function (methods)
    IMPORTS = "imports"  # File → Import
    CALLS = "calls"  # Function → Function
    INHERITS = "inherits"  # Class → Class
    USES = "uses"  # Function → Variable


class BaseNode(BaseModel):
    """Base node with common attributes."""

    id: str = Field(..., description="Unique node identifier")
    type: NodeType = Field(..., description="Node type")
    name: str = Field(..., description="Node name")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    def __hash__(self) -> int:
        return hash(self.id)


class FileNode(BaseNode):
    """Represents a source file."""

    type: NodeType = NodeType.FILE
    path: str = Field(..., description="File path relative to repo root")
    language: str = Field(..., description="Programming language")
    last_modified: datetime = Field(..., description="Last modification timestamp")
    size_bytes: int = Field(0, description="File size in bytes")
    line_count: int = Field(0, description="Number of lines")


class FunctionNode(BaseNode):
    """Represents a function or method."""

    type: NodeType = NodeType.FUNCTION
    file_id: str = Field(..., description="Parent file ID")
    signature: str = Field("", description="Function signature")
    docstring: str | None = Field(None, description="Function docstring")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    is_async: bool = Field(False, description="Whether function is async")
    is_method: bool = Field(False, description="Whether function is a class method")
    class_id: str | None = Field(None, description="Parent class ID if method")
    parameters: list[str] = Field(default_factory=list, description="Parameter names")
    return_type: str | None = Field(None, description="Return type annotation")


class ClassNode(BaseNode):
    """Represents a class definition."""

    type: NodeType = NodeType.CLASS
    file_id: str = Field(..., description="Parent file ID")
    docstring: str | None = Field(None, description="Class docstring")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    bases: list[str] = Field(default_factory=list, description="Base class names")
    decorators: list[str] = Field(default_factory=list, description="Decorator names")


class ImportNode(BaseNode):
    """Represents an import statement."""

    type: NodeType = NodeType.IMPORT
    file_id: str = Field(..., description="File containing the import")
    module: str = Field(..., description="Imported module")
    alias: str | None = Field(None, description="Import alias (as X)")
    items: list[str] = Field(default_factory=list, description="Imported items (from X import ...)")
    line: int = Field(..., description="Line number of import")


class VariableNode(BaseNode):
    """Represents a module-level or class-level variable."""

    type: NodeType = NodeType.VARIABLE
    file_id: str = Field(..., description="Parent file ID")
    type_hint: str | None = Field(None, description="Type annotation")
    line: int = Field(..., description="Line number")
    scope: str = Field("module", description="Variable scope (module, class, function)")
    class_id: str | None = Field(None, description="Parent class ID if class variable")


class Edge(BaseModel):
    """Represents an edge between two nodes."""

    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    type: EdgeType = Field(..., description="Edge type")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    def __hash__(self) -> int:
        return hash((self.source_id, self.target_id, self.type))
