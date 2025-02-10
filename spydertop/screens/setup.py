#
# setup.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
The setup frame, containing controls for the settings
contained in Spydertop.
"""

# Contents:
#
#     Column selection
#         Each tab
#             enable/disable all of the columns in [TAB]_COLUMNS
#     Meter selection
#         Enable/disable the meters that are available
#         (This is currently disabled)
#     Settings
#         Everything in config.settings (that fits)
#         Color scheme

from typing import Callable, List, Optional
from asciimatics.screen import Screen
from asciimatics.widgets import (
    Frame,
    Layout,
    ListBox,
    Text,
)
from asciimatics.event import KeyboardEvent, MouseEvent

from spydertop.constants.columns import (
    CONTAINER_COLUMNS,
    PROCESS_COLUMNS,
    FLAG_COLUMNS,
    SESSION_COLUMNS,
    CONNECTION_COLUMNS,
    LISTENING_SOCKET_COLUMNS,
    Column,
)
from spydertop.model import AppModel
from spydertop.utils import is_event_in_widget
from spydertop.widgets.form import value_to_widget

# the following are a set of functions that are used to fill in the options
# some of these are only necessary due to python's lambda behavior


def change_columns(columns: List[Column], name):
    """Create a lambda to enable/disable a column"""

    def inner(enabled, model):
        for col in columns:
            if col.header_name == name:
                model.columns_changed = True
                col.enabled = enabled
                return

    return inner


def set_setting(name):
    """Create a lambda to set a config value in the settings"""

    if name == "play_speed":

        def set_play(val, model: AppModel):
            if val != 0.0:
                setattr(model.settings, name, val)

        return set_play

    def inner(val, model: AppModel):
        setattr(model.settings, name, val)

    return inner


def set_state(name):
    """Create a lambda to set a config value in the state"""

    def inner(val, model: AppModel):
        setattr(model.state, name, val)

    return inner


def get_enabled(columns: List[Column], index: int):
    """Get the enabled status of a column"""
    return lambda _: columns[index].enabled


# the options dict is structured the same way
# as the ui would be, where the key(s) is the name of the option
# in the list box, and the value is a tuple of:
#     name: the name of the option
#     values: a tuple of (possible values, default value lambda)
#     change_func: a function that takes the value and the model

OPTIONS = {
    "Columns": {
        "Processes": [
            (
                col.header_name,
                (col.enabled, get_enabled(PROCESS_COLUMNS, i)),
                change_columns(PROCESS_COLUMNS, col.header_name),
            )
            for i, col in enumerate(PROCESS_COLUMNS)
        ],
        "Flags": [
            (
                col.header_name,
                (col.enabled, get_enabled(FLAG_COLUMNS, i)),
                change_columns(FLAG_COLUMNS, col.header_name),
            )
            for i, col in enumerate(FLAG_COLUMNS)
        ],
        "Sessions": [
            (
                col.header_name,
                (col.enabled, get_enabled(SESSION_COLUMNS, i)),
                change_columns(SESSION_COLUMNS, col.header_name),
            )
            for i, col in enumerate(SESSION_COLUMNS)
        ],
        "Connections": [
            (
                col.header_name,
                (col.enabled, get_enabled(CONNECTION_COLUMNS, i)),
                change_columns(CONNECTION_COLUMNS, col.header_name),
            )
            for i, col in enumerate(CONNECTION_COLUMNS)
        ],
        "Listening": [
            (
                col.header_name,
                (col.enabled, get_enabled(LISTENING_SOCKET_COLUMNS, i)),
                change_columns(LISTENING_SOCKET_COLUMNS, col.header_name),
            )
            for i, col in enumerate(LISTENING_SOCKET_COLUMNS)
        ],
        "Containers": [
            (
                col.header_name,
                (col.enabled, get_enabled(CONTAINER_COLUMNS, i)),
                change_columns(CONTAINER_COLUMNS, col.header_name),
            )
            for i, col in enumerate(CONTAINER_COLUMNS)
        ],
    },
    # there is currently no mechanism to enable/disable meters
    # "Meters": {"Column 1": [], "Column 2": []},
    "Other": {
        "Settings": [
            (
                "Hide Threads",
                (True, lambda model: model.settings.hide_threads),
                set_setting("hide_threads"),
            ),
            (
                "Hide Kernel Threads",
                (True, lambda model: model.settings.hide_kthreads),
                set_setting("hide_kthreads"),
            ),
            (
                "Sort Ascending",
                (True, lambda model: model.state.sort_ascending),
                set_state("sort_ascending"),
            ),
            (
                "Cursor Follows Record",
                (False, lambda model: model.settings.follow_record),
                set_setting("follow_record"),
            ),
            (
                "Use UTC Time",
                (False, lambda model: model.settings.utc_time),
                set_setting("utc_time"),
            ),
            (
                "Play",
                (False, lambda model: model.state.play),
                set_state("play"),
            ),
            (
                "Play Speed",
                (1.0, lambda model: model.settings.play_speed),
                set_setting("play_speed"),
            ),
            (
                "Tree",
                (False, lambda model: model.settings.tree),
                set_setting("tree"),
            ),
            (
                "Collapse All",
                (False, lambda model: model.settings.collapse_tree),
                set_setting("collapse_tree"),
            ),
            (
                "Filter",
                ("", lambda model: model.state.filter),
                set_state("filter"),
            ),
            (
                "Default Loading Duration (min)",
                (15, lambda model: model.settings.default_duration_minutes),
                set_setting("default_duration_minutes"),
            ),
        ],
        "Colors": [
            (
                "Select Color Scheme:",
                (
                    {"htop", "spyderbat", "monochrome", "green", "bright", "tlj256"},
                    lambda model: model.settings.theme,
                ),
                set_setting("theme"),
            ),
        ],
    },
}


class SetupFrame(Frame):
    """The setup frame, containing a form to select the behavior of the tool.
    This frame is displayed as a modal on top of the main frame."""

    _model: AppModel
    _disable_change: bool
    _layout: Layout
    _main_column: ListBox
    _second_column: ListBox
    _has_textbox: bool = False
    _on_death: Optional[Callable]

    def __init__(
        self, screen: Screen, model: AppModel, on_death: Optional[Callable] = None
    ) -> None:
        super().__init__(
            screen,
            max(screen.height // 2, 25),
            max(screen.width // 2, 50),
            title="Setup",
            reduce_cpu=True,
            is_modal=True,
        )

        self._model = model
        self._disable_change = False
        self._layout = Layout([1, 1, 3])
        self._on_death = on_death
        self.add_layout(self._layout)

        ## build widgets
        self._main_column = ListBox(
            10,
            [(x, x) for x in OPTIONS],
            name="setup main column",
            add_scroll_bar=True,
            on_change=self._on_change,
        )

        self._second_column = ListBox(
            10,
            [(x, x) for x in OPTIONS["Columns"]],
            name="setup secondary column",
            add_scroll_bar=True,
            on_change=self._on_change,
        )

        self._main_column.value = "Columns"

        self.set_theme(self._model.settings.theme)

        self.rebuild()

    def process_event(self, event):
        assert self.scene is not None
        if isinstance(event, KeyboardEvent):
            if (
                event.key_code == Screen.KEY_ESCAPE
                or event.key_code == Screen.KEY_F10
                or (event.key_code in {ord("q"), ord("Q")} and not self._has_textbox)
            ):
                self.scene.remove_effect(self)
                if self._on_death is not None:
                    self._on_death()
        elif isinstance(event, MouseEvent):
            if is_event_in_widget(event, self) and (event.buttons != 0):
                # when a click is outside the modal, close it
                self.scene.remove_effect(self)
                if self._on_death is not None:
                    self._on_death()

        super().process_event(event)
        if self._model.settings.theme != self._theme:
            self.set_theme(self._model.settings.theme)

    def make_widget(self, row):
        """Construct a widget for the given row based on its type."""
        label, values, on_change = row
        default_getter = None

        # unpack the values tuple if there is a default getter
        if isinstance(values, tuple):
            values, default_getter = values

        widget = value_to_widget(
            label, values, lambda _, val: on_change(val, self._model)
        )
        if isinstance(widget, Text):
            self._has_textbox = True
        if default_getter:
            if isinstance(widget, Text):
                widget.value = str(default_getter(self._model))
            else:
                widget.value = default_getter(self._model) # type: ignore

        return widget

    # The only way to remove and re-add widgets in Asciimatics is to use
    # Layout.clear_widgets(). Therefore, we need to be able to easily rebuild the entire
    # UI on each selection change

    # the idea is to build all of the widgets based off of the OPTIONS dict
    # and then render them by clearing and re-adding dynamically when the
    # selection changes

    def rebuild(self):
        """Rebuild the UI based off of the current selection."""
        # prevent recursing (through another on_change call) when changing things
        self._disable_change = True
        self._has_textbox = False

        second_col_selected = self._layout.get_current_widget() == self._second_column

        # First Column
        self._layout.clear_widgets()
        self._layout.add_widget(self._main_column, 0)

        selected_col = str(self._main_column.value)

        # second Column
        self._second_column.options = (
            [(x, x) for x in OPTIONS[selected_col].keys()]
            if isinstance(OPTIONS[selected_col], dict)
            else []
        )
        self._layout.add_widget(self._second_column, 1)

        # Main view
        widgets = OPTIONS[selected_col]
        if isinstance(widgets, dict):
            widgets = widgets[self._second_column.value]
        for widget in widgets:
            self._layout.add_widget(self.make_widget(widget), 2)

        self.fix()

        # select the same column as before the rebuild
        if second_col_selected:
            self._layout.focus(force_column=1, force_widget=0)
            self._main_column.blur()
        else:
            self._layout.focus(force_column=0, force_widget=0)
            self._second_column.blur()

        self._disable_change = False

    def _on_change(self):
        if not self._disable_change:
            self.rebuild()
