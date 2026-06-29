import textwrap
from pathlib import Path
import pytest
from slicer.extractor import (
    walk_function_nodes,
    build_signature_stub,
    extract_function_inventory,
)
from tree_sitter import Language, Parser
import tree_sitter_python as tspython

_PY_LANGUAGE = Language(tspython.language(), 'python')
_parser = Parser()
_parser.set_language(_PY_LANGUAGE)

FIXTURES = Path(__file__).parent / "fixtures"


def _parse(src: str):
    return _parser.parse(src.encode("utf-8")).root_node


def test_walk_finds_module_level_function():
    root = _parse("def foo(): pass")
    names = [name for name, _ in walk_function_nodes(root)]
    assert "foo" in names


def test_walk_finds_class_method():
    root = _parse("class MyClass:\n    def bar(self): pass")
    names = [name for name, _ in walk_function_nodes(root)]
    assert "MyClass.bar" in names


def test_walk_finds_decorated_function():
    root = _parse("@staticmethod\ndef baz(): pass")
    names = [name for name, _ in walk_function_nodes(root)]
    assert "baz" in names


def test_walk_does_not_yield_deeply_nested_inner_function():
    src = "def outer():\n    def inner(): pass\n    return inner"
    root = _parse(src)
    names = [name for name, _ in walk_function_nodes(root)]
    assert "outer" in names
    assert "inner" not in names


def test_stub_preserves_signature_and_docstring():
    src = textwrap.dedent("""\
        def compute(x: int, y: str = "hi") -> bool:
            \"\"\"Does the computation.\"\"\"
            result = x > 0
            return result
    """)
    root = _parse(src)
    _, node = next(walk_function_nodes(root))
    stub = build_signature_stub(node)
    assert 'def compute(x: int, y: str = "hi") -> bool:' in stub
    assert '"""Does the computation."""' in stub
    assert "result = x > 0" not in stub
    assert "return result" not in stub
    assert "..." in stub


def test_stub_without_docstring_uses_ellipsis():
    src = "def simple(a, b):\n    return a + b\n"
    root = _parse(src)
    _, node = next(walk_function_nodes(root))
    stub = build_signature_stub(node)
    assert "def simple(a, b):" in stub
    assert "return" not in stub
    assert "..." in stub


def test_property_pair_gets_unique_keys_and_labels(tmp_path):
    src = textwrap.dedent("""\
        class Foo:
            @property
            def value(self):
                return self._value

            @value.setter
            def value(self, v):
                self._value = v
    """)
    f = tmp_path / "sample.py"
    f.write_text(src, encoding="utf-8")
    inv = extract_function_inventory(f)

    assert "Foo.value#0" in inv["functions"]
    assert "Foo.value#1" in inv["functions"]
    assert inv["functions"]["Foo.value#0"]["display_label"] == "property getter"
    assert inv["functions"]["Foo.value#1"]["display_label"] == "property setter"
    assert inv["functions"]["Foo.value#0"]["full_body"].startswith("@property"), (
        "full_body 必须是原文，不能被注入合成注释"
    )


def test_non_property_collision_gets_neutral_label(tmp_path):
    src = textwrap.dedent("""\
        @area.register
        def _(shape): return shape.circle_area()
        @area.register
        def _(shape): return shape.square_area()
    """)
    f = tmp_path / "sample.py"
    f.write_text(src, encoding="utf-8")
    inv = extract_function_inventory(f)

    assert "_#0" in inv["functions"]
    assert "_#1" in inv["functions"]
    assert inv["functions"]["_#0"]["display_label"] == "_#0"
    assert inv["functions"]["_#1"]["display_label"] == "_#1"
    assert "property" not in inv["functions"]["_#0"]["display_label"]


def test_single_occurrence_keeps_bare_name(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("def solo(): pass\n", encoding="utf-8")
    inv = extract_function_inventory(f)

    assert "solo" in inv["functions"]
    assert "solo#0" not in inv["functions"]


def test_async_function_is_extracted_correctly():
    f = FIXTURES / "real_starlette_async.py"
    inv = extract_function_inventory(f)

    assert "run_in_threadpool" in inv["functions"], (
        "walk_function_nodes 未能识别出 async def 函数"
    )

    full_body = inv["functions"]["run_in_threadpool"]["full_body"]
    stub = inv["functions"]["run_in_threadpool"]["stub"]

    assert "async def run_in_threadpool" in full_body
    assert "async def run_in_threadpool" in stub, (
        "stub 必须保留 async 关键字"
    )


def test_decorator_with_arguments_preserved_in_full_and_stub():
    f = FIXTURES / "real_flask_cli.py"
    inv = extract_function_inventory(f)

    assert "shell_command" in inv["functions"]

    full_body = inv["functions"]["shell_command"]["full_body"]
    stub = inv["functions"]["shell_command"]["stub"]

    assert '@click.command("shell", short_help="Run a shell in the app context.")' in full_body
    assert '@click.command("shell", short_help="Run a shell in the app context.")' in stub
    assert "code.interact" not in stub


def test_multiline_docstring_preserved_in_full():
    f = FIXTURES / "real_absl_parser.py"
    inv = extract_function_inventory(f)

    assert "ArgumentParser.parse" in inv["functions"]

    full_body = inv["functions"]["ArgumentParser.parse"]["full_body"]

    assert "Args:" in full_body
    assert "Raises:" in full_body
    assert "Returns:" in full_body
    assert "argument: string argument passed in the commandline." in full_body
    assert "ValueError: Raised when it fails to parse the argument." in full_body
    assert "The parsed value in native type." in full_body
