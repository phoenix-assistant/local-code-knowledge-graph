"""Tests for code parsing."""

import pytest

from ckg.parsing.python_parser import PythonParser
from ckg.parsing.typescript_parser import TypeScriptParser, JavaScriptParser
from ckg.parsing.go_parser import GoParser
from ckg.parsing.rust_parser import RustParser


class TestPythonParser:
    """Tests for Python parser."""

    @pytest.fixture
    def parser(self):
        return PythonParser()

    def test_parse_function(self, parser):
        source = '''
def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"
'''
        result = parser.parse(source, "file:test.py", "test.py")

        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "hello"
        assert "name" in func.parameters
        assert func.return_type == "str"
        assert func.docstring == "Say hello."

    def test_parse_class(self, parser):
        source = '''
class MyClass(BaseClass):
    """A test class."""

    def method(self):
        pass
'''
        result = parser.parse(source, "file:test.py", "test.py")

        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "MyClass"
        assert "BaseClass" in cls.bases
        assert cls.docstring == "A test class."

        # Method should also be extracted
        assert len(result.functions) == 1
        method = result.functions[0]
        assert method.name == "method"
        assert method.is_method

    def test_parse_imports(self, parser):
        source = '''
import os
from pathlib import Path, PurePath
import json as j
'''
        result = parser.parse(source, "file:test.py", "test.py")

        assert len(result.imports) == 3

        # Check import os
        os_import = next(i for i in result.imports if i.module == "os")
        assert os_import.name == "os"

        # Check from import
        path_import = next(i for i in result.imports if "pathlib" in i.module)
        assert "Path" in path_import.items

        # Check aliased import
        json_import = next(i for i in result.imports if i.module == "json")
        assert json_import.alias == "j"

    def test_parse_async_function(self, parser):
        source = '''
async def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    pass
'''
        result = parser.parse(source, "file:test.py", "test.py")

        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "fetch_data"
        assert func.is_async


class TestTypeScriptParser:
    """Tests for TypeScript parser."""

    @pytest.fixture
    def parser(self):
        return TypeScriptParser()

    def test_parse_function(self, parser):
        source = '''
function greet(name: string): string {
    return `Hello, ${name}!`;
}
'''
        result = parser.parse(source, "file:test.ts", "test.ts")

        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "greet"

    def test_parse_class(self, parser):
        source = '''
class User extends BaseUser {
    name: string;

    constructor(name: string) {
        this.name = name;
    }

    greet(): string {
        return `Hello, ${this.name}!`;
    }
}
'''
        result = parser.parse(source, "file:test.ts", "test.ts")

        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "User"
        assert "BaseUser" in cls.bases

        # Methods
        assert len(result.functions) == 2  # constructor + greet

    def test_parse_imports(self, parser):
        source = '''
import { Component } from '@angular/core';
import * as fs from 'fs';
'''
        result = parser.parse(source, "file:test.ts", "test.ts")

        assert len(result.imports) == 2


class TestGoParser:
    """Tests for Go parser."""

    @pytest.fixture
    def parser(self):
        return GoParser()

    def test_parse_function(self, parser):
        source = '''
package main

func Hello(name string) string {
    return "Hello, " + name
}
'''
        result = parser.parse(source, "file:main.go", "main.go")

        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "Hello"

    def test_parse_struct(self, parser):
        source = '''
package main

type User struct {
    Name string
    Age  int
}
'''
        result = parser.parse(source, "file:main.go", "main.go")

        assert len(result.classes) == 1
        struct = result.classes[0]
        assert struct.name == "User"

    def test_parse_method(self, parser):
        source = '''
package main

type User struct {
    Name string
}

func (u *User) Greet() string {
    return "Hello, " + u.Name
}
'''
        result = parser.parse(source, "file:main.go", "main.go")

        methods = [f for f in result.functions if f.is_method]
        assert len(methods) == 1
        assert methods[0].name == "Greet"


class TestRustParser:
    """Tests for Rust parser."""

    @pytest.fixture
    def parser(self):
        return RustParser()

    def test_parse_function(self, parser):
        source = '''
fn hello(name: &str) -> String {
    format!("Hello, {}!", name)
}
'''
        result = parser.parse(source, "file:lib.rs", "lib.rs")

        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "hello"

    def test_parse_struct(self, parser):
        source = '''
struct User {
    name: String,
    age: u32,
}
'''
        result = parser.parse(source, "file:lib.rs", "lib.rs")

        assert len(result.classes) == 1
        struct = result.classes[0]
        assert struct.name == "User"

    def test_parse_impl(self, parser):
        source = '''
struct User {
    name: String,
}

impl User {
    fn new(name: String) -> Self {
        User { name }
    }

    fn greet(&self) -> String {
        format!("Hello, {}!", self.name)
    }
}
'''
        result = parser.parse(source, "file:lib.rs", "lib.rs")

        methods = [f for f in result.functions if f.is_method]
        assert len(methods) == 2
        method_names = {m.name for m in methods}
        assert "new" in method_names
        assert "greet" in method_names
