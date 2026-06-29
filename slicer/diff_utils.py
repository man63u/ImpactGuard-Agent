from __future__ import annotations


def lines_to_byte_ranges(
    file_bytes: bytes, changed_line_numbers: set[int]
) -> list[tuple[int, int]]:
    ranges = []
    current_line = 1
    line_start = 0
    n = len(file_bytes)
    i = 0
    while i < n:
        if file_bytes[i] == 0x0A:
            if current_line in changed_line_numbers:
                ranges.append((line_start, i + 1))
            line_start = i + 1
            current_line += 1
        i += 1
    if line_start < n and current_line in changed_line_numbers:
        ranges.append((line_start, n))
    return ranges
