#
# cursorlist.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A cursor-based list which indexes based off of an arbitrary
cursor position.
"""

from typing import Any, Dict, Generic, List, Optional, TypeVar

CT = TypeVar("CT")


class CursorList(Generic[CT]):
    """
    Keeps a sorted list of data and an index into it based off of a key and cursor.

    A CursorList takes a list of dictionary objects and sorts it by the given key.
    It then locates the integer index corresponding to the given cursor and saves it.
    This row at this index is accessible with CursorList[0].

    The record at [0], if it exists, is guaranteed to be the closest possible row
    to the cursor without exceeding it. If all rows are greater than the cursor,
    the index will be -1, and [0] will not be valid.

    When changing the cursor, CursorList will move its index towards the cursor
    until the previous conditions are satisfied.
    """

    data: List[dict]
    key: str
    index: int = -1
    cursor: Optional[CT] = None

    def __init__(self, key: str, data: List[Dict], cursor: CT):
        self.key = key
        self.data = data
        if cursor:
            self.cursor = cursor
        if len(self.data) == 0:
            return
        self._update_data()

    def extend(self, new_data: List[Dict]):
        """Appends new_data onto the existing cursorlist"""
        self.data.extend(new_data)
        self._update_data()

    def _update_data(self):
        """This *must* be called after any change to data. It corrects
        internal state related to the data"""
        if len(self.data) > 0:
            self.data.sort(key=lambda x: x[self.key])
        self.update_cursor()

    def update_cursor(self, new_cursor: Optional[CT] = None):
        """Updates the cursor location"""
        # this function is needed to ensure that the index is
        # valid. It will be reset, or updated to the nearest
        # valid location according to the requirements
        # listed above
        if new_cursor:
            self.cursor = new_cursor
        if self.cursor is None:
            self.index = -1
            return

        # case: index was invalid
        if self.index == -1:
            self.index = int(len(self.data) / 2)

        # case: data is empty
        if len(self.data) == 0:
            self.index = -1
            return

        key_vals = [v[self.key] for v in self.data[:]]

        # case: cursor is below the list
        if key_vals[0] > self.cursor:
            self.index = -1
            return

        # case: cursor is above the list
        if key_vals[len(self.data) - 1] <= self.cursor:
            self.index = len(self.data) - 1
            return

        # case: cursor is in list or above it
        direction = 1 if key_vals[self.index] <= self.cursor else -1

        while True:
            if (
                key_vals[self.index] <= self.cursor
                and key_vals[self.index + 1] > self.cursor
            ):
                break
            self.index += direction

            # out-of-bounds check
            if self.index < 0:
                self.index = -1
                break
            if self.index + 1 >= len(self.data):
                self.index = len(self.data) - 1
                break

        # assert that the cursorlist is in a valid state
        if self.index < 0 or self.index + 1 >= len(self.data):
            return
        assert self.data[self.index][self.key] <= self.cursor
        assert self.data[self.index + 1][self.key] > self.cursor

    def is_valid(self, index: int):
        """Returns True if the index is valid, False otherwise"""
        return self.index != -1 and 0 <= self.index + index < len(self.data)

    def __getitem__(self, index: int) -> Any:
        if self.index == -1:
            raise IndexError(
                "CursorList cursor is out of range, the list cannot be indexed"
            )
        offset_index = self.index + index

        if offset_index < 0 or offset_index >= len(self.data):
            raise IndexError(
                f"Cursorlist index out of range: \
{self.index} + {index} is not in range for 0-{len(self.data)-1}"
            )
        return self.data[offset_index]

    def __repr__(self) -> str:
        return f"CursorList with {len(self.data)} items."

    def __str__(self) -> str:
        return f"CursorList with {len(self.data)} items."
