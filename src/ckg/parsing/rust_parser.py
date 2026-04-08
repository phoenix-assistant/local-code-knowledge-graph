"""Rust parser using Tree-sitter."""

import tree_sitter_rust as tsrust
from tree_sitter import Language, Parser, Node

from ckg.graph.models import (
    ClassNode,
    Edge,
    EdgeType,
    FunctionNode,
    ImportNode,
    VariableNode,
)
from ckg.parsing.base import BaseParser, ParseResult


class RustParser(BaseParser):
    """Parser for Rust source code."""

    language = "rust"

    def __init__(self):
        """Initialize Rust parser."""
        self._parser = Parser(Language(tsrust.language()))

    def get_extensions(self) -> list[str]:
        """Get Rust file extensions."""
        return [".rs"]

    def parse(self, source: str, file_id: str, file_path: str) -> ParseResult:
        """Parse Rust source code."""
        result = ParseResult()
        tree = self._parser.parse(source.encode())

        self._extract_uses(tree.root_node, file_id, source, result)
        self._extract_structs(tree.root_node, file_id, source, result)
        self._extract_functions(tree.root_node, file_id, None, source, result)
        self._extract_constants(tree.root_node, file_id, source, result)

        return result

    def _get_text(self, node: Node, source: str) -> str:
        """Extract text from a node."""
        return source[node.start_byte:node.end_byte]

    def _extract_docstring(self, node: Node, source: str) -> str | None:
        """Extract doc comments before a declaration."""
        lines = source[:node.start_byte].rstrip().split("\n")
        comments = []
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith("///") or stripped.startswith("//!"):
                comments.insert(0, stripped[3:].strip())
            elif stripped == "" and comments:
                continue
            else:
                break
        return "\n".join(comments) if comments else None

    def _extract_uses(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract use statements."""
        for node in self._walk_tree(root):
            if node.type == "use_declaration":
                # Get the full use path
                use_tree = None
                for child in node.children:
                    if child.type in ("scoped_identifier", "identifier", "use_tree", "scoped_use_list"):
                        use_tree = child
                        break

                if use_tree:
                    module = self._get_text(use_tree, source)
                    import_id = f"import:{file_id}:{module}"
                    result.imports.append(
                        ImportNode(
                            id=import_id,
                            name=module,
                            file_id=file_id,
                            module=module,
                            line=node.start_point[0] + 1,
                        )
                    )
                    result.edges.append(
                        Edge(
                            source_id=file_id,
                            target_id=import_id,
                            type=EdgeType.IMPORTS,
                        )
                    )

    def _extract_structs(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract struct, enum, and trait definitions."""
        for node in root.children:
            if node.type in ("struct_item", "enum_item", "trait_item"):
                name_node = node.child_by_field_name("name")
                if not name_node:
                    continue

                name = self._get_text(name_node, source)
                class_id = f"class:{file_id}:{name}"
                docstring = self._extract_docstring(node, source)

                # Extract trait bounds (inheritance-like)
                bases = []
                type_params = node.child_by_field_name("type_parameters")
                if type_params:
                    for child in self._walk_tree(type_params):
                        if child.type == "trait_bound":
                            bases.append(self._get_text(child, source))

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
                    Edge(source_id=file_id, target_id=class_id, type=EdgeType.DEFINES)
                )

            # Handle impl blocks
            elif node.type == "impl_item":
                type_node = node.child_by_field_name("type")
                if not type_node:
                    continue

                type_name = self._get_text(type_node, source)
                class_id = f"class:{file_id}:{type_name}"

                # Extract methods from impl body
                body = node.child_by_field_name("body")
                if body:
                    self._extract_impl_methods(body, file_id, class_id, source, result)

    def _extract_impl_methods(
        self, body: Node, file_id: str, class_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract methods from an impl block."""
        for node in body.children:
            if node.type == "function_item":
                name_node = node.child_by_field_name("name")
                if not name_node:
                    continue

                name = self._get_text(name_node, source)
                func_id = f"func:{file_id}:{class_id}:{name}"

                # Extract parameters
                params_node = node.child_by_field_name("parameters")
                params = []
                if params_node:
                    for child in params_node.children:
                        if child.type == "parameter":
                            pattern = child.child_by_field_name("pattern")
                            if pattern:
                                params.append(self._get_text(pattern, source))
                        elif child.type in ("self_parameter", "self"):
                            params.append("self")

                # Extract return type
                return_type_node = node.child_by_field_name("return_type")
                return_type = self._get_text(return_type_node, source) if return_type_node else None

                # Check if async
                is_async = any(c.type == "async" for c in node.children)

                params_text = self._get_text(params_node, source) if params_node else "()"
                signature = f"{'async ' if is_async else ''}fn {name}{params_text}"
                if return_type:
                    signature += f" -> {return_type}"

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
                        is_async=is_async,
                        is_method=True,
                        class_id=class_id,
                        parameters=params,
                        return_type=return_type,
                    )
                )

                result.edges.append(
                    Edge(source_id=class_id, target_id=func_id, type=EdgeType.CONTAINS)
                )

    def _extract_functions(
        self,
        root: Node,
        file_id: str,
        class_id: str | None,
        source: str,
        result: ParseResult,
    ) -> None:
        """Extract top-level function declarations."""
        for node in root.children:
            if node.type != "function_item":
                continue

            name_node = node.child_by_field_name("name")
            if not name_node:
                continue

            name = self._get_text(name_node, source)
            func_id = f"func:{file_id}:module:{name}"

            # Extract parameters
            params_node = node.child_by_field_name("parameters")
            params = []
            if params_node:
                for child in params_node.children:
                    if child.type == "parameter":
                        pattern = child.child_by_field_name("pattern")
                        if pattern:
                            params.append(self._get_text(pattern, source))

            # Extract return type
            return_type_node = node.child_by_field_name("return_type")
            return_type = self._get_text(return_type_node, source) if return_type_node else None

            # Check if async
            is_async = any(c.type == "async" for c in node.children)

            params_text = self._get_text(params_node, source) if params_node else "()"
            signature = f"{'async ' if is_async else ''}fn {name}{params_text}"
            if return_type:
                signature += f" -> {return_type}"

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
                    is_async=is_async,
                    is_method=False,
                    parameters=params,
                    return_type=return_type,
                )
            )

            result.edges.append(
                Edge(source_id=file_id, target_id=func_id, type=EdgeType.DEFINES)
            )

    def _extract_constants(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract const and static declarations."""
        for node in root.children:
            if node.type in ("const_item", "static_item"):
                name_node = node.child_by_field_name("name")
                if not name_node:
                    continue

                name = self._get_text(name_node, source)
                var_id = f"var:{file_id}:module:{name}"

                type_node = node.child_by_field_name("type")
                type_hint = self._get_text(type_node, source) if type_node else None

                result.variables.append(
                    VariableNode(
                        id=var_id,
                        name=name,
                        file_id=file_id,
                        type_hint=type_hint,
                        line=node.start_point[0] + 1,
                        scope="module",
                    )
                )

    def _walk_tree(self, node: Node):
        """Walk all nodes in a tree."""
        yield node
        for child in node.children:
            yield from self._walk_tree(child)
