from __future__ import annotations
import urllib.parse
from collections import deque
from pathlib import Path
from urllib.request import url2pathname

from tree_sitter import Language, Parser
import tree_sitter_python as tspython

from slicer.cache import load_or_parse
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger

_PY_LANGUAGE = Language(tspython.language(), "python")
_parser = Parser()
_parser.set_language(_PY_LANGUAGE)


def uri_to_relpath(uri: str, repo_root: Path) -> str | None:
    """Convert a file:// URI to a repo-root-relative path (forward slashes).

    Returns None if the path is outside repo_root (e.g. stdlib or third-party packages).
    Callers use `if x is None: continue` — no try/except needed.
    """
    parsed = urllib.parse.urlparse(uri)
    abs_path = Path(url2pathname(parsed.path))
    try:
        return str(abs_path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return None


def build_call_index(
    file_path: Path, functions_inventory: dict
) -> dict[tuple[int, int], str | None]:
    """Scan a file once and return a mapping (row, col) -> enclosing_function_key.

    (row, col) is the start position of the callee identifier:
      - direct call foo(x)        -> start_point of the 'identifier' function field
      - attribute call obj.m(x)   -> start_point of child_by_field_name('attribute'),
                                     NOT function.start_point (which points to obj)

    Value is the key of the function that contains the call, or None for module-level calls.
    Serves two purposes:
      1. Find callees of function X: filter entries where value == X.
      2. Validate LSP references: a ref (row, col) is a real call only if (row, col) is in this index.
    """
    source = file_path.read_bytes()
    tree = _parser.parse(source)
    index: dict[tuple[int, int], str | None] = {}

    def enclosing_function_key(byte_offset: int) -> str | None:
        for key, meta in functions_inventory["functions"].items():
            s, e = meta["byte_range"]
            if s <= byte_offset < e:
                return key
        return None

    def visit(node) -> None:
        if node.type == "call":
            func_field = node.child_by_field_name("function")
            if func_field is not None:
                if func_field.type == "identifier":
                    pos = func_field.start_point
                elif func_field.type == "attribute":
                    attr = func_field.child_by_field_name("attribute")
                    pos = attr.start_point if attr is not None else None
                else:
                    pos = None
                if pos is not None:
                    index[tuple(pos)] = enclosing_function_key(node.start_byte)
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return index


def build_call_graph_context(
    seed_functions: list[dict],
    sync_lsp: SyncLanguageServer,
    repo_root: Path,
    inventory_cache: dict,
    call_index_cache: dict,
    max_depth: int = 2,
    fan_in_threshold: int = 15,
) -> dict[tuple[str, str], str]:
    """BFS over the call graph starting from seed_functions.

    Args:
        seed_functions: [{'file': str, 'key': str}, ...] where file is repo-root-relative.
        sync_lsp: already-started SyncLanguageServer.
        repo_root: absolute Path to the repository root.
        inventory_cache: mutable dict, keyed by relpath string; populated on demand.
        call_index_cache: mutable dict, keyed by relpath string; populated on demand.
        max_depth: how many BFS hops to follow (callers + callees each count as one hop).
        fan_in_threshold: functions with more real callers than this are shown as stub only.

    Returns:
        {(file, key): 'full' | 'stub'}
    """
    visited: dict[tuple[str, str], str] = {}
    queue: deque[tuple[str, str, int]] = deque(
        (f["file"], f["key"], 0) for f in seed_functions
    )

    def get_inventory(file: str) -> dict:
        if file not in inventory_cache:
            inventory_cache[file] = load_or_parse(repo_root / file)
        return inventory_cache[file]

    def get_call_index(file: str) -> dict:
        if file not in call_index_cache:
            call_index_cache[file] = build_call_index(
                repo_root / file, get_inventory(file)
            )
        return call_index_cache[file]

    while queue:
        file, key, depth = queue.popleft()
        if (file, key) in visited or depth > max_depth:
            continue

        inv = get_inventory(file)
        meta = inv["functions"].get(key)
        if meta is None or meta.get("name_point") is None:
            continue

        row, col = meta["name_point"]
        definition_loc = (file, row, col)

        raw_refs = sync_lsp.request_references(file, row, col) or []
        callers: list[tuple[str, str]] = []
        for ref in raw_refs:
            ref_file = uri_to_relpath(ref["uri"], repo_root)
            if ref_file is None:
                continue
            ref_row = ref["range"]["start"]["line"]
            ref_col = ref["range"]["start"]["character"]
            if (ref_file, ref_row, ref_col) == definition_loc:
                continue
            caller_key = get_call_index(ref_file).get((ref_row, ref_col))
            if caller_key is not None:
                callers.append((ref_file, caller_key))

        fan_in = len(callers)

        if fan_in > fan_in_threshold:
            visited[(file, key)] = "stub"
            continue

        visited[(file, key)] = "full"

        call_index = get_call_index(file)
        callee_positions = [pos for pos, enc in call_index.items() if enc == key]
        callee_defs: list[dict] = []
        for pos in callee_positions:
            defs = sync_lsp.request_definition(file, *pos) or []
            callee_defs.extend(defs)

        for caller_file, caller_key in callers:
            queue.append((caller_file, caller_key, depth + 1))

        for d in callee_defs:
            d_file = uri_to_relpath(d["uri"], repo_root)
            if d_file is None:
                continue
            d_row = d["range"]["start"]["line"]
            d_col = d["range"]["start"]["character"]
            d_inv = get_inventory(d_file)
            d_key = next(
                (
                    k
                    for k, m in d_inv["functions"].items()
                    if m.get("name_point") is not None
                    and tuple(m["name_point"]) == (d_row, d_col)
                ),
                None,
            )
            if d_key:
                queue.append((d_file, d_key, depth + 1))

    return visited


def run_module2(repo_root: Path, seed_functions: list[dict]) -> dict:
    """Convenience wrapper: start LSP, run BFS, return visited map."""
    config = MultilspyConfig.from_dict({"code_language": "python"})
    lsp = SyncLanguageServer.create(config, MultilspyLogger(), str(repo_root))
    with lsp.start_server():
        return build_call_graph_context(
            seed_functions,
            lsp,
            repo_root,
            inventory_cache={},
            call_index_cache={},
        )
