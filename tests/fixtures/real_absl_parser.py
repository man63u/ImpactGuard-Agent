# Source: absl-py 2.2.2, absl/flags/_argument_parser.py, lines 73-127
# Used for syntactic parsing only — do not import or execute
from __future__ import annotations

from typing import Generic, List, Optional, TypeVar

_T = TypeVar("_T")


class ArgumentParser(Generic[_T]):
    """Base class for parsers of flag values."""

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
