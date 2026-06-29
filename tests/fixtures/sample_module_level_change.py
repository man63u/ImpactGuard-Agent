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
