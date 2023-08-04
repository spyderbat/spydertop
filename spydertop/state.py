#
# state.py
#
# Author: Griffith Thomas
# Copyright 2023 Spyderbat, Inc. All rights reserved.
#
"""
A module for state management
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, TypeVar

T = TypeVar("T")


class ExitReason(Enum):
    """The different reasons that an ascimatics screen might stop the application"""

    QUIT = "quit"
    BACK_TO_CONFIG = "back_to_config"
    FAILURE = "failure"
    CONTINUE = "continue"


@dataclass
class State:  # pylint: disable=too-many-instance-attributes
    """
    A dataclass containing all state that does not persist across sessions
    """

    # either an api URL or a file-like object containing records
    # input_source: Union[str, TextIO]
    time: Optional[datetime] = None
    org_uid: str = ""
    source_uid: Optional[str] = None

    filter: str = ""
    play: bool = False
    sort_column: Optional[str] = None
    sort_ascending: bool = True

    exit_reason: Optional[ExitReason] = None

    _internal_state: dict = field(init=False, repr=False, default_factory=dict)

    def use_state(self, key: str, value: T) -> T:  # Tuple[T, Callable]:
        """
        Get a value from the internal state, or set it if it doesn't exist.
        This is used to preserve state across screen resizes.
        """
        if key in self._internal_state:
            return self._internal_state[key]
        self._internal_state[key] = value
        return self._internal_state[key]
