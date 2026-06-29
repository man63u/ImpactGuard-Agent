from __future__ import annotations
from collections import defaultdict
from pathlib import Path
from typing import Iterator

from tree_sitter import Language, Node, Parser
import tree_sitter_python as tspython

_PY_LANGUAGE = Language(tspython.language(), 'python')
_parser = Parser()
_parser.set_language(_PY_LANGUAGE)


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
    if node.type != 'decorated_definition':
        return None
    for child in node.children:
        if child.type != 'decorator':
            continue
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
    for child in node.children:
        if child.type == 'decorated_definition':
            inner = child.child_by_field_name('definition')
            if inner is None:
                continue
            if inner.type == 'function_definition':
                name = inner.child_by_field_name('name').text.decode('utf-8')
                qual = f"{parent_class}.{name}" if parent_class else name
                yield qual, child
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
    source = file_path.read_bytes()
    tree = _parser.parse(source)

    groups: dict[str, list] = defaultdict(list)
    for qual_name, node in walk_function_nodes(tree.root_node):
        groups[qual_name].append(node)

    functions: dict[str, dict] = {}
    for qual_name, nodes in groups.items():
        single = len(nodes) == 1
        for idx, node in enumerate(nodes):
            key = qual_name if single else f"{qual_name}#{idx}"
            role = _classify_property_role(node)
            if node.type == 'decorated_definition':
                inner = node.child_by_field_name('definition')
                name_node = (
                    inner.child_by_field_name('name')
                    if inner is not None and inner.type == 'function_definition'
                    else None
                )
            else:
                name_node = node.child_by_field_name('name')
            functions[key] = {
                'byte_range': [node.start_byte, node.end_byte],
                'full_body': node.text.decode('utf-8'),
                'stub': build_signature_stub(node),
                'display_label': role if role else key,
                'name_point': list(name_node.start_point) if name_node else None,
            }

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
