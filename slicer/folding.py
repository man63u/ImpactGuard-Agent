from __future__ import annotations


def overlaps(
    byte_range: tuple[int, int], changed_ranges: list[tuple[int, int]]
) -> bool:
    """Check if a byte range overlaps with any changed range.

    Uses half-open interval [a, b) semantics: ranges overlap if a < ce and cs < b.

    Args:
        byte_range: Tuple (start, end) representing a half-open byte interval [start, end)
        changed_ranges: List of tuples representing changed byte intervals

    Returns:
        True if byte_range overlaps with any changed_range, False otherwise
    """
    a, b = byte_range
    return any(a < ce and cs < b for cs, ce in changed_ranges)


def apply_diff_folding(
    inventory: dict,
    changed_byte_ranges: dict,
) -> dict:
    """Apply diff-based folding to function inventory.

    Decides which functions to show in full body vs. stub (folded) based on
    whether they overlap with changed byte ranges. Also extracts module-level
    changes (imports, constants) into a special '$module' key.

    Args:
        inventory: Dict mapping file_str to extractor output
                   (contains "functions" and "module_regions" keys)
        changed_byte_ranges: Dict mapping file_str to list of changed byte ranges

    Returns:
        Dict mapping file_str to context dict with function names as keys
        (showing either full_body or stub) and optional "$module" key for
        module-level changes
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

        changed_module_parts: list[str] = []
        for region in file_inv.get("module_regions", []):
            if overlaps(tuple(region["byte_range"]), ranges):
                changed_module_parts.append(region["text"])

        if changed_module_parts:
            file_ctx["$module"] = "\n".join(changed_module_parts)

        context[file_str] = file_ctx

    return context
