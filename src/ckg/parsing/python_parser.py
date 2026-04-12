"""Python parser using Tree-sitter."""

import tree_sitter_python as tspython
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


class PythonParser(BaseParser):
    """Parser for Python source code."""

    language = "python"

    def __init__(self):
        """Initialize Python parser."""
        self._parser = Parser(Language(tspython.language()))

    def get_extensions(self) -> list[str]:
        """Get Python file extensions."""
        return [".py", ".pyw", ".pyi"]

    def parse(self, source: str, file_id: str, file_path: str) -> ParseResult:
        """Parse Python source code."""
        result = ParseResult()
        tree = self._parser.parse(source.encode())

        self._extract_imports(tree.root_node, file_id, source, result)
        self._extract_classes(tree.root_node, file_id, source, result)
        self._extract_functions(tree.root_node, file_id, None, source, result)
        self._extract_variables(tree.root_node, file_id, None, source, result)

        return result

    def _get_text(self, node: Node, source: str) -> str:
        """Extract text from a node."""
        return source[node.start_byte:node.end_byte]

    def _extract_docstring(self, body_node: Node, source: str) -> str | None:
        """Extract docstring from function/class body."""
        if body_node.child_count == 0:
            return None

        first_child = body_node.child(0)
        if first_child and first_child.type == "expression_statement":
            string_node = first_child.child(0)
            if string_node and string_node.type == "string":
                text = self._get_text(string_node, source)
                # Remove quotes
                if text.startswith('"""') or text.startswith("'''"):
                    return text[3:-3].strip()
                elif text.startswith('"') or text.startswith("'"):
                    return text[1:-1].strip()
        return None

    def _extract_imports(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract import statements."""
        for node in root.children:
            if node.type == "import_statement":
                # import X, Y, Z
                for child in node.children:
                    if child.type == "dotted_name":
                        module = self._get_text(child, source)
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
                    elif child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        alias_node = child.child_by_field_name("alias")
                        if name_node:
                            module = self._get_text(name_node, source)
                            alias = (
                                self._get_text(alias_node, source)
                                if alias_node
                                else None
                            )
                            import_id = f"import:{file_id}:{module}"
                            result.imports.append(
                                ImportNode(
                                    id=import_id,
                                    name=alias or module,
                                    file_id=file_id,
                                    module=module,
                                    alias=alias,
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

            elif node.type == "import_from_statement":
                # from X import Y, Z
                module_node = node.child_by_field_name("module_name")
                module = self._get_text(module_node, source) if module_node else ""

                items = []
                for child in node.children:
                    if child.type == "dotted_name" and child != module_node:
                        items.append(self._get_text(child, source))
                    elif child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            items.append(self._get_text(name_node, source))

                if items:
                    import_id = f"import:{file_id}:{module}:{','.join(items)}"
                    result.imports.append(
                        ImportNode(
                            id=import_id,
                            name=f"from {module}",
                            file_id=file_id,
                            module=module,
                            items=items,
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

    def _extract_classes(
        self, root: Node, file_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract class definitions."""
        for node in root.children:
            if node.type != "class_definition":
                continue

            name_node = node.child_by_field_name("name")
            if not name_node:
                continue

            name = self._get_text(name_node, source)
            class_id = f"class:{file_id}:{name}"

            # Extract base classes
            bases = []
            superclass_node = node.child_by_field_name("superclasses")
            if superclass_node:
                for child in superclass_node.children:
                    if child.type in ("identifier", "attribute"):
                        bases.append(self._get_text(child, source))

            # Extract decorators
            decorators = []
            for child in node.children:
                if child.type == "decorator":
                    dec_text = self._get_text(child, source)
                    decorators.append(dec_text.lstrip("@").split("(")[0])

            # Extract docstring
            body_node = node.child_by_field_name("body")
            docstring = self._extract_docstring(body_node, source) if body_node else None

            result.classes.append(
                ClassNode(
                    id=class_id,
                    name=name,
                    file_id=file_id,
                    docstring=docstring,
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
                # Note: base class ID is a placeholder; resolution happens later
                result.edges.append(
                    Edge(
                        source_id=class_id,
                        target_id=f"class:*:{base}",
                        type=EdgeType.INHERITS,
                        metadata={"unresolved": True},
                    )
                )

            # Extract methods from class body
            if body_node:
                self._extract_functions(body_node, file_id, class_id, source, result)
                self._extract_variables(body_node, file_id, class_id, source, result)

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
            if node.type not in ("function_definition", "async_function_definition"):
                continue

            name_node = node.child_by_field_name("name")
            if not name_node:
                continue

            name = self._get_text(name_node, source)
            # Check for async - either separate type or async keyword child
            is_async = node.type == "async_function_definition" or any(
                c.type == "async" for c in node.children
            )
            is_method = class_id is not None

            func_id = f"func:{file_id}:{class_id or 'module'}:{name}"

            # Extract parameters
            params_node = node.child_by_field_name("parameters")
            params = []
            if params_node:
                for child in params_node.children:
                    if child.type == "identifier":
                        params.append(self._get_text(child, source))
                    elif child.type in (
                        "typed_parameter",
                        "default_parameter",
                        "typed_default_parameter",
                    ):
                        # For typed_parameter, get the first identifier child
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                params.append(self._get_text(subchild, source))
                                break

            # Extract return type
            return_type_node = node.child_by_field_name("return_type")
            return_type = (
                self._get_text(return_type_node, source) if return_type_node else None
            )

            # Build signature
            params_text = self._get_text(params_node, source) if params_node else "()"
            signature = f"{'async ' if is_async else ''}def {name}{params_text}"
            if return_type:
                signature += f" -> {return_type}"

            # Extract docstring
            body_node = node.child_by_field_name("body")
            docstring = self._extract_docstring(body_node, source) if body_node else None

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

            # Extract function calls (basic)
            if body_node:
                self._extract_calls(body_node, func_id, source, result)

    def _extract_calls(
        self, body_node: Node, func_id: str, source: str, result: ParseResult
    ) -> None:
        """Extract function calls from a function body."""
        for node in self._walk_tree(body_node):
            if node.type == "call":
                func_node = node.child_by_field_name("function")
                if func_node:
                    call_name = self._get_text(func_node, source)
                    # Remove attribute access for now
                    if "." in call_name:
                        call_name = call_name.split(".")[-1]
                    result.edges.append(
                        Edge(
                            source_id=func_id,
                            target_id=f"func:*:*:{call_name}",
                            type=EdgeType.CALLS,
                            metadata={"unresolved": True},
                        )
                    )

    def _extract_variables(
        self,
        root: Node,
        file_id: str,
        class_id: str | None,
        source: str,
        result: ParseResult,
    ) -> None:
        """Extract module/class-level variables."""
        for node in root.children:
            if node.type not in ("assignment", "annotated_assignment"):
                continue

            # Skip if inside a function (we only want module/class level)
            left = node.child_by_field_name("left")
            if not left:
                continue

            if left.type == "identifier":
                name = self._get_text(left, source)
                var_id = f"var:{file_id}:{class_id or 'module'}:{name}"

                # Get type hint if available
                type_hint = None
                if node.type == "annotated_assignment":
                    type_node = node.child_by_field_name("type")
                    if type_node:
                        type_hint = self._get_text(type_node, source)

                scope = "class" if class_id else "module"
                result.variables.append(
                    VariableNode(
                        id=var_id,
                        name=name,
                        file_id=file_id,
                        type_hint=type_hint,
                        line=node.start_point[0] + 1,
                        scope=scope,
                        class_id=class_id,
                    )
                )

    def _walk_tree(self, node: Node):
        """Walk all nodes in a tree."""
        yield node
        for child in node.children:
            yield from self._walk_tree(child)
