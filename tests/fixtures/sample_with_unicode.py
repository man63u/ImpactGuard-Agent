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
