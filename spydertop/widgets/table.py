#
# table.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
This module contains a table widget which displays data in a tabular format.
It extends the functionality of the asciimatics.widgets.MultiColumnListBox
"""

import re
from typing import Any, Dict, List, NewType, Optional, Tuple, Union

from asciimatics.screen import Screen
from asciimatics.event import KeyboardEvent, MouseEvent
from asciimatics.widgets import Widget
from asciimatics.parsers import Parser
from asciimatics.strings import ColouredText
from spydertop.constants.columns import Column
from spydertop.utils import align_with_overflow

from spydertop.utils.types import ExtendedParser
from spydertop.model import AppModel, Tree
from spydertop.config import Config

InternalRow = NewType("InternalRow", Tuple[List[Union[ColouredText, str]], List[Any]])


class Table(Widget):  # pylint: disable=too-many-instance-attributes
    """
    The main record table for the application. This table
    handles the sorting, filtering, and display of the records.
    """

    tree: Optional[Tree]

    header_enabled: bool = True
    columns: List[Column] = []
    _rows: List[InternalRow] = []
    _filtered_rows: List[InternalRow] = []
    _tree_rows: Optional[List[InternalRow]] = None

    _config: Config
    _parser: Parser

    _vertical_offset: int = 0
    _horizontal_offset: int = 0

    def __init__(
        self,
        model: AppModel,
        tree: Optional[Tree],
        name="Table",
        parser=ExtendedParser(),
    ):
        super().__init__(
            name, tab_stop=True, disabled=False, on_focus=None, on_blur=None
        )

        self._state, self._set_state = model.use_state(
            name,
            {
                "id_to_follow": None,
                "selected_row": 0,
            },
        )
        self._parser = parser
        self._config = model.config
        self.tree = tree

    def update(
        self, frame_no
    ):  # pylint: disable=too-many-branches,too-many-locals,too-many-statements
        assert self._frame is not None
        # select the followed id
        if self._state["id_to_follow"] is not None and self._config["follow_record"]:
            for i, row in enumerate(self._filtered_rows):
                if row[1][0] == self._state["id_to_follow"]:
                    self.value = i
                    break
        else:
            if len(self._filtered_rows) > 0 and 0 <= self.value < len(
                self._filtered_rows
            ):
                self._set_state(id_to_follow=self._filtered_rows[self.value][1][0])

        # validate the selected row
        if (
            self._state["selected_row"] >= len(self._filtered_rows)
            and len(self._filtered_rows) != 0
        ):
            self.value = len(self._filtered_rows) - 1

        # first, print the header
        if self.header_enabled:
            offset = -self._horizontal_offset
            for col in self.columns:
                if col.header_name == self._config["sort_column"]:
                    color, attr, background = self._frame.palette.get(
                        "table_header_selected",
                        self._frame.palette["selected_focus_field"],
                    )
                    arrow = "↑" if self._config["sort_ascending"] else "↓"
                else:
                    color, attr, background = self._frame.palette.get(
                        "table_header", self._frame.palette["title"]
                    )
                    arrow = ""
                width = col.max_width
                if width == 0:
                    width = max(self._w - offset, 1)

                assert width > 0

                if col.enabled:
                    self._frame.canvas.paint(
                        f"{col.header_name+arrow:{col.align}{width}} ",
                        self._x + offset,
                        self._y,
                        color,
                        attr,
                        background,
                    )
                    offset += width + 1
            y_offset = 1
        else:
            y_offset = 0

        # then, print the rows
        for i in range(self._vertical_offset, self._vertical_offset + self._h - 1):
            if i >= len(self._filtered_rows) or i < 0:
                break
            displayable_row, _ = self._filtered_rows[i]
            x_offset = -self._horizontal_offset
            if self._state["selected_row"] == i:
                color, attr, background = self._frame.palette.get(
                    "table_selected", self._frame.palette["selected_focus_field"]
                )
                has_color = False
            else:
                color, attr, background = self._frame.palette.get(
                    "table", self._frame.palette["focus_field"]
                )
                has_color = True
            for j, col in enumerate(self.columns):
                width = col.max_width
                if col.enabled:
                    if width == 0:
                        width = (
                            self._w
                            - sum(_.max_width + 1 for _ in self.columns if _.enabled)
                            + self._horizontal_offset
                        )
                    line = str(displayable_row[j]).replace("\n", " ")
                    # first, the space needed to pad the text to the correct alignment
                    # is calculated.
                    line = align_with_overflow(line, width, col.align)
                    # then, colors are added if needed.
                    line = ColouredText(line, self._parser) if self._parser else line

                    to_paint = str(line)
                    # finally, the line is painted.
                    self._frame.canvas.paint(
                        to_paint + " ",
                        self._x + x_offset,
                        self._y + y_offset,
                        color,
                        attr,
                        background,
                        colour_map=line.colour_map  # type: ignore
                        if hasattr(line, "colour_map") and has_color
                        else None,
                    )
                    x_offset += width + 1
            y_offset += 1

    def process_event(  # pylint: disable=too-many-return-statements,too-many-branches
        self, event
    ):
        if isinstance(event, KeyboardEvent):
            if event.key_code == Screen.KEY_UP:
                self.value = max(0, self._state["selected_row"] - 1)
                return None
            if event.key_code == Screen.KEY_DOWN:
                self.value = min(
                    len(self._filtered_rows) - 1, self._state["selected_row"] + 1
                )
                return None
            if event.key_code == Screen.KEY_LEFT:
                self._horizontal_offset = max(0, self._horizontal_offset - 1)
                return None
            if event.key_code == Screen.KEY_RIGHT:
                self._horizontal_offset += 1
                return None
            if event.key_code == 337:
                self.value = max(0, self._state["selected_row"] - 5)
                return None
            if event.key_code == 336:
                self.value = min(
                    len(self._filtered_rows) - 1, self._state["selected_row"] + 5
                )
                return None
            if event.key_code == 393:
                self._horizontal_offset = max(0, self._horizontal_offset - 5)
                return None
            if event.key_code == 402:
                self._horizontal_offset += 5
                return None
            if event.key_code == Screen.KEY_PAGE_UP:
                self.value = max(0, self._state["selected_row"] - self._h + 1)
                return None
            if event.key_code == Screen.KEY_PAGE_DOWN:
                self.value = min(
                    len(self._filtered_rows) - 1,
                    self._state["selected_row"] + self._h - 1,
                )
                return None
            if event.key_code == Screen.KEY_HOME:
                self.value = 0
                return None
            if event.key_code == Screen.KEY_END:
                self.value = len(self._filtered_rows) - 1
                return None
        if isinstance(event, MouseEvent):  # pylint: disable=too-many-nested-blocks
            if event.buttons & event.LEFT_CLICK != 0:
                this_x, this_y = self.get_location()
                relative_x = event.x - this_x
                relative_y = event.y - this_y
                if relative_x < 0 or relative_x >= self._w:
                    return event
                if relative_y < 0 or relative_y >= self._h:
                    return event
                if relative_y == 0:
                    # this is the header
                    relative_x += self._horizontal_offset
                    for col in self.columns:
                        if not col.enabled:
                            continue
                        if relative_x - col.max_width - 1 < 0 or col.max_width == 0:
                            if self._config["sort_column"] == col.header_name:
                                self._config["sort_ascending"] = not self._config[
                                    "sort_ascending"
                                ]
                            else:
                                self._config["sort_column"] = col.header_name
                            break
                        relative_x -= col.max_width + 1
                else:
                    # select the clicked row
                    self.value = relative_y - 1 + self._vertical_offset
                return None
        return event

    def required_height(self, offset, width):
        return Widget.FILL_FRAME

    def reset(self):
        pass

    def set_rows(
        self, displayable_rows: List[List[str]], sortable_rows: List[List[Any]]
    ) -> None:
        """
        Set the rows for the table. Both the displayable and sortable rows
        must be in the same order and have the same number of columns and rows.

        :param displayable_rows: a list of lists of strings, each representing a row
        :param sortable_rows: a list of lists of sortable data, each representing a row
        """
        assert len(displayable_rows) == len(sortable_rows)
        if len(displayable_rows) != 0:
            assert len(displayable_rows[0]) == len(sortable_rows[0])

        self._rows = list(zip(displayable_rows, sortable_rows))  # type: ignore
        self.do_sort()

    def do_sort(self) -> None:
        """
        Sort the rows according to the configured sort order.
        """

        # if we are displaying a tree, we need to use the tree to sort
        # first, and to modify the command
        if (
            self._config["tree"]
            and self._config["tab"] == "processes"
            and self.tree is not None
        ):
            # we need the columns to have an ID
            assert self.columns[0].header_name == "ID"
            # refactor cached sortable data to be indexed by id
            sortable = {}
            for row in self._rows:
                sortable[row[1][0]] = row

            self._tree_rows = self._sort_level(self.tree, sortable, 0, [])
        else:
            self._rows = self._simple_sort(self._rows)
        self.do_filter()

    def do_filter(self) -> None:
        """
        Filter the rows by the configured value.
        """
        value = self._config["filter"]
        rows = (
            self._tree_rows
            if self._config["tree"]
            and self._config["tab"] == "processes"
            and self._tree_rows is not None
            else self._rows
        )
        if value is None:
            self._filtered_rows = rows
            return

        column_matches, rest = self._parse_filter(value)

        self._filtered_rows = [
            row for row in rows if self._filter_predicate(row, column_matches, rest)
        ]
        if self._state["selected_row"] >= len(self._filtered_rows):
            self.value = 0

    def _filter_predicate(  # pylint: disable=too-many-return-statements
        self, row: InternalRow, column_matches: List[str], rest: str
    ) -> bool:
        # filter by specific columns
        for column_match in column_matches:
            try:
                index = [_.header_name.lower() for _ in self.columns].index(
                    column_match[0].lower()
                )
                if index >= len(row[0]):
                    return False
                # handle numerical comparisons
                if column_match[1][0] in {"<", ">"}:
                    if row[1][index] is None:
                        return False
                    if column_match[1][0] == "<":
                        if row[1][index] >= float(column_match[1][1:]):
                            return False
                    elif row[1][index] <= float(column_match[1][1:]):
                        return False
                # handle nots
                elif column_match[1][0] == "!" and column_match[1][1:] in str(
                    row[0][index]
                ):
                    return False
                # handle case with no operator
                elif (column_match[1][0] != "!") and not column_match[1] in str(
                    row[0][index]
                ):
                    return False
            except ValueError:
                pass

        # match the rest against the entire visible row
        combined = " ".join(
            [str(v) for i, v in enumerate(row[0]) if self.columns[i].enabled]
        )

        if len(rest) > 0 and rest[0] == "!":
            return rest[1:] not in combined

        return rest in combined

    def _parse_filter(self, value: str) -> Tuple[List[str], str]:
        """
        Parse a filter string into a list of tuples of the form (column, value).
        """
        column_matches = []
        match_regex = re.compile(r"\s*(\S+): ?(\S+)( +|$)")
        match = re.match(match_regex, value)
        while match:
            column_matches.append((match.group(1), match.group(2)))
            value = value[match.end() :]
            match = re.match(match_regex, value)
        return column_matches, value.strip()

    def fix_vert_offset(self):
        """Fix the vertical offset to keep the selected row
        within the range of the table."""
        if self._h == 0:
            # the screen is resizing, so don't do anything
            self._vertical_offset = 0
            return
        if self._state["selected_row"] < self._vertical_offset:
            self._vertical_offset = self._state["selected_row"]
        if self._state["selected_row"] >= self._vertical_offset + self._h - 1:
            self._vertical_offset = self._state["selected_row"] - self._h + 2

    def find(self, search: str) -> bool:
        """Finds the first row that contains the given search string."""
        column_matches, rest = self._parse_filter(search)
        for i, row in enumerate(self._filtered_rows):
            if self._filter_predicate(row, column_matches, rest):
                self.value = i
                return True
        return False

    def get_selected(self) -> Optional[InternalRow]:
        """Returns the selected row"""
        if (
            self._state["selected_row"] >= len(self._filtered_rows)
            or self._state["selected_row"] < 0
        ):
            return None
        return self._filtered_rows[self._state["selected_row"]]

    def _sort_level(
        self,
        tree: Dict[str, Any],
        rows: Dict[str, Tuple],
        depth: int,
        parents_end: List[bool],
    ) -> List[InternalRow]:
        """Sort a level of the tree, appending sorted versions
        of the children underneath each row."""
        level = []

        # construct a list of all the children of this level
        for rec_id, branch in tree.items():
            if rec_id not in rows:
                # this process is excluded, so don't include it in the tree
                continue
            row = rows[rec_id]
            level.append(row)

        # sort this level
        level = self._simple_sort(level)

        # recursively build the final rows
        sorted_rows = []
        for i, row in enumerate(level):
            branch = tree[row[1][0]]
            new_displayable = list(row[0])
            prefix = self._make_tree_prefix(
                depth,
                branch is None
                or branch[0]
                or len([x for x in branch[1].keys() if x in rows]) == 0,
                i == len(level) - 1,
                parents_end,
            )
            if isinstance(new_displayable[-1], ColouredText):
                new_displayable[-1] = ColouredText(
                    prefix + new_displayable[-1].raw_text, self._parser  # type: ignore
                )
            else:
                new_displayable[-1] = prefix + new_displayable[-1]
            sorted_rows.append((new_displayable, row[1]))
            if branch is not None and branch[0]:
                sorted_rows.extend(
                    self._sort_level(
                        branch[1],
                        rows,
                        depth + 1,
                        parents_end + [i == len(level) - 1],
                    )
                )

        return sorted_rows

    def _simple_sort(self, rows: List[InternalRow]) -> List[InternalRow]:
        """Sort a list of rows by a key, putting all Nones at the end."""
        if len(rows) == 0:
            return []
        key = self._config["sort_column"]
        ascending = self._config["sort_ascending"]
        # sort by PID by default
        col_names = [_.header_name for _ in self.columns]
        if "PID" in col_names:
            pid_index = col_names.index("PID")
            rows.sort(key=lambda x: x[1][pid_index])

        if key is None or key not in col_names:
            return rows

        index = col_names.index(key)

        if self.columns[index].value_type is dict:
            return rows

        def key_func(val):
            return val[1][index]

        none_vals = [n for n in rows if key_func(n) is None]
        non_none = [n for n in rows if key_func(n) is not None]
        non_none.sort(key=key_func, reverse=not ascending)
        return non_none + none_vals

    @staticmethod
    def _make_tree_prefix(
        depth: int, not_expandable: bool, end: bool, parents_end: List[bool]
    ) -> str:
        """Constructs a prefix for the row showing the tree structure"""
        if depth == 0:
            return ""
        return (
            "".join(["   " if b else "│  " for b in parents_end[1:]])
            + ("├" if not end else "└")
            + ("─" if not_expandable else "+")
            + " "
        )

    @property
    def value(self) -> int:
        """The selected row"""
        return self._state["selected_row"]

    @value.setter
    def value(self, value: int):
        if len(self._filtered_rows) == 0:
            return
        value = max(value, 0)
        if value >= len(self._filtered_rows):
            value = len(self._filtered_rows) - 1
        self._set_state(selected_row=value)
        self._set_state(id_to_follow=self._filtered_rows[value][1][0])
        self.fix_vert_offset()
