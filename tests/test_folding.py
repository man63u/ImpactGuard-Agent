import textwrap
from pathlib import Path
from slicer.extractor import extract_function_inventory
from slicer.folding import overlaps, apply_diff_folding
from slicer.diff_utils import lines_to_byte_ranges

FIXTURES = Path(__file__).parent / "fixtures"


def test_fold_preserves_signature_and_docstring_only(tmp_path):
    src = textwrap.dedent("""\
        def greet(name: str, greeting: str = "Hello") -> str:
            \"\"\"Return a greeting string.\"\"\"
            result = f"{greeting}, {name}!"
            return result
    """)
    f = tmp_path / "sample.py"
    f.write_text(src, encoding="utf-8")

    inv = extract_function_inventory(f)

    folded = apply_diff_folding({str(f): inv}, {str(f): []})
    stub = folded[str(f)]["greet"]

    assert 'def greet(name: str, greeting: str = "Hello") -> str:' in stub
    assert '"""Return a greeting string."""' in stub
    assert "result = f" not in stub
    assert "return result" not in stub
    assert "..." in stub


def test_changed_function_kept_full(tmp_path):
    src = textwrap.dedent("""\
        def foo():
            \"\"\"Docstring.\"\"\"
            x = 1
            return x


        def bar():
            return 2
    """)
    f = tmp_path / "sample.py"
    f.write_text(src, encoding="utf-8")

    inv = extract_function_inventory(f)
    file_bytes = f.read_bytes()

    changed_ranges = lines_to_byte_ranges(file_bytes, {4})
    folded = apply_diff_folding({str(f): inv}, {str(f): changed_ranges})

    assert "x = 1" in folded[str(f)]["foo"], "改动函数必须展示完整函数体"
    assert "x = 1" not in folded[str(f)]["bar"], "未改动函数必须折叠为 stub"
    assert "..." in folded[str(f)]["bar"]


def test_module_level_change_outside_any_function_kept_full():
    f = FIXTURES / "sample_module_level_change.py"
    inv = extract_function_inventory(f)
    file_bytes = f.read_bytes()

    lines = file_bytes.decode("utf-8").splitlines(keepends=True)
    target_line = next(
        i + 1 for i, l in enumerate(lines) if "CONSTANT_ONE = 42" in l
    )

    changed_ranges = lines_to_byte_ranges(file_bytes, {target_line})
    folded = apply_diff_folding({str(f): inv}, {str(f): changed_ranges})

    file_ctx = folded[str(f)]
    assert "$module" in file_ctx, "模块级改动必须出现在 '$module' key 下"
    assert "CONSTANT_ONE = 42" in file_ctx["$module"]


def test_byte_offset_correct_with_non_ascii_content():
    f = FIXTURES / "sample_with_unicode.py"
    inv = extract_function_inventory(f)
    file_bytes = f.read_bytes()

    lines = file_bytes.decode("utf-8").splitlines(keepends=True)
    target_line = next(
        i + 1 for i, l in enumerate(lines) if "return str(x * 2)" in l
    )

    changed_ranges = lines_to_byte_ranges(file_bytes, {target_line})
    folded = apply_diff_folding({str(f): inv}, {str(f): changed_ranges})

    file_ctx = folded[str(f)]
    assert "return str(x * 2)" in file_ctx["target_function"], (
        "即使改动行之前有中文字符，字节偏移也必须能正确命中 target_function"
    )
    assert "..." in file_ctx["unchanged_function"], (
        "未改动的 unchanged_function 仍应折叠为 stub"
    )
