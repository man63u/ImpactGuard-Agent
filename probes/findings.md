# Module 2 预研发现报告

运行环境：Python 3.8.3 (Anaconda)，multilspy 0.0.15，jedi-language-server 0.41.3，tree-sitter 0.21.3

---

## 问题 1：multilspy 返回结构 + 坐标系是否 0-indexed

### 探测脚本

`probes/probe1_multilspy_shape.py`

fixture_a 文件内容：

```
# lib.py
row 0: def helper():
row 1:     return 42

# main.py
row 0: from lib import helper
row 1: (空)
row 2: (空)
row 3: def caller():
row 4:     return helper()
```

查询 1：`request_definition("main.py", 4, 11)` — main.py 第 4 行，col=11（`helper()` 里 `h` 的位置）

查询 2：`request_references("lib.py", 0, 4)` — lib.py 第 0 行，col=4（`def helper():` 里 `h` 的位置）

### 真实输出

**request_definition 输出：**
```python
[{'uri': 'file:///c:/Users/17320/Desktop/ImpactGuard-Agent/probes/fixture_a/lib.py',
  'range': {'start': {'line': 0, 'character': 4}, 'end': {'line': 0, 'character': 10}},
  'absolutePath': 'C:\\Users\\17320\\Desktop\\ImpactGuard-Agent\\probes\\fixture_a\\lib.py',
  'relativePath': 'lib.py'}]
<class 'list'>
keys: ['uri', 'range', 'absolutePath', 'relativePath']
```

**request_references 输出（3 条）：**
```python
[
  # [0] lib.py 定义本身
  {'uri': '...lib.py', 'range': {'start': {'line': 0, 'character': 4}, 'end': {'line': 0, 'character': 10}},
   'absolutePath': '...lib.py', 'relativePath': 'lib.py'},
  # [1] main.py 第 0 行: "from lib import helper"  col=16 是 import 里的 helper
  {'uri': '...main.py', 'range': {'start': {'line': 0, 'character': 16}, 'end': {'line': 0, 'character': 22}},
   'absolutePath': '...main.py', 'relativePath': 'main.py'},
  # [2] main.py 第 4 行: "    return helper()"  col=11 是调用处的 helper
  {'uri': '...main.py', 'range': {'start': {'line': 4, 'character': 11}, 'end': {'line': 4, 'character': 17}},
   'absolutePath': '...main.py', 'relativePath': 'main.py'}
]
```

### 结论

**返回类型：** `list[dict]`，纯 Python dict，每个元素有 4 个 key：`uri`、`range`、`absolutePath`、`relativePath`。`range` 是嵌套 dict：`{'start': {'line': int, 'character': int}, 'end': {'line': int, 'character': int}}`。

**坐标系：** 确认是 **0-indexed**。传入 `main.py` row=4, col=11 正好命中 `helper` 的第一个字母 `h`；返回的定义位置是 `lib.py` line=0, character=4，也是 `def helper():` 里 `h` 的正确位置。与 Tree-sitter 的 `start_point` 完全一致（也是 `(row, col)` 0-indexed）——**可以直接把 Tree-sitter 的 `start_point` 坐标传给 multilspy，不需要做任何偏移转换**。

**`request_references` 包含的内容：** 返回 3 条：①定义本身，②`import` 语句里的引用，③实际调用处。下一步 `find_call_sites` 需要过滤掉「定义本身」（同文件 + 范围与定义 range 相同），然后视需求决定是否保留 import 引用（import 引用只说明「这个文件用了它」，但不是 call 节点；真正的调用点是 col 恰好落在 call node `function` 字段 `start_point` 的那条）。

---

## 问题 2：Flask 装饰器路由，request_references 看不看得到被装饰这件事

### 探测脚本

`probes/probe2_flask_decorator.py`

fixture_b 文件内容：

```
# app.py
row 0: from flask import Flask
row 1: (空)
row 2: app = Flask(__name__)
row 3: (空)
row 4: (空)
row 5: @app.route("/health")
row 6: def health_check():
row 7:     return "ok"
```

查询：`request_references("app.py", 6, 4)` — 函数名 `health_check` 所在位置

### 真实输出

```python
[{'uri': '...app.py',
  'range': {'start': {'line': 6, 'character': 4}, 'end': {'line': 6, 'character': 16}},
  'absolutePath': '...app.py', 'relativePath': 'app.py'}]
type: <class 'list'>
count: 1
```

### 结论

**只返回 1 条：函数定义本身**（line=6, char=4-16 正是 `health_check` 这个名字的位置）。`@app.route("/health")` 装饰器那一行（row=5）**不在**结果里。

这是预期内的结果：Flask 路由分发是运行时动态的，没有任何静态文本引用调用了 `health_check`。对 BFS fan-in 的影响是：从这类函数往上查调用方，`request_references` 只会返回定义本身，过滤掉后结果为空——**BFS 在此自然终止，不需要特殊处理**。如果将来需要标注「这是一个入口点（entry point）」，可以在 `extract_function_inventory` 阶段检查 `decorated_definition` 里是否有 `@xxx.route`/`@router.get` 等装饰器，打上标记；但那是另一个任务的事。

---

## 问题 3：tree-sitter call 节点，`foo(x)` 和 `obj.method(x)` 下的节点形状

### 探测脚本

`probes/probe3_call_node_shape.py`

测试源码：
```python
def f():
    foo(1)
    obj.method(2)
```

### 真实输出（关键部分）

```
'call' [(2, 4) - (2, 10)] text='foo(1)'
  'identifier' [(2, 4) - (2, 7)] text='foo'      ← function 字段
  'argument_list' ...

'call' [(3, 4) - (3, 17)] text='obj.method(2)'
  'attribute' [(3, 4) - (3, 14)] text='obj.method'  ← function 字段
    'identifier' [(3, 4) - (3, 7)] text='obj'
    '.' ...
    'identifier' [(3, 8) - (3, 14)] text='method'
  'argument_list' ...

=== function 字段详情 ===

call='foo(1)'
  function字段 node.type: 'identifier'
  function字段 start_point: (2, 4)

call='obj.method(2)'
  function字段 node.type: 'attribute'
  function字段 start_point: (3, 4)
  attribute子字段 (child_by_field_name('attribute')): <Node type=identifier, start_point=(3, 8), end_point=(3, 14)>
    type='identifier', text='method', start_point=(3, 8)
  object子字段 (child_by_field_name('object')): <Node type=identifier, start_point=(3, 4), end_point=(3, 7)>
    type='identifier', text='obj'
  全部 children: [0]=identifier('obj'), [1]='.', [2]=identifier('method')
```

### 结论

**`foo(1)` 直接调用：** `call` 节点的 `function` 字段类型是 `'identifier'`，`start_point` 就是函数名的位置——可以直接传给 `request_definition`。

**`obj.method(2)` 属性调用：** `call` 节点的 `function` 字段类型是 `'attribute'`。`attribute` 节点内部有两个具名子字段：
- `child_by_field_name("object")` → `identifier`，文本是 `'obj'`（被调用的对象）
- `child_by_field_name("attribute")` → `identifier`，文本是 `'method'`，`start_point=(3, 8)`（方法名的位置）

**字段名核实正确**：`child_by_field_name("attribute")` 确实能取到方法名节点，下一步 `find_call_sites` 里对属性调用应当取 `function.child_by_field_name("attribute").start_point` 传给 `request_definition`——而不是用 `function.start_point`（那指向的是 `obj` 的起始位置，会把 LSP 指到对象那里，找不到方法的定义）。

---

---

## 问题 4（补充）：uri_to_relpath 在 Windows Python 3.8.3 上的实测验证

### 探测脚本

`probes/probe4_uri_normalization.py`

### 真实输出

```
原始uri: file:///c:/Users/17320/Desktop/ImpactGuard-Agent/probes/fixture_a/lib.py
urlparse.path: '/c:/Users/17320/Desktop/ImpactGuard-Agent/probes/fixture_a/lib.py'
url2pathname结果: 'C:\\Users\\17320\\Desktop\\ImpactGuard-Agent\\probes\\fixture_a\\lib.py'
Path(raw_path): C:\Users\17320\Desktop\ImpactGuard-Agent\probes\fixture_a\lib.py
repo_root: C:\Users\17320\Desktop\ImpactGuard-Agent\probes\fixture_a
归一化后: 'lib.py'
通过
```

### 结论

`url2pathname` 在 Windows Python 3.8.3 上正确处理 `/c:/...` → `C:\...`（驱动器字母大写化），`Path.relative_to()` 可以直接使用。

**实现时额外发现一个边界情况**：BFS 追 callee 定义时，如果 callee 定义在 repo_root 之外（stdlib 或第三方库，如 `flask/app.py`），`uri_to_relpath` 会抛 `ValueError`。在 `build_call_graph_context` 里 `for d in callee_defs` 循环中加 `try/except ValueError: continue` 即可——与任务书中"遇到跨边界路径直接跳过"的原则一致。

---

## 问题汇总

| # | 问题 | 结论 |
|---|------|------|
| 1a | multilspy 返回什么类型？ | `list[dict]`，key: `uri`, `range`, `absolutePath`, `relativePath`；`range` 是 `{start: {line, character}, end: {line, character}}` |
| 1b | 坐标系是否 0-indexed？ | 是，与 Tree-sitter `start_point` 完全一致，**无需转换** |
| 2 | Flask 装饰器路由的 references 能看到装饰器吗？ | 不能；只返回定义本身；BFS fan-in 自然终止，无需特殊处理 |
| 3a | `foo(x)` 的 function 字段类型？ | `'identifier'`，用 `function.start_point` 传 LSP |
| 3b | `obj.method(x)` 的 function 字段类型及正确字段名？ | `'attribute'`，用 `child_by_field_name("attribute").start_point` 传 LSP（非 `function.start_point`） |
