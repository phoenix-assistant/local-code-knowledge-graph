"""Go parser using Tree-sitter."""

import tree_sitter_go as tsgo
from tree_sitter import Language, Node, Parser

from ckg.graph.models import (
    ClassNode,
    Edge,
    EdgeType,
    FunctionNode,
    ImportNode,
    VariableNode,
)
from ckg.parsing.base import BaseParser, ParseResult


class GoParser(BaseParser):
    """Parser for Go source code."""

    language = "go"

    def __init__(self):
        """Initialize Go parser."""
        self._parser = Parser(Language(tsgo.language()))

    def get_extensions(self) -> list[str]:
        """Get Go file extensions."""
        return [".go"]

    def parse(self, source: str, file_id: str, file_path: str) -> ParseResult:
        """Parse Go source code."""
        result = ParseResult()
        tree = self._parser.parse(source.encode())

        self._extract_imports(tree.root_node, file_id, source, result)
        self._extract_types(tree.root_node, file_id, source, result)
        self._extract_functions(tree.root_node, file_id, source, result)
        self._extract_variables(tree.root_node, file_id, source, result)

        return result

    def _get_text(self, node: Node, source: str) -> str:
        """Extract text from a node."""
        return source[node.start_byte:node.end_byte]

    def _extract_docstring(self, node: Node, source: str) -> str | None:
        """Extract comment before a declaration."""
        lines = source[:node.start_byte].rstrip().split("\n")
        comments = []
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith("//"):
                comments.insert(0, stripped[2:].strip())
            elif stripped == "" and comments:
                continue
            else:
                break
        return "\n".join(comments) if comments else None

    def _extract_imports(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract import statements."""
        for node in root.children:
            if node.type == "import_declaration":
                for child in self._walk_tree(node):
                    if child.type == "import_spec":
                        path_node = child.child_by_field_name("path")
                        name_node = child.child_by_field_name("name")

                        if path_node:
                            module = self._get_text(path_node, source).strip('"')
                            alias = self._get_text(name_node, source) if name_node else None

                            import_id = f"import:{file_id}:{module}"
                            result.imports.append(
                                ImportNode(
                                    id=import_id,
                                    name=alias or module.split("/")[-1],
                                    file_id=file_id,
                                    module=module,
                                    alias=alias,
                                    line=child.start_point[0] + 1,
                                )
                            )
                            result.edges.append(
                                Edge(
                                    source_id=file_id,
                                    target_id=import_id,
                                    type=EdgeType.IMPORTS,
                                )
                            )

    def _extract_types(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract type definitions (structs, interfaces)."""
        for node in root.children:
            if node.type == "type_declaration":
                for child in node.children:
                    if child.type == "type_spec":
                        name_node = child.child_by_field_name("name")
                        type_node = child.child_by_field_name("type")

                        if not name_node:
                            continue

                        name = self._get_text(name_node, source)
                        class_id = f"class:{file_id}:{name}"

                        docstring = self._extract_docstring(node, source)

                        # Extract embedded types (inheritance-like)
                        bases = []
                        if type_node and type_node.type in ("struct_type", "interface_type"):
                            for field in type_node.children:
                                if field.type == "field_declaration":
                                    # Embedded field (no name, just type)
                                    field_name = field.child_by_field_name("name")
                                    if not field_name:
                                        field_type = field.child_by_field_name("type")
                                        if field_type:
                                            bases.append(self._get_text(field_type, source))

                        result.classes.append(
                            ClassNode(
                                id=class_id,
                                name=name,
                                file_id=file_id,
                                docstring=docstring,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                bases=bases,
                            )
                        )

                        result.edges.append(
                            Edge(
                                source_id=file_id,
                                target_id=class_id,
                                type=EdgeType.DEFINES,
                            )
                        )

                        # Add inheritance edges
                        for base in bases:
                            result.edges.append(
                                Edge(
                                    source_id=class_id,
                                    target_id=f"class:*:{base}",
                                    type=EdgeType.INHERITS,
                                    metadata={"unresolved": True},
                                )
                            )

    def _extract_functions(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract function and method declarations."""
        for node in root.children:
            if node.type in ("function_declaration", "method_declaration"):
                name_node = node.child_by_field_name("name")
                if not name_node:
                    continue

                name = self._get_text(name_node, source)
                is_method = node.type == "method_declaration"

                # Get receiver type for methods
                receiver_type = None
                if is_method:
                    receiver = node.child_by_field_name("receiver")
                    if receiver:
                        for child in receiver.children:
                            if child.type == "parameter_declaration":
                                type_node = child.child_by_field_name("type")
                                if type_node:
                                    receiver_type = self._get_text(type_node, source)
                                    # Remove pointer
                                    if receiver_type.startswith("*"):
                                        receiver_type = receiver_type[1:]

                class_id = f"class:{file_id}:{receiver_type}" if receiver_type else None
                func_id = f"func:{file_id}:{receiver_type or 'module'}:{name}"

                # Extract parameters
                params_node = node.child_by_field_name("parameters")
                params = []
                if params_node:
                    for child in params_node.children:
                        if child.type == "parameter_declaration":
                            param_name = child.child_by_field_name("name")
                            if param_name:
                                params.append(self._get_text(param_name, source))

                # Extract return type
                result_node = node.child_by_field_name("result")
                return_type = self._get_text(result_node, source) if result_node else None

                # Build signature
                params_text = self._get_text(params_node, source) if params_node else "()"
                signature = f"func {name}{params_text}"
                if return_type:
                    signature += f" {return_type}"

                docstring = self._extract_docstring(node, source)

                result.functions.append(
                    FunctionNode(
                        id=func_id,
                        name=name,
                        file_id=file_id,
                        signature=signature,
                        docstring=docstring,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        is_method=is_method,
                        class_id=class_id,
                        parameters=params,
                        return_type=return_type,
                    )
                )

                if class_id:
                    result.edges.append(
                        Edge(source_id=class_id, target_id=func_id, type=EdgeType.CONTAINS)
                    )
                else:
                    result.edges.append(
                        Edge(source_id=file_id, target_id=func_id, type=EdgeType.DEFINES)
                    )

    def _extract_variables(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract package-level variables and constants."""
        for node in root.children:
            if node.type in ("var_declaration", "const_declaration"):
                for child in node.children:
                    if child.type == "var_spec" or child.type == "const_spec":
                        name_node = child.child_by_field_name("name")
                        if not name_node:
                            # Handle multiple names
                            for n in child.children:
                                if n.type == "identifier":
                                    name = self._get_text(n, source)
                                    var_id = f"var:{file_id}:module:{name}"

                                    type_node = child.child_by_field_name("type")
                                    type_hint = self._get_text(type_node, source) if type_node else None

                                    result.variables.append(
                                        VariableNode(
                                            id=var_id,
                                            name=name,
                                            file_id=file_id,
                                            type_hint=type_hint,
                                            line=child.start_point[0] + 1,
                                            scope="module",
                                        )
                                    )
                        else:
                            name = self._get_text(name_node, source)
                            var_id = f"var:{file_id}:module:{name}"

                            type_node = child.child_by_field_name("type")
                            type_hint = self._get_text(type_node, source) if type_node else None

                            result.variables.append(
                                VariableNode(
                                    id=var_id,
                                    name=name,
                                    file_id=file_id,
                                    type_hint=type_hint,
                                    line=child.start_point[0] + 1,
                                    scope="module",
                                )
                            )

    def _walk_tree(self, node: Node):
        """Walk all nodes in a tree."""
        yield node
        for child in node.children:
            yield from self._walk_tree(child)
