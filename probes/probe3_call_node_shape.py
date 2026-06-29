from tree_sitter import Language, Parser
import tree_sitter_python as tspython

# 复用 Module 1 的 0.21.x API
PY_LANGUAGE = Language(tspython.language(), "python")
parser = Parser()
parser.set_language(PY_LANGUAGE)

src = b"""
def f():
    foo(1)
    obj.method(2)
"""
tree = parser.parse(src)


def dump(node, depth=0):
    print("  " * depth + f"{node.type!r} [{node.start_point} - {node.end_point}] text={node.text.decode()!r}")
    for child in node.children:
        dump(child, depth + 1)


print("=== 完整语法树 ===")
dump(tree.root_node)


def find_calls(node, out):
    if node.type == "call":
        out.append(node)
    for child in node.children:
        find_calls(child, out)
    return out


calls = find_calls(tree.root_node, [])

print("\n=== 单独检查每个 call 节点的 function 字段 ===")
for call_node in calls:
    func_field = call_node.child_by_field_name("function")
    print(f"\ncall节点文本: {call_node.text.decode()!r}")
    print(f"  function字段 node.type: {func_field.type!r}")
    print(f"  function字段 text: {func_field.text.decode()!r}")
    print(f"  function字段 start_point: {func_field.start_point}")
    if func_field.type == "attribute":
        # 尝试 "attribute" 字段
        attr = func_field.child_by_field_name("attribute")
        obj_field = func_field.child_by_field_name("object")
        print(f"  attribute子字段 (child_by_field_name('attribute')): {attr}")
        if attr:
            print(f"    type={attr.type!r}, text={attr.text.decode()!r}, start_point={attr.start_point}")
        print(f"  object子字段 (child_by_field_name('object')): {obj_field}")
        if obj_field:
            print(f"    type={obj_field.type!r}, text={obj_field.text.decode()!r}")
        # 列出所有字段名
        print(f"  全部 children (type, field_name, text):")
        for i, child in enumerate(func_field.children):
            print(f"    [{i}] type={child.type!r} text={child.text.decode()!r} named={child.is_named}")
