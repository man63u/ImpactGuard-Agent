# Module 1 — Tree-sitter Structured Extraction & Diff-Based Folding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-phase pipeline that parses Python files with Tree-sitter (Phase A, cacheable) and folds unchanged functions to stubs while preserving full bodies for changed functions (Phase B, pure in-memory), producing a structured dict consumable by downstream modules.

**Architecture:** Phase A (`extractor.py`) runs Tree-sitter once per unique file content, caches the function inventory to disk keyed by SHA-256(content + version), and is parallelised with `ProcessPoolExecutor`. Phase B (`folding.py`) takes the cached inventory plus the PR's changed byte ranges (computed by `diff_utils.py`) and performs the full/stub decision entirely in memory without re-running Tree-sitter. Module-level code (imports, constants) that falls outside any function node is treated as a named region and preserved when changed.

**Tech Stack:** Python 3.10+, tree-sitter 0.22+, tree-sitter-python 0.22+, pytest 7+

## Global Constraints

- Python ≥ 3.10 (uses `str | None` union syntax)
- tree-sitter ≥ 0.22, < 1.0 (uses `Parser(language)` constructor; do NOT use `tree.edit()`)
- tree-sitter-python ≥ 0.22, < 1.0
- No Redis, no external database, no asyncio — cache is local filesystem only
- Only Python grammar implemented; leave extension points, don't add other grammars
- Folded stubs MUST include: signature (params, annotations, defaults) + docstring. Never fold to bare name only.
- `SLICER_VERSION = "v1"` — bump manually when extraction/folding logic changes
- Cache dir: `.impactguard_cache/` at project root
- `ProcessPoolExecutor(max_workers=os.cpu_count())` — no hardcoded numbers
- Module-level changed code (not inside any function) goes to `"$module"` key in per-file context; never silently dropped
- UTF-8 byte offsets computed by scanning raw bytes for `0x0A`; no `len(line_str)` shortcut

---

## File Map

| File | Responsibility |
|------|---------------|
| `requirements.txt` | Runtime deps: tree-sitter, tree-sitter-python |
| `requirements-dev.txt` | Test deps: pytest, pytest-cov |
| `pyproject.toml` | Project metadata & pytest config |
| `slicer/__init__.py` | Public API re-exports |
| `slicer/extractor.py` | `walk_function_nodes`, `build_signature_stub`, `extract_function_inventory` |
| `slicer/diff_utils.py` | `lines_to_byte_ranges` — UTF-8-correct line→byte conversion |
| `slicer/cache.py` | `cache_key`, `load_or_parse`, `CACHE_DIR`, `SLICER_VERSION` |
| `slicer/folding.py` | `overlaps`, `apply_diff_folding` |
| `slicer/pipeline.py` | `build_inventory_for_files` — parallel orchestration |
| `tests/fixtures/sample_with_unicode.py` | File with Chinese comments before a target function |
| `tests/fixtures/sample_module_level_change.py` | File with module-level constants and imports |
| `tests/conftest.py` | Shared fixtures (`tmp_cache_dir`) |
| `tests/test_cache.py` | Cache correctness tests (3 acceptance criteria) |
| `tests/test_folding.py` | Folding & extraction tests (4 acceptance criteria) |
| `tests/test_pipeline.py` | Parallel vs sequential consistency test (1 acceptance criterion) |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `pyproject.toml`
- Create: `slicer/__init__.py`
- Create: `slicer/extractor.py` (empty stub)
- Create: `slicer/diff_utils.py` (empty stub)
- Create: `slicer/cache.py` (empty stub)
- Create: `slicer/folding.py` (empty stub)
- Create: `slicer/pipeline.py` (empty stub)
- Create: `tests/__init__.py`
- Create: `tests/fixtures/__init__.py`

**Interfaces:**
- Produces: installable package skeleton that `pytest` can discover

- [ ] **Step 1: Create `requirements.txt`**

```
tree-sitter>=0.22,<1.0
tree-sitter-python>=0.22,<1.0
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest>=7.0
pytest-cov
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "impactguard-slicer"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "tree-sitter>=0.22,<1.0",
    "tree-sitter-python>=0.22,<1.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Create `slicer/__init__.py`**

```python
from .pipeline import build_inventory_for_files
from .folding import apply_diff_folding
from .diff_utils import lines_to_byte_ranges

__all__ = ["build_inventory_for_files", "apply_diff_folding", "lines_to_byte_ranges"]
```

- [ ] **Step 5: Create empty module stubs**

`slicer/extractor.py`:
```python
# placeholder
```

`slicer/diff_utils.py`:
```python
# placeholder
```

`slicer/cache.py`:
```python
# placeholder
```

`slicer/folding.py`:
```python
# placeholder
```

`slicer/pipeline.py`:
```python
# placeholder
```

`tests/__init__.py` and `tests/fixtures/__init__.py`: empty files.

- [ ] **Step 6: Install dependencies**

```
pip install -r requirements-dev.txt
```

Expected: no errors.

- [ ] **Step 7: Verify pytest can discover the package**

```
pytest --collect-only
```

Expected: "no tests ran" (0 items collected) with no import errors.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt requirements-dev.txt pyproject.toml slicer/ tests/
git commit -m "feat: scaffold slicer package structure"
```

---

## Task 2: `slicer/extractor.py` — Tree-sitter AST Parsing

**Files:**
- Modify: `slicer/extractor.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - `walk_function_nodes(node: Node, parent_class: str | None = None) -> Iterator[tuple[str, Node]]`
  - `build_signature_stub(node: Node) -> str`
  - `extract_function_inventory(file_path: Path) -> dict` — returns `{"functions": {name: {"byte_range": [start, end], "full_body": str, "stub": str}}, "module_regions": [{"byte_range": [start, end], "text": str}]}`

- [ ] **Step 1: Write failing tests for `walk_function_nodes`**

Create `tests/test_extractor.py`:

```python
import textwrap
from pathlib import Path
import pytest
from slicer.extractor import walk_function_nodes, build_signature_stub, extract_function_inventory
from tree_sitter import Language, Parser
import tree_sitter_python as tspython

_PY_LANGUAGE = Language(tspython.language())
_parser = Parser(_PY_LANGUAGE)


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
    assert "inner" not in names  # inner is part of outer's body


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
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_extractor.py -v
```

Expected: ImportError or AttributeError (slicer.extractor has no real content).

- [ ] **Step 3: Implement `slicer/extractor.py`**

```python
from __future__ import annotations
from pathlib import Path
from typing import Iterator

from tree_sitter import Language, Node, Parser
import tree_sitter_python as tspython

_PY_LANGUAGE = Language(tspython.language())
_parser = Parser(_PY_LANGUAGE)


def _get_body_indent(block_node: Node) -> str:
    for child in block_node.children:
        if child.type not in ('newline', 'indent', 'dedent', 'comment'):
            return ' ' * child.start_point[1]
    return '    '


def _extract_docstring(block_node: Node) -> str | None:
    for child in block_node.children:
        if child.type == 'expression_statement':
            for gc in child.children:
                if gc.type in ('string', 'concatenated_string'):
                    return gc.text.decode('utf-8')
            return None
        elif child.type in ('newline', 'indent', 'dedent', 'comment'):
            continue
        else:
            return None
    return None


def walk_function_nodes(
    node: Node, parent_class: str | None = None
) -> Iterator[tuple[str, Node]]:
    """Yield (qualified_name, node) for function_definition nodes.

    Only walks one level into classes — deeply nested inner functions are
    intentionally skipped; they are part of the outer function's body text.
    """
    for child in node.children:
        if child.type == 'decorated_definition':
            inner = child.child_by_field_name('definition')
            if inner is None:
                continue
            if inner.type == 'function_definition':
                name = inner.child_by_field_name('name').text.decode('utf-8')
                qual = f"{parent_class}.{name}" if parent_class else name
                yield qual, child  # use decorated_definition so byte_range includes decorators
            elif inner.type == 'class_definition':
                class_name = inner.child_by_field_name('name').text.decode('utf-8')
                body = inner.child_by_field_name('body')
                if body:
                    yield from walk_function_nodes(body, parent_class=class_name)
        elif child.type == 'function_definition':
            name = child.child_by_field_name('name').text.decode('utf-8')
            qual = f"{parent_class}.{name}" if parent_class else name
            yield qual, child
        elif child.type == 'class_definition':
            class_name = child.child_by_field_name('name').text.decode('utf-8')
            body = child.child_by_field_name('body')
            if body:
                yield from walk_function_nodes(body, parent_class=class_name)


def build_signature_stub(node: Node) -> str:
    """Return decorator lines (if any) + def signature + docstring + '...'."""
    func_def = (
        node.child_by_field_name('definition')
        if node.type == 'decorated_definition'
        else node
    )
    block_node = func_def.child_by_field_name('body')
    if block_node is None:
        return node.text.decode('utf-8')

    sig_end = block_node.start_byte - node.start_byte
    signature = node.text[:sig_end].decode('utf-8').rstrip()

    body_indent = _get_body_indent(block_node)
    docstring = _extract_docstring(block_node)

    if docstring:
        return f"{signature}\n{body_indent}{docstring}\n{body_indent}..."
    return f"{signature}\n{body_indent}..."


def extract_function_inventory(file_path: Path) -> dict:
    """Parse file_path with Tree-sitter; return structured function inventory.

    Return structure:
    {
      "functions": {
        "qual_name": {"byte_range": [start, end], "full_body": str, "stub": str}
      },
      "module_regions": [
        {"byte_range": [start, end], "text": str}   # bytes not inside any function
      ]
    }
    """
    source = file_path.read_bytes()
    tree = _parser.parse(source)

    functions: dict[str, dict] = {}
    for qual_name, node in walk_function_nodes(tree.root_node):
        functions[qual_name] = {
            'byte_range': [node.start_byte, node.end_byte],
            'full_body': node.text.decode('utf-8'),
            'stub': build_signature_stub(node),
        }

    # Module regions: file bytes NOT covered by any function node.
    # Merge overlapping ranges first (nested functions could theoretically overlap).
    covered = sorted((m['byte_range'][0], m['byte_range'][1]) for m in functions.values())
    merged: list[tuple[int, int]] = []
    for s, e in covered:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    module_regions: list[dict] = []
    prev_end = 0
    for s, e in merged:
        if prev_end < s:
            text = source[prev_end:s].decode('utf-8')
            if text.strip():
                module_regions.append({'byte_range': [prev_end, s], 'text': text})
        prev_end = e
    if prev_end < len(source):
        text = source[prev_end:].decode('utf-8')
        if text.strip():
            module_regions.append({'byte_range': [prev_end, len(source)], 'text': text})

    return {'functions': functions, 'module_regions': module_regions}
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_extractor.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add slicer/extractor.py tests/test_extractor.py
git commit -m "feat: implement Tree-sitter AST extraction with function walk and stub builder"
```

---

## Task 3: `slicer/diff_utils.py` — UTF-8-Correct Line-to-Byte Conversion

**Files:**
- Modify: `slicer/diff_utils.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - `lines_to_byte_ranges(file_bytes: bytes, changed_line_numbers: set[int]) -> list[tuple[int, int]]`
    - `changed_line_numbers` is 1-indexed
    - Returns list of `(start_byte_inclusive, end_byte_exclusive)` for each matching line

- [ ] **Step 1: Write failing tests**

Create `tests/test_diff_utils.py`:

```python
from slicer.diff_utils import lines_to_byte_ranges


def test_ascii_single_line():
    src = b"hello\nworld\n"
    # Line 1 = "hello\n" bytes [0, 6)
    ranges = lines_to_byte_ranges(src, {1})
    assert ranges == [(0, 6)]


def test_ascii_multiple_lines():
    src = b"a\nbb\nccc\n"
    ranges = lines_to_byte_ranges(src, {1, 3})
    assert (0, 2) in ranges   # "a\n"
    assert (5, 9) in ranges   # "ccc\n"


def test_multibyte_utf8_before_target_line():
    # Line 1: Chinese chars (3 bytes each) + newline
    # Line 2: ASCII target line
    line1 = "中文\n".encode("utf-8")   # 7 bytes: 3+3+1
    line2 = b"def foo(): pass\n"       # 16 bytes
    src = line1 + line2
    ranges = lines_to_byte_ranges(src, {2})
    expected_start = len(line1)        # 7
    expected_end = len(line1) + len(line2)  # 23
    assert ranges == [(expected_start, expected_end)]


def test_no_trailing_newline_last_line():
    src = b"first\nsecond"  # no trailing newline
    ranges = lines_to_byte_ranges(src, {2})
    assert ranges == [(6, 12)]


def test_empty_changed_set_returns_empty():
    src = b"line1\nline2\n"
    assert lines_to_byte_ranges(src, set()) == []


def test_line_number_out_of_range_returns_empty():
    src = b"only one line\n"
    assert lines_to_byte_ranges(src, {99}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_diff_utils.py -v
```

Expected: ImportError or AttributeError.

- [ ] **Step 3: Implement `slicer/diff_utils.py`**

```python
from __future__ import annotations


def lines_to_byte_ranges(
    file_bytes: bytes, changed_line_numbers: set[int]
) -> list[tuple[int, int]]:
    """Convert 1-indexed line numbers to byte ranges.

    Scans raw bytes for 0x0A — correct for UTF-8 because multibyte sequences
    use bytes 0x80–0xFF, so '\n' (0x0A) is unambiguous.
    """
    if not changed_line_numbers:
        return []

    ranges: list[tuple[int, int]] = []
    current_line = 1
    line_start = 0
    n = len(file_bytes)
    i = 0

    while i < n:
        if file_bytes[i] == 0x0A:  # '\n'
            if current_line in changed_line_numbers:
                ranges.append((line_start, i + 1))
            line_start = i + 1
            current_line += 1
        i += 1

    # Last line with no trailing newline
    if line_start < n and current_line in changed_line_numbers:
        ranges.append((line_start, n))

    return ranges
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_diff_utils.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add slicer/diff_utils.py tests/test_diff_utils.py
git commit -m "feat: implement UTF-8-correct line-to-byte-range conversion"
```

---

## Task 4: `slicer/cache.py` — File-Based Caching

**Files:**
- Modify: `slicer/cache.py`

**Interfaces:**
- Consumes: `extract_function_inventory` from `slicer.extractor`
- Produces:
  - `CACHE_DIR: Path` — `.impactguard_cache/`
  - `SLICER_VERSION: str` — `"v1"`
  - `cache_key(file_path: Path) -> str`
  - `load_or_parse(file_path: Path) -> dict`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cache.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import slicer.cache as cache_mod
from slicer.cache import cache_key, load_or_parse, CACHE_DIR, SLICER_VERSION


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect CACHE_DIR to a temp dir for every test."""
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")
    yield tmp_path / ".cache"


def _write_py(tmp_path: Path, name: str, content: str) -> Path:
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


# ── Acceptance criterion 1 ──────────────────────────────────────────────────

def test_unchanged_file_hits_cache(tmp_path):
    """Second call to load_or_parse must NOT re-run extract_function_inventory."""
    f = _write_py(tmp_path, "sample.py", "def foo(): pass\n")

    call_count = 0
    real_extract = __import__("slicer.extractor", fromlist=["extract_function_inventory"]).extract_function_inventory

    def counting_extract(path):
        nonlocal call_count
        call_count += 1
        return real_extract(path)

    with patch("slicer.cache.extract_function_inventory", side_effect=counting_extract):
        load_or_parse(f)
        load_or_parse(f)

    assert call_count == 1, "parse should be called exactly once; second call must hit cache"


# ── Acceptance criterion 2 ──────────────────────────────────────────────────

def test_changed_file_misses_cache_only_for_that_file(tmp_path):
    """When one file changes, only that file is re-parsed; unchanged files stay cached."""
    f1 = _write_py(tmp_path, "a.py", "def alpha(): pass\n")
    f2 = _write_py(tmp_path, "b.py", "def beta(): pass\n")

    parse_calls: list[str] = []
    real_extract = __import__("slicer.extractor", fromlist=["extract_function_inventory"]).extract_function_inventory

    def tracking_extract(path):
        parse_calls.append(path.name)
        return real_extract(path)

    with patch("slicer.cache.extract_function_inventory", side_effect=tracking_extract):
        load_or_parse(f1)
        load_or_parse(f2)
        parse_calls.clear()

        # Modify only f2
        f2.write_text("def beta_v2(): pass\n", encoding="utf-8")
        load_or_parse(f1)
        load_or_parse(f2)

    assert "a.py" not in parse_calls, "unchanged file must hit cache"
    assert "b.py" in parse_calls, "changed file must be re-parsed"


# ── Acceptance criterion 3 ──────────────────────────────────────────────────

def test_cache_invalidated_by_version_bump(tmp_path, monkeypatch):
    """After bumping SLICER_VERSION, the old cache entry must not be used."""
    f = _write_py(tmp_path, "sample.py", "def foo(): pass\n")

    parse_calls = []
    real_extract = __import__("slicer.extractor", fromlist=["extract_function_inventory"]).extract_function_inventory

    def tracking_extract(path):
        parse_calls.append(path.name)
        return real_extract(path)

    with patch("slicer.cache.extract_function_inventory", side_effect=tracking_extract):
        load_or_parse(f)
        assert parse_calls == ["sample.py"]
        parse_calls.clear()

        # Bump version — old cache key is different, so cache misses
        monkeypatch.setattr(cache_mod, "SLICER_VERSION", "v2")
        load_or_parse(f)

    assert parse_calls == ["sample.py"], "version bump must invalidate cache"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_cache.py -v
```

Expected: ImportError or AttributeError from `slicer.cache`.

- [ ] **Step 3: Implement `slicer/cache.py`**

```python
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from slicer.extractor import extract_function_inventory

CACHE_DIR = Path(".impactguard_cache")
SLICER_VERSION = "v1"


def cache_key(file_path: Path) -> str:
    content = file_path.read_bytes()
    return hashlib.sha256(content + SLICER_VERSION.encode()).hexdigest()


def load_or_parse(file_path: Path) -> dict:
    key = cache_key(file_path)
    cache_file = CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    result = extract_function_inventory(file_path)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Atomic write: rename is atomic on POSIX; on Windows it's best-effort but safe here
    # because concurrent writes of the same key produce identical content.
    tmp = cache_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache_file)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_cache.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add slicer/cache.py tests/test_cache.py
git commit -m "feat: implement file-based cache keyed by sha256(content + version)"
```

---

## Task 5: `slicer/folding.py` — Diff Folding & Module-Level Preservation

**Files:**
- Modify: `slicer/folding.py`

**Interfaces:**
- Consumes: `extract_function_inventory` return type (from Task 2)
- Produces:
  - `overlaps(byte_range: tuple[int, int], changed_ranges: list[tuple[int, int]]) -> bool`
  - `apply_diff_folding(inventory: dict, changed_byte_ranges: dict) -> dict`
    - `inventory` is `{str(file_path): <extract_function_inventory result>}`
    - `changed_byte_ranges` is `{str(file_path): [(start, end), ...]}`
    - Returns `{str(file_path): {"func_name": "full_body or stub", "$module": "text if any changed"}}` — `$module` key omitted when no module-level code changed

- [ ] **Step 1: Create test fixtures**

`tests/fixtures/sample_with_unicode.py`:

```python
# 这是一个包含中文注释的Python文件
# 用于测试UTF-8多字节字符的字节偏移计算

"""模块文档：包含多字节UTF-8字符"""

CONSTANT = 1  # 常量


def unchanged_function():
    """此函数不在改动行内，应该被折叠。"""
    return "unchanged"


def target_function(x: int) -> str:
    """目标函数：改动行落在这里。"""
    return str(x * 2)


def after_function() -> None:
    return None
```

`tests/fixtures/sample_module_level_change.py`:

```python
import os
import sys

CONSTANT_ONE = 42
CONSTANT_TWO = "hello"


def some_function() -> int:
    """This function is not changed."""
    return CONSTANT_ONE + 1


class SomeClass:
    CLASS_VAR = "class_level"

    def method(self) -> str:
        return self.CLASS_VAR
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_folding.py`:

```python
import textwrap
from pathlib import Path
import pytest
from slicer.extractor import extract_function_inventory
from slicer.folding import overlaps, apply_diff_folding
from slicer.diff_utils import lines_to_byte_ranges

FIXTURES = Path(__file__).parent / "fixtures"


# ── Acceptance criterion 4 ──────────────────────────────────────────────────

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

    # No lines changed → all functions should be folded to stub
    folded = apply_diff_folding({str(f): inv}, {str(f): []})
    stub = folded[str(f)]["greet"]

    assert 'def greet(name: str, greeting: str = "Hello") -> str:' in stub
    assert '"""Return a greeting string."""' in stub
    assert "result = f" not in stub
    assert "return result" not in stub
    assert "..." in stub


# ── Acceptance criterion 5 ──────────────────────────────────────────────────

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

    # Changed line 4: "    x = 1" — inside foo's body
    changed_ranges = lines_to_byte_ranges(file_bytes, {4})
    folded = apply_diff_folding({str(f): inv}, {str(f): changed_ranges})

    assert "x = 1" in folded[str(f)]["foo"], "changed function must show full body"
    assert "x = 1" not in folded[str(f)]["bar"], "unchanged function must be stub"
    assert "..." in folded[str(f)]["bar"]


# ── Acceptance criterion 6 ──────────────────────────────────────────────────

def test_module_level_change_outside_any_function_kept_full():
    f = FIXTURES / "sample_module_level_change.py"
    inv = extract_function_inventory(f)
    file_bytes = f.read_bytes()

    # Find the line number of "CONSTANT_ONE = 42"
    lines = file_bytes.decode("utf-8").splitlines(keepends=True)
    target_line = next(
        i + 1 for i, l in enumerate(lines) if "CONSTANT_ONE = 42" in l
    )

    changed_ranges = lines_to_byte_ranges(file_bytes, {target_line})
    folded = apply_diff_folding({str(f): inv}, {str(f): changed_ranges})

    file_ctx = folded[str(f)]
    assert "$module" in file_ctx, "module-level change must appear under '$module'"
    assert "CONSTANT_ONE = 42" in file_ctx["$module"]


# ── Acceptance criterion 7 ──────────────────────────────────────────────────

def test_byte_offset_correct_with_non_ascii_content():
    f = FIXTURES / "sample_with_unicode.py"
    inv = extract_function_inventory(f)
    file_bytes = f.read_bytes()

    # Find the line number of "return str(x * 2)" inside target_function
    lines = file_bytes.decode("utf-8").splitlines(keepends=True)
    target_line = next(
        i + 1 for i, l in enumerate(lines) if "return str(x * 2)" in l
    )

    changed_ranges = lines_to_byte_ranges(file_bytes, {target_line})
    folded = apply_diff_folding({str(f): inv}, {str(f): changed_ranges})

    file_ctx = folded[str(f)]
    assert "return str(x * 2)" in file_ctx["target_function"], \
        "byte offset must correctly reach target_function despite preceding Chinese text"
    assert "..." in file_ctx["unchanged_function"], \
        "unchanged_function must still be folded"
```

- [ ] **Step 3: Run tests to verify they fail**

```
pytest tests/test_folding.py -v
```

Expected: ImportError from `slicer.folding`.

- [ ] **Step 4: Implement `slicer/folding.py`**

```python
from __future__ import annotations


def overlaps(
    byte_range: tuple[int, int], changed_ranges: list[tuple[int, int]]
) -> bool:
    """True if [byte_range[0], byte_range[1]) overlaps any range in changed_ranges."""
    a, b = byte_range
    return any(a < ce and cs < b for cs, ce in changed_ranges)


def apply_diff_folding(
    inventory: dict,
    changed_byte_ranges: dict,
) -> dict:
    """Decide full_body vs stub for each function based on diff overlap.

    Args:
        inventory: {file_path_str: extract_function_inventory result}
        changed_byte_ranges: {file_path_str: [(start, end), ...]}

    Returns:
        {file_path_str: {func_name: text, "$module": text (if changed)}}
        "$module" key is present only when module-level code overlaps a changed range.
    """
    context: dict = {}

    for file_str, file_inv in inventory.items():
        ranges = changed_byte_ranges.get(file_str, [])
        file_ctx: dict[str, str] = {}

        for name, meta in file_inv.get("functions", {}).items():
            br = tuple(meta["byte_range"])
            file_ctx[name] = (
                meta["full_body"] if overlaps(br, ranges) else meta["stub"]
            )

        # Preserve module-level regions that overlap changed ranges
        changed_module_parts: list[str] = []
        for region in file_inv.get("module_regions", []):
            if overlaps(tuple(region["byte_range"]), ranges):
                changed_module_parts.append(region["text"])

        if changed_module_parts:
            file_ctx["$module"] = "\n".join(changed_module_parts)

        context[file_str] = file_ctx

    return context
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_folding.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add slicer/folding.py tests/test_folding.py tests/fixtures/
git commit -m "feat: implement diff folding with module-level region preservation"
```

---

## Task 6: `slicer/pipeline.py` — Parallel File Processing

**Files:**
- Modify: `slicer/pipeline.py`

**Interfaces:**
- Consumes: `load_or_parse` from `slicer.cache`
- Produces:
  - `build_inventory_for_files(files: list[Path]) -> dict`
    - Returns `{str(file_path): <extract_function_inventory result>}` for all files

- [ ] **Step 1: Write failing tests**

Create `tests/test_pipeline.py`:

```python
import textwrap
from pathlib import Path
import pytest
from slicer.cache import load_or_parse
from slicer.pipeline import build_inventory_for_files


def _make_py(tmp_path: Path, name: str, src: str) -> Path:
    f = tmp_path / name
    f.write_text(textwrap.dedent(src), encoding="utf-8")
    return f


# ── Acceptance criterion 8 ──────────────────────────────────────────────────

def test_parallel_processing_produces_same_result_as_sequential(tmp_path, monkeypatch):
    """build_inventory_for_files must produce the same result as calling load_or_parse sequentially."""
    import slicer.cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")

    files = [
        _make_py(tmp_path, "a.py", """\
            def alpha(x: int) -> int:
                \"\"\"Alpha docstring.\"\"\"
                return x + 1
        """),
        _make_py(tmp_path, "b.py", """\
            CONSTANT = 99

            def beta() -> str:
                return "beta"
        """),
        _make_py(tmp_path, "c.py", """\
            class Gamma:
                def delta(self) -> None:
                    pass
        """),
    ]

    sequential = {str(f): load_or_parse(f) for f in files}
    # Clear cache so parallel run does its own work
    import shutil
    shutil.rmtree(tmp_path / ".cache", ignore_errors=True)

    parallel = build_inventory_for_files(files)

    assert parallel == sequential


def test_empty_file_list_returns_empty_dict():
    result = build_inventory_for_files([])
    assert result == {}


def test_single_file_returns_correct_inventory(tmp_path, monkeypatch):
    import slicer.cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")

    f = _make_py(tmp_path, "solo.py", """\
        def only_func() -> int:
            return 42
    """)
    result = build_inventory_for_files([f])
    assert str(f) in result
    assert "only_func" in result[str(f)]["functions"]
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_pipeline.py -v
```

Expected: ImportError from `slicer.pipeline`.

- [ ] **Step 3: Implement `slicer/pipeline.py`**

```python
from __future__ import annotations
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from slicer.cache import load_or_parse


def _worker(file_path: Path) -> tuple[str, dict]:
    return str(file_path), load_or_parse(file_path)


def build_inventory_for_files(files: list[Path]) -> dict:
    """Parse all files in parallel using ProcessPoolExecutor.

    Returns {str(file_path): extract_function_inventory result}.
    ProcessPoolExecutor is used (not ThreadPoolExecutor) to bypass the GIL
    for CPU-bound Tree-sitter parsing.
    """
    if not files:
        return {}

    inventory: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        futures = {pool.submit(_worker, f): f for f in files}
        for future in as_completed(futures):
            path_str, result = future.result()
            inventory[path_str] = result

    return inventory
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_pipeline.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add slicer/pipeline.py tests/test_pipeline.py
git commit -m "feat: implement parallel file processing with ProcessPoolExecutor"
```

---

## Task 7: Full Test Suite & Integration Check

**Files:**
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: all slicer modules
- Produces: green full test run

- [ ] **Step 1: Create `tests/conftest.py` with shared fixture**

```python
import pytest
import slicer.cache as cache_mod


@pytest.fixture(autouse=False)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect CACHE_DIR to a temp directory."""
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")
    yield tmp_path / ".cache"
```

- [ ] **Step 2: Run the full test suite**

```
pytest -v --tb=short
```

Expected: all tests in `test_extractor.py`, `test_diff_utils.py`, `test_cache.py`, `test_folding.py`, `test_pipeline.py` PASS.

- [ ] **Step 3: Run with coverage to confirm coverage of core modules**

```
pytest --cov=slicer --cov-report=term-missing -v
```

Expected: `slicer/extractor.py`, `slicer/cache.py`, `slicer/folding.py`, `slicer/diff_utils.py`, `slicer/pipeline.py` all covered. Review any uncovered lines.

- [ ] **Step 4: Verify the public API works end-to-end**

Create a temporary integration smoke test (do not commit):

```python
# Run as: python -c "exec(open('smoke.py').read())"
from pathlib import Path
from slicer import build_inventory_for_files, apply_diff_folding, lines_to_byte_ranges

f = Path("tests/fixtures/sample_with_unicode.py")
inventory = build_inventory_for_files([f])
file_bytes = f.read_bytes()
# Pretend line 15 changed (adjust if fixture changes)
changed_ranges = lines_to_byte_ranges(file_bytes, {15})
context = apply_diff_folding(inventory, {str(f): changed_ranges})
for name, text in context[str(f)].items():
    print(f"\n=== {name} ===\n{text[:200]}")
```

Expected: at least one function shows `...` (stub) and one shows full body.

- [ ] **Step 5: Final commit**

```bash
git add tests/conftest.py
git commit -m "test: add conftest shared fixture and verify full test suite green"
```

---

## Self-Review Against Spec

### Spec Coverage Check

| Requirement | Task(s) |
|-------------|---------|
| No `tree.edit()` | Task 2 — only `parser.parse()` called |
| No Redis/external persistence | Task 4 — `.impactguard_cache/` local FS only |
| Python-only grammar | Task 2 — `tree_sitter_python` only |
| Stubs include signature + docstring | Task 2 (build_signature_stub), Task 5 criterion 4 |
| Phase A cacheable | Tasks 2+4 |
| Phase B in-memory | Task 5 |
| Cache key = sha256(content + version) | Task 4 |
| SLICER_VERSION manual bump | Task 4 |
| No AST tree in cache | Task 4 — JSON with extracted strings only |
| ProcessPoolExecutor, max_workers=os.cpu_count() | Task 6 |
| No asyncio | Not introduced anywhere |
| Module-level changes → `$module` key | Task 5, criterion 6 |
| UTF-8 multi-byte correct | Task 3, criterion 7 |
| test_unchanged_file_hits_cache | Task 4, test_cache.py |
| test_changed_file_misses_cache_only_for_that_file | Task 4, test_cache.py |
| test_cache_invalidated_by_version_bump | Task 4, test_cache.py |
| test_fold_preserves_signature_and_docstring_only | Task 5, test_folding.py |
| test_changed_function_kept_full | Task 5, test_folding.py |
| test_module_level_change_outside_any_function_kept_full | Task 5, test_folding.py |
| test_byte_offset_correct_with_non_ascii_content | Task 5, test_folding.py |
| test_parallel_processing_produces_same_result_as_sequential | Task 6, test_pipeline.py |

### Placeholder Scan

None found. All code steps contain concrete implementations.

### Type Consistency

- `extract_function_inventory` returns `{"functions": {str: {"byte_range": list[int], "full_body": str, "stub": str}}, "module_regions": [{"byte_range": list[int], "text": str}]}`
- `apply_diff_folding` consumes this exact shape in `file_inv.get("functions", {})` and `file_inv.get("module_regions", [])`
- `load_or_parse` returns `extract_function_inventory` result → consistent with `build_inventory_for_files`
- `lines_to_byte_ranges` returns `list[tuple[int, int]]` → consumed as `changed_byte_ranges` values → consistent with `overlaps` parameter type

All consistent. ✓
