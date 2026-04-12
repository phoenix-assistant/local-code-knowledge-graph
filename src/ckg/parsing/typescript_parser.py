"""TypeScript/JavaScript parser using Tree-sitter."""

import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
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


class TypeScriptParser(BaseParser):
    """Parser for TypeScript source code."""

    language = "typescript"

    def __init__(self):
        """Initialize TypeScript parser."""
        self._ts_parser = Parser(Language(tstypescript.language_typescript()))
        self._tsx_parser = Parser(Language(tstypescript.language_tsx()))

    def get_extensions(self) -> list[str]:
        """Get TypeScript file extensions."""
        return [".ts", ".tsx", ".mts", ".cts"]

    def parse(self, source: str, file_id: str, file_path: str) -> ParseResult:
        """Parse TypeScript source code."""
        result = ParseResult()

        # Use TSX parser for .tsx files
        parser = self._tsx_parser if file_path.endswith(".tsx") else self._ts_parser
        tree = parser.parse(source.encode())

        self._extract_imports(tree.root_node, file_id, source, result)
        self._extract_classes(tree.root_node, file_id, source, result)
        self._extract_functions(tree.root_node, file_id, None, source, result)
        self._extract_variables(tree.root_node, file_id, source, result)

        return result

    def _get_text(self, node: Node, source: str) -> str:
        """Extract text from a node."""
        return source[node.start_byte:node.end_byte]

    def _extract_imports(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract import statements."""
        for node in self._walk_tree(root):
            if node.type == "import_statement":
                source_node = node.child_by_field_name("source")
                if not source_node:
                    continue

                module = self._get_text(source_node, source).strip("'\"")
                items = []

                # Extract imported names
                for child in node.children:
                    if child.type == "import_clause":
                        for grandchild in self._walk_tree(child):
                            if grandchild.type == "identifier":
                                items.append(self._get_text(grandchild, source))
                            elif grandchild.type == "import_specifier":
                                name_node = grandchild.child_by_field_name("name")
                                if name_node:
                                    items.append(self._get_text(name_node, source))

                import_id = f"import:{file_id}:{module}"
                result.imports.append(
                    ImportNode(
                        id=import_id,
                        name=module,
                        file_id=file_id,
                        module=module,
                        items=items,
                        line=node.start_point[0] + 1,
                    )
                )
                result.edges.append(
                    Edge(source_id=file_id, target_id=import_id, type=EdgeType.IMPORTS)
                )

    def _extract_classes(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract class definitions."""
        for node in root.children:
            if node.type != "class_declaration":
                continue

            name_node = node.child_by_field_name("name")
            if not name_node:
                continue

            name = self._get_text(name_node, source)
            class_id = f"class:{file_id}:{name}"

            # Extract base classes
            bases = []
            # Try both field name and direct child search
            heritage = node.child_by_field_name("heritage")
            if not heritage:
                # Look for class_heritage child
                for child in node.children:
                    if child.type == "class_heritage":
                        heritage = child
                        break
            if heritage:
                for child in self._walk_tree(heritage):
                    if child.type == "identifier":
                        bases.append(self._get_text(child, source))

            # Extract decorators
            decorators = []
            for child in node.children:
                if child.type == "decorator":
                    dec_text = self._get_text(child, source)
                    decorators.append(dec_text.lstrip("@").split("(")[0])

            result.classes.append(
                ClassNode(
                    id=class_id,
                    name=name,
                    file_id=file_id,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    bases=bases,
                    decorators=decorators,
                )
            )

            result.edges.append(
                Edge(source_id=file_id, target_id=class_id, type=EdgeType.DEFINES)
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

            # Extract methods
            body = node.child_by_field_name("body")
            if not body:
                # Look for class_body child
                for child in node.children:
                    if child.type == "class_body":
                        body = child
                        break
            if body:
                self._extract_methods(body, file_id, class_id, source, result)

    def _extract_methods(
        self, body: Node, file_id: str, class_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract class methods."""
        for node in body.children:
            if node.type != "method_definition":
                continue

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
                    if child.type in ("identifier", "required_parameter", "optional_parameter"):
                        param_name = child.child_by_field_name("pattern") or child
                        if param_name.type == "identifier":
                            params.append(self._get_text(param_name, source))

            # Extract return type
            return_type_node = node.child_by_field_name("return_type")
            return_type = self._get_text(return_type_node, source) if return_type_node else None

            # Check if async
            is_async = any(c.type == "async" for c in node.children)

            params_text = self._get_text(params_node, source) if params_node else "()"
            signature = f"{'async ' if is_async else ''}{name}{params_text}"
            if return_type:
                signature += f": {return_type}"

            result.functions.append(
                FunctionNode(
                    id=func_id,
                    name=name,
                    file_id=file_id,
                    signature=signature,
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
        """Extract function definitions."""
        for node in root.children:
            if node.type not in ("function_declaration", "export_statement"):
                continue

            func_node = node
            if node.type == "export_statement":
                # Find the function inside export
                for child in node.children:
                    if child.type == "function_declaration":
                        func_node = child
                        break
                else:
                    continue

            name_node = func_node.child_by_field_name("name")
            if not name_node:
                continue

            name = self._get_text(name_node, source)
            func_id = f"func:{file_id}:module:{name}"

            # Extract parameters
            params_node = func_node.child_by_field_name("parameters")
            params = []
            if params_node:
                for child in params_node.children:
                    if child.type in ("identifier", "required_parameter", "optional_parameter"):
                        param_name = child.child_by_field_name("pattern") or child
                        if param_name.type == "identifier":
                            params.append(self._get_text(param_name, source))

            # Extract return type
            return_type_node = func_node.child_by_field_name("return_type")
            return_type = self._get_text(return_type_node, source) if return_type_node else None

            # Check if async
            is_async = any(c.type == "async" for c in func_node.children)

            params_text = self._get_text(params_node, source) if params_node else "()"
            signature = f"{'async ' if is_async else ''}function {name}{params_text}"
            if return_type:
                signature += f": {return_type}"

            result.functions.append(
                FunctionNode(
                    id=func_id,
                    name=name,
                    file_id=file_id,
                    signature=signature,
                    start_line=func_node.start_point[0] + 1,
                    end_line=func_node.end_point[0] + 1,
                    is_async=is_async,
                    is_method=False,
                    parameters=params,
                    return_type=return_type,
                )
            )

            result.edges.append(
                Edge(source_id=file_id, target_id=func_id, type=EdgeType.DEFINES)
            )

    def _extract_variables(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract module-level variables."""
        for node in root.children:
            if node.type not in ("lexical_declaration", "variable_declaration", "export_statement"):
                continue

            var_node = node
            if node.type == "export_statement":
                for child in node.children:
                    if child.type in ("lexical_declaration", "variable_declaration"):
                        var_node = child
                        break
                else:
                    continue

            for child in var_node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    if name_node and name_node.type == "identifier":
                        name = self._get_text(name_node, source)
                        var_id = f"var:{file_id}:module:{name}"

                        # Get type annotation
                        type_hint = None
                        type_node = child.child_by_field_name("type")
                        if type_node:
                            type_hint = self._get_text(type_node, source)

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


class JavaScriptParser(TypeScriptParser):
    """Parser for JavaScript source code."""

    language = "javascript"

    def __init__(self):
        """Initialize JavaScript parser."""
        self._ts_parser = Parser(Language(tsjavascript.language()))
        self._tsx_parser = Parser(Language(tsjavascript.language()))

    def get_extensions(self) -> list[str]:
        """Get JavaScript file extensions."""
        return [".js", ".jsx", ".mjs", ".cjs"]
