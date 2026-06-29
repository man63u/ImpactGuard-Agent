# Module 1 — Tree-sitter 结构化提取与 Diff 折叠 实现计划

> **给自动执行的 agent：** 必须使用子技能 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务执行本计划。步骤使用 `- [ ]` 复选框语法跟踪进度。

**目标：** 构建一个两阶段流水线——Phase A 用 Tree-sitter 解析 Python 文件并缓存函数清单（cacheable），Phase B 根据 PR 改动行决定每个函数展示 full_body 还是 stub（纯内存，不重跑 Tree-sitter）——最终产出供下游模块消费的结构化字典。

**架构：** Phase A（`extractor.py`）对每个独立的文件内容只运行一次 Tree-sitter，解析结果以 `SHA-256(content + SLICER_VERSION)` 为 key 写入磁盘缓存，通过 `ProcessPoolExecutor` 并行。Phase B（`folding.py`）接收缓存清单和 PR 改动字节范围（由 `diff_utils.py` 计算），完全在内存中完成 full/stub 决策，不触碰 Tree-sitter。模块级代码（import、常量）若改动则以 `"$module"` key 保留，绝不静默丢弃。

**技术栈：** Python 3.10+，tree-sitter 0.22+，tree-sitter-python 0.22+，pytest 7+

## 全局约束

- Python ≥ 3.10（使用 `str | None` 联合类型语法）
- tree-sitter ≥ 0.22，< 1.0（使用 `Parser(language)` 构造函数；**禁止**使用 `tree.edit()`）
- tree-sitter-python ≥ 0.22，< 1.0
- 无 Redis，无外部数据库，无 asyncio——缓存只用本地文件系统
- 只实现 Python grammar；接口预留扩展点，本阶段不添加其他语言
- 折叠后的 stub **必须**保留：函数签名（含参数、类型注解、默认值）+ docstring；绝不能只保留函数名
- `SLICER_VERSION = "v2"` — 提取/折叠逻辑变更时手动升版本号（v1→v2 原因：修复了同名函数互相覆盖导致数据丢失的 bug，旧缓存可能存着错误的 getter-only 数据，必须强制失效）
- 缓存目录：项目根目录下的 `.impactguard_cache/`
- `ProcessPoolExecutor(max_workers=os.cpu_count())` — 禁止硬编码数字
- 模块级改动代码写入 per-file context 的 `"$module"` key；绝不静默丢弃
- UTF-8 字节偏移通过扫描原始字节中的 `0x0A` 计算；禁止用 `len(line_str)` 估算

---

## 文件结构映射

| 文件 | 职责 |
|------|------|
| `requirements.txt` | 运行时依赖：tree-sitter、tree-sitter-python |
| `requirements-dev.txt` | 测试依赖：pytest、pytest-cov |
| `pyproject.toml` | 项目元数据和 pytest 配置 |
| `slicer/__init__.py` | 公共 API 再导出 |
| `slicer/extractor.py` | `walk_function_nodes`、`build_signature_stub`、`extract_function_inventory`、`_classify_property_role` |
| `slicer/diff_utils.py` | `lines_to_byte_ranges` — UTF-8 正确的行号→字节范围转换 |
| `slicer/cache.py` | `cache_key`、`load_or_parse`、`CACHE_DIR`、`SLICER_VERSION` |
| `slicer/folding.py` | `overlaps`、`apply_diff_folding` |
| `slicer/pipeline.py` | `build_inventory_for_files` — 并行入口 |
| `tests/fixtures/sample_with_unicode.py` | 改动行前含中文注释的测试用例 |
| `tests/fixtures/sample_module_level_change.py` | 改动是模块级常量/import 的测试用例 |
| `tests/fixtures/real_starlette_async.py` | 真实 async def fixture（Starlette 0.44.0） |
| `tests/fixtures/real_flask_cli.py` | 真实带参数装饰器 fixture（Flask 1.1.2） |
| `tests/fixtures/real_absl_parser.py` | 真实多行 Google-style docstring fixture（absl-py 2.2.2） |
| `tests/conftest.py` | 共享 fixture（`isolated_cache`） |
| `tests/test_extractor.py` | 提取逻辑测试（6 个原始 + 6 个新增 = 12 个） |
| `tests/test_cache.py` | 缓存正确性测试（3 个验收标准） |
| `tests/test_folding.py` | 折叠与提取测试（4 个验收标准） |
| `tests/test_pipeline.py` | 并行与串行一致性测试（1 个验收标准） |

---

## Task 1：项目脚手架

**文件：**
- 新建：`requirements.txt`
- 新建：`requirements-dev.txt`
- 新建：`pyproject.toml`
- 新建：`slicer/__init__.py`
- 新建：`slicer/extractor.py`（空占位符）
- 新建：`slicer/diff_utils.py`（空占位符）
- 新建：`slicer/cache.py`（空占位符）
- 新建：`slicer/folding.py`（空占位符）
- 新建：`slicer/pipeline.py`（空占位符）
- 新建：`tests/__init__.py`
- 新建：`tests/fixtures/__init__.py`

**接口：**
- 产出：pytest 能发现的可安装包骨架

- [ ] **Step 1：创建 `requirements.txt`**

```
tree-sitter>=0.22,<1.0
tree-sitter-python>=0.22,<1.0
```

- [ ] **Step 2：创建 `requirements-dev.txt`**

```
-r requirements.txt
pytest>=7.0
pytest-cov
```

- [ ] **Step 3：创建 `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

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

> **注意：** `build-backend` 必须是 `"setuptools.build_meta"`，不能是 `"setuptools.backends.legacy:build"`——后者是不存在的值，会报 `ModuleNotFoundError: No module named 'setuptools.backends'`。

- [ ] **Step 4：创建 `slicer/__init__.py`**

```python
from .pipeline import build_inventory_for_files
from .folding import apply_diff_folding
from .diff_utils import lines_to_byte_ranges

__all__ = ["build_inventory_for_files", "apply_diff_folding", "lines_to_byte_ranges"]
```

- [ ] **Step 5：创建空模块占位符**

`slicer/extractor.py`、`slicer/diff_utils.py`、`slicer/cache.py`、`slicer/folding.py`、`slicer/pipeline.py` 各写一行注释：
```python
# placeholder
```

`tests/__init__.py` 和 `tests/fixtures/__init__.py`：空文件。

- [ ] **Step 6：安装依赖**

```
pip install -r requirements-dev.txt
```

预期：无报错。

- [ ] **Step 7：验证 pytest 能发现包**

```
pytest --collect-only
```

预期：0 items collected，无 import 报错。

- [ ] **Step 8：提交**

```bash
git add requirements.txt requirements-dev.txt pyproject.toml slicer/ tests/
git commit -m "feat: scaffold slicer package structure"
```

---

## Task 2：`slicer/extractor.py` — Tree-sitter AST 解析

**文件：**
- 修改：`slicer/extractor.py`
- 新建：`tests/test_extractor.py`
- 新建：`tests/fixtures/real_starlette_async.py`
- 新建：`tests/fixtures/real_flask_cli.py`
- 新建：`tests/fixtures/real_absl_parser.py`

**接口：**
- 消费：无（本任务没有上游依赖）
- 产出：
  - `walk_function_nodes(node: Node, parent_class: str | None = None) -> Iterator[tuple[str, Node]]`
  - `build_signature_stub(node: Node) -> str`
  - `_classify_property_role(node: Node) -> str | None`
  - `extract_function_inventory(file_path: Path) -> dict`，返回结构：
    ```
    {
      "functions": {
        # 无冲突时 key = 裸 qual_name；有冲突时该组全员改为 qual_name#0, qual_name#1...
        # 不变式：裸名出现 <=> 该名字在文件里唯一
        "<qual_name_or_qual_name#N>": {
          "byte_range": [start, end],
          "full_body": str,         # 原始源码文本，不注入合成内容
          "stub": str,              # 签名 + docstring + "..."
          "display_label": str,     # 人类可读标签；识别不出来时回退成 key 本身
        }
      },
      "module_regions": [
        {"byte_range": [start, end], "text": str}   # 不属于任何函数的字节区间
      ]
    }
    ```

**关键设计说明：** 同一 `qual_name` 出现多次（最常见是 `@property`/`@x.setter` getter-setter 对，也可能是 `@typing.overload`、`singledispatch` 等）时，旧实现里 `functions[qual_name] = {...}` 直接赋值会让后一个静默覆盖前一个，且被覆盖函数的 `byte_range` 从"已覆盖"集合里消失，导致其源码被错误地计入 `module_regions`。修复方案：先按 `qual_name` 分组，再统一决定 key。

- [ ] **Step 1：创建三个真实 fixture 文件**

**`tests/fixtures/real_starlette_async.py`**（Starlette 0.44.0，`starlette/concurrency.py` 第 35–37 行）：

```python
# Source: starlette 0.44.0, starlette/concurrency.py, lines 1-37
# Used for syntactic parsing only — do not import or execute
from __future__ import annotations

import functools
import sys
import typing
import warnings

import anyio.to_thread

if sys.version_info >= (3, 10):  # pragma: no cover
    from typing import ParamSpec
else:  # pragma: no cover
    from typing_extensions import ParamSpec

P = ParamSpec("P")
T = typing.TypeVar("T")


async def run_until_first_complete(*args: tuple[typing.Callable, dict]) -> None:  # type: ignore[type-arg]
    warnings.warn(
        "run_until_first_complete is deprecated and will be removed in a future version.",
        DeprecationWarning,
    )

    async with anyio.create_task_group() as task_group:

        async def run(func: typing.Callable[[], typing.Coroutine]) -> None:  # type: ignore[type-arg]
            await func()
            task_group.cancel_scope.cancel()

        for func, kwargs in args:
            task_group.start_soon(run, functools.partial(func, **kwargs))


async def run_in_threadpool(func: typing.Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    func = functools.partial(func, *args, **kwargs)
    return await anyio.to_thread.run_sync(func)
```

**`tests/fixtures/real_flask_cli.py`**（Flask 1.1.2，`flask/cli.py` 第 864–896 行）：

```python
# Source: Flask 1.1.2, flask/cli.py, lines 864-896
# Used for syntactic parsing only — do not import or execute
import click
import os
import sys

# Stubs for Flask-specific decorators used in the source
with_appcontext = lambda f: f
pass_script_info = lambda f: f


@click.command("shell", short_help="Run a shell in the app context.")
@with_appcontext
def shell_command():
    """Run an interactive Python shell in the context of a given
    Flask application.  The application will populate the default
    namespace of this shell according to it's configuration.

    This is useful for executing small snippets of management code
    without having to manually configure the application.
    """
    import code
    from .globals import _app_ctx_stack

    app = _app_ctx_stack.top.app
    banner = "Python %s on %s\nApp: %s [%s]\nInstance: %s" % (
        sys.version,
        sys.platform,
        app.import_name,
        app.env,
        app.instance_path,
    )
    ctx = {}

    startup = os.environ.get("PYTHONSTARTUP")
    if startup and os.path.isfile(startup):
        with open(startup, "r") as f:
            eval(compile(f.read(), startup, "exec"), ctx)

    ctx.update(app.make_shell_context())

    code.interact(banner=banner, local=ctx)
```

**`tests/fixtures/real_absl_parser.py`**（absl-py 2.2.2，`absl/flags/_argument_parser.py` 第 73–112 行）：

```python
# Source: absl-py 2.2.2, absl/flags/_argument_parser.py, lines 73-127
# Used for syntactic parsing only — do not import or execute
from __future__ import annotations

from typing import Generic, List, Optional, TypeVar

_T = TypeVar("_T")


class ArgumentParser(Generic[_T]):
    """Base class for parsers of flag values.

    This class is the base class for Flag value parsers. A subclass should
    be created to override the ``parse()`` method. It is a requirement for a
    correct implementation of ``parse()`` to never modify its argument.

    It is also a requirement for a correct implementation to return objects
    that will not be modified later, since we cache FlagValues.flag_dict.
    """

    syntactic_help: str = ""

    def parse(self, argument: str) -> Optional[_T]:
        """Parses the string argument and returns the native value.

        By default it returns its argument unmodified.

        Args:
          argument: string argument passed in the commandline.

        Raises:
          ValueError: Raised when it fails to parse the argument.
          TypeError: Raised when the argument has the wrong type.

        Returns:
          The parsed value in native type.
        """
        if not isinstance(argument, str):
            raise TypeError(
                'flag value must be a string, found "{}"'.format(type(argument))
            )
        return argument  # type: ignore[return-value]

    def flag_type(self) -> str:
        """Returns a string representing the type of the flag."""
        return "string"
```

- [ ] **Step 2：写失败测试**

创建 `tests/test_extractor.py`：

```python
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

_PY_LANGUAGE = Language(tspython.language())
_parser = Parser(_PY_LANGUAGE)

FIXTURES = Path(__file__).parent / "fixtures"


def _parse(src: str):
    return _parser.parse(src.encode("utf-8")).root_node


# ── 原始 6 个基础测试（保持不变）──────────────────────────────────────────

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


# ── 修订新增：同名函数冲突处理测试（3个）─────────────────────────────────

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
        "full_body 必须是原文，不能被注入合成注释，否则行号会跟源文件错位"
    )


def test_non_property_collision_gets_neutral_label(tmp_path):
    """singledispatch 这种用 '_' 重复命名的场景，不应被错误贴上 property 标签——
    这条测试是防止识别逻辑过度自信的护栏，不是要求系统认出 singledispatch。"""
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
    """无冲突时 key 必须保持裸名——这是本次修复要保证的核心不变式。"""
    f = tmp_path / "sample.py"
    f.write_text("def solo(): pass\n", encoding="utf-8")
    inv = extract_function_inventory(f)

    assert "solo" in inv["functions"]
    assert "solo#0" not in inv["functions"]


# ── 修订新增：真实 fixture 测试（3个）────────────────────────────────────

def test_async_function_is_extracted_correctly():
    """验证 tree-sitter-python 对 async def 的 AST 节点类型，
    以及 walk_function_nodes / build_signature_stub 能正确处理 async def。

    在执行此测试前，先手动运行以下代码确认节点类型：

        from tree_sitter import Language, Parser
        import tree_sitter_python as tspython
        p = Parser(Language(tspython.language()))
        tree = p.parse(b"async def run_in_threadpool(func): pass")
        for child in tree.root_node.children:
            print(child.type)   # 应输出 'function_definition'，不是 'async_function_definition'

    tree-sitter-python >= 0.22 中 async def 和 def 共用同一节点类型 function_definition，
    async 关键字是该节点的第一个子节点。walk_function_nodes 不需要额外分支处理 async 函数。
    """
    f = FIXTURES / "real_starlette_async.py"
    inv = extract_function_inventory(f)

    # walk_function_nodes 必须能识别出 run_in_threadpool（async def，无装饰器）
    assert "run_in_threadpool" in inv["functions"], (
        "walk_function_nodes 未能识别出 async def 函数；"
        "请先打印节点类型确认 tree-sitter-python 对 async def 的实际输出"
    )

    full_body = inv["functions"]["run_in_threadpool"]["full_body"]
    stub = inv["functions"]["run_in_threadpool"]["stub"]

    assert "async def run_in_threadpool" in full_body
    assert "async def run_in_threadpool" in stub, (
        "stub 必须保留 async 关键字，不能丢"
    )


def test_decorator_with_arguments_preserved_in_full_and_stub():
    """验证带参数装饰器（如 @click.command("shell", short_help="...")）
    在 full_body 和 stub 里都被完整保留，括号内的参数不能被截断。

    Fixture 来源：Flask 1.1.2，flask/cli.py，shell_command 函数。
    """
    f = FIXTURES / "real_flask_cli.py"
    inv = extract_function_inventory(f)

    assert "shell_command" in inv["functions"]

    full_body = inv["functions"]["shell_command"]["full_body"]
    stub = inv["functions"]["shell_command"]["stub"]

    # 完整装饰器文本必须在 full_body 里
    assert '@click.command("shell", short_help="Run a shell in the app context.")' in full_body
    # stub 也必须包含完整装饰器（decorated_definition 节点的 byte_range 包含装饰器）
    assert '@click.command("shell", short_help="Run a shell in the app context.")' in stub
    # 确认函数体语句被折叠掉了
    assert "code.interact" not in stub


def test_multiline_docstring_preserved_in_full():
    """验证 Google-style 多行 docstring（含 Args:/Raises:/Returns: 分段）
    在 full_body 里每一行都完整保留。

    Fixture 来源：absl-py 2.2.2，absl/flags/_argument_parser.py，
    ArgumentParser.parse 方法。
    """
    f = FIXTURES / "real_absl_parser.py"
    inv = extract_function_inventory(f)

    assert "ArgumentParser.parse" in inv["functions"]

    full_body = inv["functions"]["ArgumentParser.parse"]["full_body"]

    # 所有 docstring 分段标题必须完整出现在 full_body 里
    assert "Args:" in full_body
    assert "Raises:" in full_body
    assert "Returns:" in full_body
    # 各分段的具体内容行也必须保留
    assert "argument: string argument passed in the commandline." in full_body
    assert "ValueError: Raised when it fails to parse the argument." in full_body
    assert "The parsed value in native type." in full_body
```

- [ ] **Step 3：运行测试，验证失败**

```
pytest tests/test_extractor.py -v
```

预期：ImportError 或 AttributeError（`slicer/extractor.py` 尚为占位符）。

- [ ] **Step 4：实现 `slicer/extractor.py`**

```python
from __future__ import annotations
from collections import defaultdict
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


def _classify_property_role(node: Node) -> str | None:
    """尝试识别这是不是 property 的 getter/setter/deleter 之一。

    识别不出来就返回 None，交给上层走中立兜底，不强行贴语义标签——
    避免在 singledispatch/overload 等场景下贴错标签，这比不贴标签更危险。
    """
    if node.type != 'decorated_definition':
        return None
    for child in node.children:
        if child.type != 'decorator':
            continue
        # decorator 子节点：'@' token + 装饰器表达式；取最后一个子节点作为表达式
        expr = child.children[-1]
        if expr.type == 'identifier' and expr.text == b'property':
            return 'property getter'
        if expr.type == 'attribute':
            attr = expr.child_by_field_name('attribute')
            if attr and attr.text in (b'setter', b'deleter'):
                return f"property {attr.text.decode()}"
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
        # 无冲突时 key = 裸 qual_name；有冲突时该组全员改为 qual_name#0, qual_name#1...
        # 不变式：裸名出现 <=> 该名字在文件里唯一
        "<key>": {
          "byte_range": [start, end],
          "full_body": str,       # 原始源码，绝不注入合成内容
          "stub": str,
          "display_label": str,   # 人类可读标签；识别不出来时回退成 key 本身
        }
      },
      "module_regions": [
        {"byte_range": [start, end], "text": str}   # bytes not inside any function
      ]
    }
    """
    source = file_path.read_bytes()
    tree = _parser.parse(source)

    # 第一阶段：按 qual_name 分组，只收集，不决定 key
    groups: dict[str, list] = defaultdict(list)
    for qual_name, node in walk_function_nodes(tree.root_node):
        groups[qual_name].append(node)

    # 第二阶段：组内只有一个 -> 裸名；有冲突 -> 全员编号（不管冲突原因）
    functions: dict[str, dict] = {}
    for qual_name, nodes in groups.items():
        single = len(nodes) == 1
        for idx, node in enumerate(nodes):
            key = qual_name if single else f"{qual_name}#{idx}"
            role = _classify_property_role(node)
            functions[key] = {
                'byte_range': [node.start_byte, node.end_byte],
                'full_body': node.text.decode('utf-8'),
                'stub': build_signature_stub(node),
                'display_label': role if role else key,
            }

    # module_regions 计算：遍历 functions.values() 取 byte_range 算"已覆盖区间"。
    # 现在 functions 不再丢失任何函数的 byte_range，这部分计算自动修复。
    covered = sorted(
        (m['byte_range'][0], m['byte_range'][1]) for m in functions.values()
    )
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

- [ ] **Step 5：运行测试，验证通过**

```
pytest tests/test_extractor.py -v
```

预期：全部 12 个测试 PASS。

- [ ] **Step 6：提交**

```bash
git add slicer/extractor.py tests/test_extractor.py tests/fixtures/real_starlette_async.py tests/fixtures/real_flask_cli.py tests/fixtures/real_absl_parser.py
git commit -m "feat: implement Tree-sitter extraction with collision-safe naming and display_label"
```

---

## Task 3：`slicer/diff_utils.py` — UTF-8 正确的行号→字节范围转换

**（本任务内容与原文档完全一致，未做任何修改）**

**文件：**
- 修改：`slicer/diff_utils.py`

**接口：**
- 消费：无
- 产出：
  - `lines_to_byte_ranges(file_bytes: bytes, changed_line_numbers: set[int]) -> list[tuple[int, int]]`
    - `changed_line_numbers` 从 1 开始计数
    - 返回每条匹配行的 `(start_byte_inclusive, end_byte_exclusive)` 列表

- [ ] **Step 1：写失败测试**

创建 `tests/test_diff_utils.py`：

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
    expected_start = len(line1)              # 7
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

- [ ] **Step 2：运行测试，验证失败**

```
pytest tests/test_diff_utils.py -v
```

预期：ImportError 或 AttributeError。

- [ ] **Step 3：实现 `slicer/diff_utils.py`**

```python
from __future__ import annotations


def lines_to_byte_ranges(
    file_bytes: bytes, changed_line_numbers: set[int]
) -> list[tuple[int, int]]:
    """Convert 1-indexed line numbers to byte ranges.

    Scans raw bytes for 0x0A — correct for UTF-8 because multibyte sequences
    use bytes 0x80–0xFF, so '\\n' (0x0A) is unambiguous.
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

- [ ] **Step 4：运行测试，验证通过**

```
pytest tests/test_diff_utils.py -v
```

预期：全部 6 个测试 PASS。

- [ ] **Step 5：提交**

```bash
git add slicer/diff_utils.py tests/test_diff_utils.py
git commit -m "feat: implement UTF-8-correct line-to-byte-range conversion"
```

---

## Task 4：`slicer/cache.py` — 基于文件的缓存层

**文件：**
- 修改：`slicer/cache.py`
- 新建：`tests/test_cache.py`

**接口：**
- 消费：`slicer.extractor` 的 `extract_function_inventory`
- 产出：
  - `CACHE_DIR: Path` — `.impactguard_cache/`
  - `SLICER_VERSION: str` — `"v2"`（从 v1 升到 v2，原因：修复同名函数覆盖 bug，旧缓存可能含错误数据）
  - `cache_key(file_path: Path) -> str`
  - `load_or_parse(file_path: Path) -> dict`

- [ ] **Step 1：写失败测试**

创建 `tests/test_cache.py`：

```python
import json
from pathlib import Path
from unittest.mock import patch
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


# ── 验收标准 1 ──────────────────────────────────────────────────────────────

def test_unchanged_file_hits_cache(tmp_path):
    """第二次调用 load_or_parse 不应重新触发 extract_function_inventory。"""
    f = _write_py(tmp_path, "sample.py", "def foo(): pass\n")

    call_count = 0
    real_extract = __import__(
        "slicer.extractor", fromlist=["extract_function_inventory"]
    ).extract_function_inventory

    def counting_extract(path):
        nonlocal call_count
        call_count += 1
        return real_extract(path)

    with patch("slicer.cache.extract_function_inventory", side_effect=counting_extract):
        load_or_parse(f)
        load_or_parse(f)

    assert call_count == 1, "解析只应被调用一次；第二次调用必须命中缓存"


# ── 验收标准 2 ──────────────────────────────────────────────────────────────

def test_changed_file_misses_cache_only_for_that_file(tmp_path):
    """只改了一个文件时，其余文件仍命中缓存，只有该文件被重新解析。"""
    f1 = _write_py(tmp_path, "a.py", "def alpha(): pass\n")
    f2 = _write_py(tmp_path, "b.py", "def beta(): pass\n")

    parse_calls: list[str] = []
    real_extract = __import__(
        "slicer.extractor", fromlist=["extract_function_inventory"]
    ).extract_function_inventory

    def tracking_extract(path):
        parse_calls.append(path.name)
        return real_extract(path)

    with patch("slicer.cache.extract_function_inventory", side_effect=tracking_extract):
        load_or_parse(f1)
        load_or_parse(f2)
        parse_calls.clear()

        # 只修改 f2
        f2.write_text("def beta_v2(): pass\n", encoding="utf-8")
        load_or_parse(f1)
        load_or_parse(f2)

    assert "a.py" not in parse_calls, "未改动的文件必须命中缓存"
    assert "b.py" in parse_calls, "已改动的文件必须重新解析"


# ── 验收标准 3 ──────────────────────────────────────────────────────────────

def test_cache_invalidated_by_version_bump(tmp_path, monkeypatch):
    """升级 SLICER_VERSION 后，旧缓存条目不应被使用。

    注意：默认 SLICER_VERSION 现在是 "v2"，所以这里 monkeypatch 的目标值必须是
    "v3"（或任何与 "v2" 不同的值），才能真正测试"版本号变更导致缓存失效"这一行为。
    如果把 "v2" monkeypatch 成 "v2"，测试会通过但不再验证版本升级的效果。
    """
    f = _write_py(tmp_path, "sample.py", "def foo(): pass\n")

    parse_calls = []
    real_extract = __import__(
        "slicer.extractor", fromlist=["extract_function_inventory"]
    ).extract_function_inventory

    def tracking_extract(path):
        parse_calls.append(path.name)
        return real_extract(path)

    with patch("slicer.cache.extract_function_inventory", side_effect=tracking_extract):
        load_or_parse(f)
        assert parse_calls == ["sample.py"]
        parse_calls.clear()

        # 升级版本号 — 旧缓存 key 不同，所以缓存未命中
        monkeypatch.setattr(cache_mod, "SLICER_VERSION", "v3")
        load_or_parse(f)

    assert parse_calls == ["sample.py"], "版本号升级必须让缓存失效"
```

- [ ] **Step 2：运行测试，验证失败**

```
pytest tests/test_cache.py -v
```

预期：ImportError 或 AttributeError from `slicer.cache`。

- [ ] **Step 3：实现 `slicer/cache.py`**

```python
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from slicer.extractor import extract_function_inventory

CACHE_DIR = Path(".impactguard_cache")
# v1→v2: fixed silent overwrite of same-named functions (e.g. property getter/setter pairs);
# old caches may contain inventories with missing functions — must be invalidated.
SLICER_VERSION = "v2"


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

- [ ] **Step 4：运行测试，验证通过**

```
pytest tests/test_cache.py -v
```

预期：全部 3 个测试 PASS。

- [ ] **Step 5：提交**

```bash
git add slicer/cache.py tests/test_cache.py
git commit -m "feat: implement file-based cache keyed by sha256(content+version), bump to v2"
```

---

## Task 5：`slicer/folding.py` — Diff 折叠与模块级改动保留

**（本任务内容与原文档完全一致，未做任何修改）**

**文件：**
- 修改：`slicer/folding.py`

**接口：**
- 消费：`extract_function_inventory` 的返回类型（来自 Task 2）
- 产出：
  - `overlaps(byte_range: tuple[int, int], changed_ranges: list[tuple[int, int]]) -> bool`
  - `apply_diff_folding(inventory: dict, changed_byte_ranges: dict) -> dict`
    - `inventory` 的格式是 `{str(file_path): <extract_function_inventory 返回值>}`
    - `changed_byte_ranges` 的格式是 `{str(file_path): [(start, end), ...]}`
    - 返回 `{str(file_path): {"func_name": "full_body 或 stub", "$module": "text（如有改动）"}}`
    - `$module` key 仅在模块级代码与改动范围重叠时出现

- [ ] **Step 1：创建测试 fixture 文件**

`tests/fixtures/sample_with_unicode.py`：

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

`tests/fixtures/sample_module_level_change.py`：

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

- [ ] **Step 2：写失败测试**

创建 `tests/test_folding.py`：

```python
import textwrap
from pathlib import Path
import pytest
from slicer.extractor import extract_function_inventory
from slicer.folding import overlaps, apply_diff_folding
from slicer.diff_utils import lines_to_byte_ranges

FIXTURES = Path(__file__).parent / "fixtures"


# ── 验收标准 4 ──────────────────────────────────────────────────────────────

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

    # 无改动行 → 所有函数都应折叠为 stub
    folded = apply_diff_folding({str(f): inv}, {str(f): []})
    stub = folded[str(f)]["greet"]

    assert 'def greet(name: str, greeting: str = "Hello") -> str:' in stub
    assert '"""Return a greeting string."""' in stub
    assert "result = f" not in stub
    assert "return result" not in stub
    assert "..." in stub


# ── 验收标准 5 ──────────────────────────────────────────────────────────────

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

    # 改动行 4："    x = 1"——在 foo 的函数体内
    changed_ranges = lines_to_byte_ranges(file_bytes, {4})
    folded = apply_diff_folding({str(f): inv}, {str(f): changed_ranges})

    assert "x = 1" in folded[str(f)]["foo"], "改动函数必须展示完整函数体"
    assert "x = 1" not in folded[str(f)]["bar"], "未改动函数必须折叠为 stub"
    assert "..." in folded[str(f)]["bar"]


# ── 验收标准 6 ──────────────────────────────────────────────────────────────

def test_module_level_change_outside_any_function_kept_full():
    f = FIXTURES / "sample_module_level_change.py"
    inv = extract_function_inventory(f)
    file_bytes = f.read_bytes()

    # 找到 "CONSTANT_ONE = 42" 所在行号
    lines = file_bytes.decode("utf-8").splitlines(keepends=True)
    target_line = next(
        i + 1 for i, l in enumerate(lines) if "CONSTANT_ONE = 42" in l
    )

    changed_ranges = lines_to_byte_ranges(file_bytes, {target_line})
    folded = apply_diff_folding({str(f): inv}, {str(f): changed_ranges})

    file_ctx = folded[str(f)]
    assert "$module" in file_ctx, "模块级改动必须出现在 '$module' key 下"
    assert "CONSTANT_ONE = 42" in file_ctx["$module"]


# ── 验收标准 7 ──────────────────────────────────────────────────────────────

def test_byte_offset_correct_with_non_ascii_content():
    f = FIXTURES / "sample_with_unicode.py"
    inv = extract_function_inventory(f)
    file_bytes = f.read_bytes()

    # 找到 "return str(x * 2)" 所在行号（在 target_function 函数体内）
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
```

- [ ] **Step 3：运行测试，验证失败**

```
pytest tests/test_folding.py -v
```

预期：ImportError from `slicer.folding`。

- [ ] **Step 4：实现 `slicer/folding.py`**

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

        # 保留与改动范围重叠的模块级区域
        changed_module_parts: list[str] = []
        for region in file_inv.get("module_regions", []):
            if overlaps(tuple(region["byte_range"]), ranges):
                changed_module_parts.append(region["text"])

        if changed_module_parts:
            file_ctx["$module"] = "\n".join(changed_module_parts)

        context[file_str] = file_ctx

    return context
```

- [ ] **Step 5：运行测试，验证通过**

```
pytest tests/test_folding.py -v
```

预期：全部 4 个测试 PASS。

- [ ] **Step 6：提交**

```bash
git add slicer/folding.py tests/test_folding.py tests/fixtures/
git commit -m "feat: implement diff folding with module-level region preservation"
```

---

## Task 6：`slicer/pipeline.py` — 并行文件处理

**（本任务内容与原文档完全一致，未做任何修改）**

**文件：**
- 修改：`slicer/pipeline.py`

**接口：**
- 消费：`slicer.cache` 的 `load_or_parse`
- 产出：
  - `build_inventory_for_files(files: list[Path]) -> dict`
    - 返回 `{str(file_path): <extract_function_inventory 返回值>}` for all files

- [ ] **Step 1：写失败测试**

创建 `tests/test_pipeline.py`：

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


# ── 验收标准 8 ──────────────────────────────────────────────────────────────

def test_parallel_processing_produces_same_result_as_sequential(tmp_path, monkeypatch):
    """build_inventory_for_files 的结果必须与逐个顺序调用 load_or_parse 的结果一致。"""
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
    # 清除缓存，让并行执行重新解析
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

- [ ] **Step 2：运行测试，验证失败**

```
pytest tests/test_pipeline.py -v
```

预期：ImportError from `slicer.pipeline`。

- [ ] **Step 3：实现 `slicer/pipeline.py`**

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

- [ ] **Step 4：运行测试，验证通过**

```
pytest tests/test_pipeline.py -v
```

预期：全部 3 个测试 PASS。

- [ ] **Step 5：提交**

```bash
git add slicer/pipeline.py tests/test_pipeline.py
git commit -m "feat: implement parallel file processing with ProcessPoolExecutor"
```

---

## Task 7：完整测试套件运行与集成验证

**（本任务内容与原文档完全一致，未做任何修改）**

**文件：**
- 新建：`tests/conftest.py`

**接口：**
- 消费：所有 slicer 模块
- 产出：绿色完整测试运行

- [ ] **Step 1：创建 `tests/conftest.py`**

```python
import pytest
import slicer.cache as cache_mod


@pytest.fixture(autouse=False)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect CACHE_DIR to a temp directory."""
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")
    yield tmp_path / ".cache"
```

- [ ] **Step 2：运行完整测试套件**

```
pytest -v --tb=short
```

预期：`test_extractor.py`、`test_diff_utils.py`、`test_cache.py`、`test_folding.py`、`test_pipeline.py` 中的所有测试 PASS。

- [ ] **Step 3：覆盖率检查**

```
pytest --cov=slicer --cov-report=term-missing -v
```

预期：`slicer/extractor.py`、`slicer/cache.py`、`slicer/folding.py`、`slicer/diff_utils.py`、`slicer/pipeline.py` 核心代码路径全部覆盖。检查并处理未覆盖行。

- [ ] **Step 4：端到端 API 冒烟测试**

临时创建冒烟脚本（不提交）：

```python
# Run as: python -c "exec(open('smoke.py').read())"
from pathlib import Path
from slicer import build_inventory_for_files, apply_diff_folding, lines_to_byte_ranges

f = Path("tests/fixtures/sample_with_unicode.py")
inventory = build_inventory_for_files([f])
file_bytes = f.read_bytes()
# 假设第 15 行有改动（如 fixture 内容改变请相应调整行号）
changed_ranges = lines_to_byte_ranges(file_bytes, {15})
context = apply_diff_folding(inventory, {str(f): changed_ranges})
for name, text in context[str(f)].items():
    print(f"\n=== {name} ===\n{text[:200]}")
```

预期：至少有一个函数显示 `...`（stub），有一个显示完整函数体。

- [ ] **Step 5：最终提交**

```bash
git add tests/conftest.py
git commit -m "test: add conftest shared fixture and verify full test suite green"
```

---

## 规格覆盖自查（Self-Review）

### 规格覆盖检查

| 需求 | 对应任务 |
|------|---------|
| 禁止 `tree.edit()` | Task 2 — 只调用 `parser.parse()` |
| 禁止 Redis/外部持久化 | Task 4 — `.impactguard_cache/` 本地 FS |
| 只实现 Python grammar | Task 2 — 只用 `tree_sitter_python` |
| Stub 必须包含签名 + docstring | Task 2（`build_signature_stub`），Task 5 验收标准 4 |
| Phase A 可缓存 | Task 2 + Task 4 |
| Phase B 纯内存 | Task 5 |
| 缓存 key = sha256(content + version) | Task 4 |
| `SLICER_VERSION` 手动升级 | Task 4 — v1→v2，代码注释说明原因 |
| 缓存中不保存 AST 树对象 | Task 4 — 只缓存 JSON 可序列化的字符串 |
| `ProcessPoolExecutor, max_workers=os.cpu_count()` | Task 6 |
| 禁止 asyncio | 所有任务中均未引入 |
| 模块级改动 → `$module` key | Task 5，验收标准 6 |
| UTF-8 多字节字符正确处理 | Task 3，验收标准 7 |
| **同名函数不覆盖（新增）** | Task 2 — `defaultdict` 分组，`#N` 编号 |
| **`display_label` 字段（新增）** | Task 2 — `_classify_property_role` + 兜底回退 |
| **`pyproject.toml` build-backend 正确（修复）** | Task 1 — `"setuptools.build_meta"` |
| **SLICER_VERSION 默认值更新为 v2（修订）** | Task 4，全局约束 |
| `test_unchanged_file_hits_cache` | Task 4，`test_cache.py` |
| `test_changed_file_misses_cache_only_for_that_file` | Task 4，`test_cache.py` |
| `test_cache_invalidated_by_version_bump`（monkeypatch 目标改为 "v3"） | Task 4，`test_cache.py` |
| `test_fold_preserves_signature_and_docstring_only` | Task 5，`test_folding.py` |
| `test_changed_function_kept_full` | Task 5，`test_folding.py` |
| `test_module_level_change_outside_any_function_kept_full` | Task 5，`test_folding.py` |
| `test_byte_offset_correct_with_non_ascii_content` | Task 5，`test_folding.py` |
| `test_parallel_processing_produces_same_result_as_sequential` | Task 6，`test_pipeline.py` |
| **`test_property_pair_gets_unique_keys_and_labels`（新增）** | Task 2，`test_extractor.py` |
| **`test_non_property_collision_gets_neutral_label`（新增）** | Task 2，`test_extractor.py` |
| **`test_single_occurrence_keeps_bare_name`（新增）** | Task 2，`test_extractor.py` |
| **`test_async_function_is_extracted_correctly`（新增）** | Task 2，`test_extractor.py`，fixture: `real_starlette_async.py` |
| **`test_decorator_with_arguments_preserved_in_full_and_stub`（新增）** | Task 2，`test_extractor.py`，fixture: `real_flask_cli.py` |
| **`test_multiline_docstring_preserved_in_full`（新增）** | Task 2，`test_extractor.py`，fixture: `real_absl_parser.py` |

### 占位符扫描

无占位符。所有步骤均包含完整的实现代码。

### 类型一致性

- `extract_function_inventory` 返回 `{"functions": {str: {"byte_range": list[int], "full_body": str, "stub": str, "display_label": str}}, "module_regions": [{"byte_range": list[int], "text": str}]}`
- `apply_diff_folding` 在 `file_inv.get("functions", {})` 中消费此格式，访问 `meta["byte_range"]`、`meta["full_body"]`、`meta["stub"]` ——与上述结构一致（`display_label` 不被 folding 消费，可忽略）
- `load_or_parse` 返回 `extract_function_inventory` 的结果 → 与 `build_inventory_for_files` 的返回值一致
- `lines_to_byte_ranges` 返回 `list[tuple[int, int]]` → 作为 `changed_byte_ranges` 的值消费 → 与 `overlaps` 的参数类型一致
- `test_cache_invalidated_by_version_bump` 中 monkeypatch 目标值为 `"v3"`，与新默认值 `"v2"` 不同 ✓

全部一致。✓

---

## 修订变更摘要（相对原文档）

| 修订项 | 涉及任务 | 具体改动 |
|--------|---------|---------|
| 修复同名函数覆盖 bug | Task 2 | `extract_function_inventory` 改用 `defaultdict` 分组 + `#N` 编号；新增 `_classify_property_role` |
| 新增 `display_label` 字段 | Task 2 | 函数清单每项增加 `display_label`；property getter/setter 识别；兜底回退成 key |
| 新增 3 个冲突命名测试 | Task 2 | `test_property_pair_*`、`test_non_property_collision_*`、`test_single_occurrence_*` |
| 新增 3 个真实 fixture 测试 | Task 2 | async def（Starlette 0.44.0）、带参数装饰器（Flask 1.1.2）、多行 Google docstring（absl-py 2.2.2） |
| `SLICER_VERSION` v1→v2 | Task 4，全局约束 | 代码注释说明升版本原因 |
| `test_cache_invalidated_by_version_bump` monkeypatch 目标改为 "v3" | Task 4 | 防止测试变为"v2→v2"而失去验证意义 |
| 修正 `pyproject.toml` build-backend | Task 1 | `"setuptools.backends.legacy:build"` → `"setuptools.build_meta"` |
| Task 5/6/7 内容 | — | **未做任何改动** |
| 整体语言 | — | 说明性文字、任务描述、表格改为中文；代码/变量名/注释/commit message 保持英文 |
