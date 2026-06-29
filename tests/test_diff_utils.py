from slicer.diff_utils import lines_to_byte_ranges


def test_single_changed_line():
    content = b"line1\nline2\nline3\n"
    result = lines_to_byte_ranges(content, {2})
    assert result == [(6, 12)]


def test_multiple_changed_lines():
    content = b"line1\nline2\nline3\n"
    result = lines_to_byte_ranges(content, {1, 3})
    assert result == [(0, 6), (12, 18)]


def test_no_changed_lines():
    content = b"line1\nline2\n"
    result = lines_to_byte_ranges(content, set())
    assert result == []


def test_last_line_without_newline():
    content = b"line1\nline2"
    result = lines_to_byte_ranges(content, {2})
    assert result == [(6, 11)]


def test_utf8_multibyte_characters():
    # "你好\n" = 7 bytes (3+3+1), "world\n" = 6 bytes
    content = "你好\nworld\n".encode("utf-8")
    result = lines_to_byte_ranges(content, {1})
    assert result == [(0, 7)]


def test_all_lines_changed():
    content = b"a\nb\nc\n"
    result = lines_to_byte_ranges(content, {1, 2, 3})
    assert result == [(0, 2), (2, 4), (4, 6)]
