#
# main.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc.  All rights reserved.
#

"""
The main frame for the tool. This frame contains the record list and usage metrics,
as well as showing all the menu buttons.
"""

import re
import textwrap
from typing import Any, Dict, List, Tuple, Union

from asciimatics.screen import Screen
from asciimatics.widgets import (
    Frame,
    Layout,
    Widget,
    MultiColumnListBox,
    Button,
    ListBox,
)
from asciimatics.exceptions import NextScene, StopApplication
from asciimatics.event import KeyboardEvent
from asciimatics.parsers import AsciimaticsParser

from spydertop.model import AppModel
from spydertop.screens.setup import SetupFrame
from spydertop.screens.meters import (
    get_memory,
    get_swap,
    show_disk_io,
    show_ld_avg,
    show_network,
    show_tasks,
    update_cpu,
    show_uptime,
)
from spydertop.screens.modals import InputModal, NotificationModal
from spydertop.utils import COLOR_REGEX, log, convert_to_seconds, pretty_time
from spydertop.columns import (
    PROCESS_COLUMNS,
    SESSION_COLUMNS,
    CONNECTION_COLUMNS,
    FLAG_COLUMNS,
    LISTENING_SOCKET_COLUMNS,
)
from spydertop.widgets import FuncLabel, Meter, Padding
from spydertop.screens.footer import Footer


class MainFrame(Frame):
    # update and caching management
    _model: AppModel
    _old_settings: Dict[str, Any]
    _last_frame: int = 0
    _widgets_initialized = False
    needs_screen_refresh = True
    needs_update = True
    needs_recalculate = True
    _cached_options = None
    _cached_sortable = None
    _cached_displayable = None
    _current_columns = PROCESS_COLUMNS
    _old_column_val = None
    _last_effects: int = 1

    # widgets
    _main = None
    _cpus = []
    _tabs = []
    _memory = None
    _swap = None
    _columns = None

    # -- initialization -- #
    def __init__(self, screen, model: AppModel) -> None:
        initial_data = {
            "tab": "processes",
            "column_offset": 0,
        }
        super().__init__(
            screen,
            screen.height,
            screen.width,
            has_border=False,
            can_scroll=False,
            data=initial_data,
            name="MainFrame",
        )
        self._model = model
        self._old_settings = model.config.settings

        self.set_theme(model.config["theme"])

    def _init_widgets(self):
        ############## Header #################
        header = Layout([1, 1], fill_frame=False)
        self.add_layout(header)
        header.add_widget(Padding(), 0)
        header.add_widget(Padding(), 1)

        # meters
        self._cpus = []
        cpu_count = len(self._model.get_value("cpu_time").keys()) - 1
        for i in range(0, cpu_count):
            self._cpus.append(
                Meter(
                    f"{i:<3}",
                    values=[0, 0, 0, 0],
                    colors=[
                        Screen.COLOUR_BLUE,
                        Screen.COLOUR_GREEN,
                        Screen.COLOUR_RED,
                        Screen.COLOUR_CYAN,
                    ],
                    total=1,
                    percent=True,
                    important_value=3,
                )
            )
            if i < cpu_count / 2:
                column = 0
            else:
                column = 1
            header.add_widget(self._cpus[i], column)
        self._memory = Meter(
            "Mem",
            values=[0, 0, 0, 0],
            colors=[
                Screen.COLOUR_GREEN,
                Screen.COLOUR_BLUE,
                Screen.COLOUR_MAGENTA,
                Screen.COLOUR_YELLOW,
            ],
            total=1024 * 1024,
            important_value=0,
        )
        header.add_widget(self._memory)
        self._swap = Meter(
            "Swp",
            values=[0, 0],
            colors=[
                Screen.COLOUR_RED,
                Screen.COLOUR_YELLOW,
            ],
            total=0,
            important_value=0,
        )
        header.add_widget(self._swap)

        # dynamic labels
        header.add_widget(
            FuncLabel(lambda: show_disk_io(self._model), parser=AsciimaticsParser()),
            column=0,
        )
        header.add_widget(
            FuncLabel(lambda: show_network(self._model), parser=AsciimaticsParser()),
            column=0,
        )

        header.add_widget(
            FuncLabel(lambda: show_tasks(self._model), parser=AsciimaticsParser()),
            column=1,
        )
        header.add_widget(
            FuncLabel(lambda: show_ld_avg(self._model), parser=AsciimaticsParser()),
            column=1,
        )
        header.add_widget(
            FuncLabel(lambda: show_uptime(self._model), parser=AsciimaticsParser()),
            column=1,
        )

        header.add_widget(Padding(), 0)
        header.add_widget(Padding(), 1)

        ################# Main Table Tabs #######################
        tabs_layout = Layout(self.calculate_widths([1] * 5))
        self._tabs = []
        self.add_layout(tabs_layout)
        for i, name in enumerate(
            ["Processes", "Flags", "Sessions", "Connections", "Listening"]
        ):

            def wrapper(name):
                def inner():
                    self._switch_to_tab(name.lower())

                return inner

            button = Button(name, wrapper(name), add_box=False)
            self._tabs.append(button)
            tabs_layout.add_widget(button, i)

        ################# Main Table #######################
        self._main = Layout([1], fill_frame=True)
        self.add_layout(self._main)

        self._columns = MultiColumnListBox(
            Widget.FILL_FRAME,
            [],
            [],
            titles=[],
            name="records_table",
            parser=AsciimaticsParser(),
        )
        self._main.add_widget(self._columns)

        ################# Footer #######################

        status = FuncLabel(
            lambda: f"{self._model.state}",
            align=">",
            parser=AsciimaticsParser(),
            color="focus_button",
        )
        self._footer = Footer(self.calculate_widths([1] * 10 + [3]), self, [], status)
        self.add_layout(self._footer)
        self._switch_buttons("main")

        self.reset()
        self.fix()
        self._switch_to_tab(self.data["tab"])
        self.switch_focus(self._main, 0, 0)
        self._widgets_initialized = True

    # -- overrides -- #
    def update(self, frame_no):
        conf = self._model.config

        # if model is in failure state, raise next scene
        if self._model.failed:
            raise NextScene("Failure")
        # early exit if model is not ready
        if not self._model.loaded:
            return
        elif not self._widgets_initialized:
            self._init_widgets()

        # update model (if needed, at most 4 times per second)
        if conf["play"] and (frame_no % max(int(20 / conf["play_speed"]), 5) == 0):
            if self._last_frame != 0:
                frames_delta = frame_no - self._last_frame
                time_delta = frames_delta / 20
                self._model.timestamp += time_delta * conf["play_speed"]
                self.needs_recalculate = True
            self._last_frame = frame_no

        # detect changes in settings
        if conf.settings_changed:
            conf.settings_changed = False
            self.needs_update = True
            if conf["theme"] != self._old_settings["theme"]:
                self.set_theme(conf["theme"])
                # update theme colors in tabs
                for button in self._tabs:
                    if "tab" in self.palette:
                        button.custom_colour = (
                            "selected_tab"
                            if self.data["tab"] == button.text.lower()
                            else "tab"
                        )
                    else:
                        button.custom_colour = (
                            "selected_focus_field"
                            if self.data["tab"] == button.text.lower()
                            else "focus_field"
                        )
                self.needs_screen_refresh = True

            if conf["play"] != self._old_settings["play"]:
                self._footer.change_button_text(
                    8, "Play" if not self._model.config["play"] else "Pause"
                )
                self.fix()
                self.needs_screen_refresh = True
            if (
                conf["hide_threads"] != self._old_settings["hide_threads"]
                or conf["hide_kthreads"] != self._old_settings["hide_kthreads"]
            ) and self.data["tab"] == "processes":
                self.needs_recalculate = True
            self._old_settings = self._model.config.settings.copy()
        if self._model.columns_changed:
            self._model.columns_changed = False
            self.needs_update = True

        # detect changes in effects (opened/closed)
        if len(self._scene.effects) != self._last_effects:
            self._last_effects = len(self._scene.effects)
            self.needs_screen_refresh = True

        try:
            # work up the caching system, updating each part of the cache
            # only if necessary
            if self.needs_recalculate:
                self._build_options()
                self.needs_recalculate = False
                self.needs_update = True

            if self.needs_update:
                self._build_displayable()
                self.needs_update = False
                self.needs_screen_refresh = True

            # update screen if needed
            if self.needs_screen_refresh:
                self._update_columns()

                # update header
                for (i, cpu) in enumerate(self._cpus):
                    cpu.values = update_cpu(i, self._model)
                (total, values) = get_memory(self._model)
                self._memory.total = total
                self._memory.values = values
                (total, values) = get_swap(self._model)
                self._swap.total = total
                self._swap.values = values

                self.needs_screen_refresh = False
                return super().update(frame_no)
        except Exception as e:
            self._model.fail("An error occurred while updating the screen.")
            log.traceback(e)
            raise NextScene("Failure")

    def reset(self):
        # log.info("Resetting MainFrame, data is being saved")
        if self._main is not None:
            self.switch_focus(self._main, 0, 0)
        self._initial_data = self.data
        return super().reset()

    def process_event(self, event):
        self.needs_screen_refresh = True
        # Do the key handling for this Frame.
        KEYMAP = {
            "q": self._quit,
            "Q": self._quit,
            "[": lambda: self._shift_time(-1.0),
            "]": lambda: self._shift_time(1.0),
            "{": lambda: self._shift_time(-60.0),
            "}": lambda: self._shift_time(60.0),
            "\\": self._show_filter,
            "/": self._show_search,
            ".": self._show_sort_menu,
            ">": self._show_sort_menu,
            "h": self._help,
            "?": self._help,
            "p": lambda: self._switch_to_tab("processes"),
            "f": lambda: self._switch_to_tab("flags"),
            "s": lambda: self._switch_to_tab("sessions"),
            "c": lambda: self._switch_to_tab("connections"),
            "l": lambda: self._switch_to_tab("listening"),
            " ": self._play,
            "C": self._show_setup,
            "S": self._show_setup,
            "H": lambda: self._config("hide_threads"),
            "K": lambda: self._config("hide_kthreads"),
            "I": lambda: self._config("sort_ascending"),
            "t": lambda: self._config("tree"),
            "*": lambda: self._config("collapse_tree"),
            "-": self._enable_disable,
            "=": self._enable_disable,
            "+": self._enable_disable,
            "\n": self._show_details,
        }
        CTRLKEYMAP = {
            # some keys are not valid here due to limitations
            # with key events in the console. Try to only
            # use lower case letters.
        }
        if isinstance(event, KeyboardEvent):
            if event.key_code in {ord(k) for k in KEYMAP.keys()}:
                KEYMAP[chr(event.key_code)]()
                return
            for k in CTRLKEYMAP.keys():
                if event.key_code == Screen.ctrl(k):
                    CTRLKEYMAP[k]()
                    return
            if event.key_code in range(Screen.KEY_F11, Screen.KEY_F1 + 1):
                self._footer.click(-event.key_code - 2)
            if event.key_code == Screen.KEY_RIGHT:
                self._shift_columns(1)
                return
            if event.key_code == Screen.KEY_LEFT:
                self._shift_columns(-1)
                return
            if (
                event.key_code == Screen.KEY_TAB
                or event.key_code == Screen.KEY_BACK_TAB
            ):
                current_tab_index = 0
                for i, tab in enumerate(self._tabs):
                    if tab.text.lower() == self.data["tab"]:
                        current_tab_index = i
                        break
                offset = 1 if event.key_code == Screen.KEY_TAB else -1
                next_tab = self._tabs[
                    (current_tab_index + offset) % len(self._tabs)
                ].text.lower()
                self._switch_to_tab(next_tab)
                return

        # if no widget is focused, focus the table   widget
        try:
            self._layouts[self._focus].focus()
        except IndexError:
            self.switch_focus(self._main, 0, 0)
        # Now pass on to lower levels for normal handling of the event.
        return super().process_event(event)

    # -- update handling -- #
    def _update_columns(self):
        """Update the columns in the multi-column list box widget."""
        columns_to_use = [c for c in self._current_columns if c[5]][
            self.data["column_offset"] :
        ]

        # these are changed manually because the functionality
        # necessary is not available in MultiColumnListBox
        arrow = "↑" if self._model.config["sort_ascending"] else "↓"
        self._columns._titles = [
            v[0] if v[0] != self._model.config["sort_column"] else f"|{v[0]}{arrow}|"
            for v in columns_to_use
        ]
        self._columns._align = [v[2] for v in columns_to_use]
        self._columns._columns = [
            v[3] if v[0] != self._model.config["sort_column"] or v[3] == 0 else v[3] + 3
            for v in columns_to_use
        ]
        self._columns._spacing = [0] + [1] * (len(columns_to_use) - 1)

        # shallow copy of the data to avoid modifying the cache
        options = [_ for _ in self._cached_displayable]

        # remove color from the selected item
        if self._columns.value is not None and len(options) > 0:

            if self._columns.value >= len(options):
                self._columns.value = 0
            try:
                options[self._columns.value] = [
                    re.sub(COLOR_REGEX, "", val) for val in options[self._columns.value]
                ]
            except IndexError as e:
                log.err("Index error while updating columns")
                log.traceback(e)

        self._columns.options = [(v, i) for i, v in enumerate(options)]

    def _build_displayable(self):
        """Constructs the displayable data for the records list using cached data."""
        self._cached_displayable = []
        sorted_rows = self._get_sorted_rows()

        for row in sorted_rows:
            # filter out rows that don't match the filter
            if (
                self._model.config["filter"]
                and self._model.config["filter"] not in row[-1]
            ):
                continue
            # only use enabled rows which are not hidden due to offset
            try:
                row = [row[i] for i, c in enumerate(self._current_columns) if c[5]][
                    self.data["column_offset"] :
                ]
            except IndexError as e:
                # FIXME: this should not be possible
                log.err(f"Row was {row}, columns were {self._current_columns}")
                log.traceback(e)
                raise e
            self._cached_displayable.append(row)

    def _build_options(self):
        """Build the options for the records table, depending on the current tab."""
        try:
            if self.data["tab"] == "processes":
                self._cached_sortable = self._build_process_options()

            if self.data["tab"] == "sessions":
                self._cached_sortable = self._build_other_options(self._model.sessions)

            if self.data["tab"] == "flags":
                self._cached_sortable = self._build_other_options(self._model.flags)

            if self.data["tab"] == "connections":
                self._cached_sortable = self._build_other_options(
                    self._model.connections
                )

            if self.data["tab"] == "listening":
                self._cached_sortable = self._build_other_options(self._model.listening)

            self._columns_fresh = True
        except Exception as e:
            self._model.fail("An error occurred while updating the records table")
            log.traceback(e)

    def _build_other_options(self, records: Dict[str, Any]) -> Tuple[List, List]:
        """Builds options for records other than the processes tab, using
        the current columns"""
        # rows = []
        sortable_rows = []

        for record in records.values():
            # determine if the record is visible for this time
            if "valid_from" in record:
                if record["valid_from"] > self._model.timestamp:
                    continue
                end_time = (
                    record["valid_from"] + record["duration"]
                    if "duration" in record
                    else record["valid_to"]
                    if "valid_to" in record
                    else None
                )
                if (
                    end_time
                    and end_time < self._model.timestamp - self._model.time_elapsed
                ):
                    continue
            elif "time" in record:
                # show all events only after they occur
                if self._model.timestamp < record["time"]:
                    continue
            # build the row for options
            cells = []
            sortable_cells = {}
            for col in self._current_columns:
                label = col[0]
                try:
                    sort_val = col[4](self._model, record)
                    cells.append(str(col[1](self._model, record)))
                    sortable_cells[label] = sort_val
                except Exception as e:
                    # If there is an issue, use an empty values
                    log.warn(
                        f"Error when building other options in column {label}, row {len(rows)}"
                    )
                    log.traceback(e)
                    sortable_cells[label] = None
                    cells.append("")

            sortable_cells["displayable"] = cells
            sortable_rows.append(sortable_cells)

        return sortable_rows

    def _build_process_options(
        self,
    ) -> Tuple[List, List]:
        """Build options for the processes tab. This requires more work than
        the other tabs, because the data is not in a single record; the
        event_top data is also required to be bundled in"""
        model_processes = self._model.processes
        previous_et_processes, event_top_processes = self._model.get_top_processes()
        defaults = event_top_processes["default"]

        rows = []
        sortable_rows = []

        # loop through the process records, and fill in the event_top data
        # if it is available
        for process in model_processes.values():
            # determine if the record is visible in this time period
            if process["valid_from"] > self._model.timestamp:
                continue
            end_time = (
                process["valid_to"]
                if "valid_to" in process
                else process["valid_from"] + process["duration"]
                if "duration" in process
                else None
            )
            if end_time and end_time < self._model.timestamp - self._model.time_elapsed:
                continue

            # ignore if the process is hidden
            if (
                self._model.config["hide_kthreads"]
                and process["type"] == "kernel thread"
            ):
                continue
            if self._model.config["hide_threads"] and process["type"] == "thread":
                continue

            pid = str(process["pid"])

            # if the process is a thread, it may not have a value in the event_top processes
            if pid in event_top_processes and pid in previous_et_processes:
                et_process = event_top_processes[pid]
                prev_et_process = previous_et_processes[pid]
            else:
                et_process = None
                prev_et_process = None

            # build the row for options
            cells = []
            sortable_cells = {}
            for col in self._current_columns:
                label = col[0]
                try:
                    # expand the event_top data with defaults
                    if et_process is not None:
                        full = defaults.copy()
                        full.update(et_process)

                        prev_full = defaults.copy()
                        prev_full.update(prev_et_process)
                    else:
                        full = None
                        prev_full = None

                    # call the column functions with the full data
                    sort_val = col[4](self._model, prev_full, full, process)
                    cell_val = col[1](self._model, prev_full, full, process)
                    if cell_val is None:
                        cell_val = ""
                    cells.append(str(cell_val))
                    sortable_cells[label] = sort_val
                except Exception as e:
                    # if there is a problem, just use an empty value
                    log.warn(
                        f"Error when building process options in column {label}, row {len(rows)}"
                    )
                    log.traceback(e)
                    sortable_cells[label] = None
                    cells.append("")

            sortable_cells["displayable"] = cells
            sortable_rows.append(sortable_cells)

        return sortable_rows

    # -- input handling -- #
    def _enable_disable(self):
        """find the currently selected row and enable/disable that
        branch in the model.tree"""
        if self.data["tab"] != "processes":
            return
        row_index = self._columns.value
        sorted_rows = self._get_sorted_rows(True)
        row = sorted_rows[row_index]

        def recursive_enable_disable(tree, id_to_ed):
            for id, branch in tree.items():
                if branch is None:
                    continue
                if id == id_to_ed:
                    tree[id] = (not branch[0], branch[1])
                    return
                else:
                    recursive_enable_disable(branch[1], id_to_ed)

        recursive_enable_disable(self._model.tree, row["ID"])
        self.needs_update = True

    def _switch_buttons(self, version):
        """Switch the footer buttons to the given version"""
        MAIN = [
            ("Help", self._help),
            ("Setup", self._show_setup),
            ("Search", lambda: self._show_search()),
            ("Filter", lambda: self._show_filter()),
            ("Tree", lambda: self._config("tree")),
            ("SortBy", lambda: self._show_sort_menu()),
            ("Time", lambda: self._switch_buttons("time")),
            ("", lambda: None),
            ("Play", self._play),
            ("Quit", self._quit),
        ]

        # relative time picker
        TIME_SELECTION = [
            ("-1 hour", lambda: self._shift_time(-3600.0)),
            ("-15 minutes", lambda: self._shift_time(-60.0 * 15)),
            ("-1 minute", lambda: self._shift_time(-60.0)),
            ("-15 seconds", lambda: self._shift_time(-15.0)),
            ("+15 seconds", lambda: self._shift_time(15.0)),
            ("+1 minute", lambda: self._shift_time(60.0)),
            ("+15 minutes", lambda: self._shift_time(60.0 * 15)),
            ("+1 hour", lambda: self._shift_time(3600.0)),
            ("Custom", lambda: self._show_time_entry()),
            ("Done", lambda: self._switch_buttons("main")),
        ]

        # for when modals are opened
        MODAL = [
            ("", lambda: None),
            ("", lambda: None),
            ("", lambda: None),
            ("", lambda: None),
            ("", lambda: None),
            ("", lambda: None),
            ("", lambda: None),
            ("", lambda: None),
            ("", lambda: None),
            ("Done", lambda: self._switch_buttons("main")),
        ]

        if version == "main":
            self._footer.set_buttons(MAIN)
        elif version == "time":
            self._footer.set_buttons(TIME_SELECTION)
        elif version == "modal":
            self._footer.set_buttons(MODAL)

        self.fix()

    def _switch_to_tab(self, tabname):
        """Switch to the given tab, and update the state accordingly"""
        # update state
        self.data["tab"] = tabname
        self.data["column_offset"] = 0
        self.needs_recalculate = True
        self._model.config["sort_column"] = None
        self._model.config["filter"] = None
        self._cached_options = None
        self._cached_sortable = None

        # update tabs colors
        for button in self._tabs:
            if "tab" in self.palette:
                button.custom_colour = (
                    "selected_tab" if self.data["tab"] == button.text.lower() else "tab"
                )
            else:
                button.custom_colour = (
                    "selected_focus_field"
                    if self.data["tab"] == button.text.lower()
                    else "focus_field"
                )

        # update columns and sort
        if tabname == "processes":
            self._current_columns = PROCESS_COLUMNS
            self._model.config["sort_column"] = "CPU%"
            self._model.config["sort_ascending"] = False

        if tabname == "sessions":
            self._current_columns = SESSION_COLUMNS
            self._model.config["sort_column"] = "I"
            self._model.config["sort_ascending"] = False

        if tabname == "flags":
            self._current_columns = FLAG_COLUMNS
            self._model.config["sort_column"] = "AGE"
            self._model.config["sort_ascending"] = True

        if tabname == "connections":
            self._current_columns = CONNECTION_COLUMNS
            self._model.config["sort_column"] = "DURATION"
            self._model.config["sort_ascending"] = True

        if tabname == "listening":
            self._current_columns = LISTENING_SOCKET_COLUMNS
            self._model.config["sort_column"] = "DURATION"
            self._model.config["sort_ascending"] = True

    def _show_sort_menu(self):
        """show the sort menu"""

        def set_sort(title):
            log.info(f"Switching sort to: {title}")
            self._model.config["sort_column"] = title
            self.needs_update = True

        menu = InputModal(
            self.screen,
            label="Sort By:",
            options=[(row[0], row[0]) for row in self._current_columns],
            on_submit=set_sort,
            widget=ListBox,
            theme=self._model.config["theme"],
            height=len(self._current_columns),
            value=self._model.config["sort_column"],
        )
        self._scene.add_effect(menu)

    def _show_search(self):
        """show the search input modal"""
        self._switch_buttons("modal")

        def run_search(value):
            if not value:
                return
            options = self._columns.options
            self.needs_screen_refresh = True
            for option in options:
                if value in str(option[0][-1]):
                    self._columns.value = option[1]
                    return

        self._scene.add_effect(
            InputModal(
                self.screen,
                label="Search:",
                theme=self._model.config["theme"],
                on_change=run_search,
                on_death=lambda: self._switch_buttons("main"),
            )
        )

    def _show_time_entry(self):
        """Show a modal to enter a time offset"""
        self._switch_buttons("modal")

        def validator(val):
            try:
                convert_to_seconds(val)
                return True
            except:
                return False

        self._scene.add_effect(
            InputModal(
                self.screen,
                label="Custom Time Offset:",
                theme=self._model.config["theme"],
                on_submit=lambda value: self._shift_time(convert_to_seconds(value)),
                validator=validator,
                on_death=lambda: self._switch_buttons("time"),
            )
        )

    def _show_filter(self):
        """Show a filter menu"""
        self._switch_buttons("modal")

        def set_filter(value):
            self._model.config["filter"] = value
            self.needs_update = True

        self._scene.add_effect(
            InputModal(
                self.screen,
                self._model.config["filter"],
                label="Filter:",
                theme=self._model.config["theme"],
                on_change=set_filter,
                on_death=lambda: self._switch_buttons("main"),
            )
        )

    def _show_details(self):
        """Show a modal with details about the selected record"""
        sorted_rows = self._get_sorted_rows()

        label_fg = self.palette["label"][0]
        field_fg = self.palette["field"][0]
        if label_fg == -1:
            label_fg = 7
        if field_fg == -1:
            field_fg = 7

        # convert the sorted rows to a human-readable string
        data_lines = ""
        for (name, value) in zip(
            [c[0] for c in self._current_columns], sorted_rows[self._columns.value]
        ):
            # remove any tree characters
            if name == "Command":
                value = re.sub(r"^(│  )*[├└][─+] ", "", value)
            # wrap the value if it's too long
            if len(value) > self.screen.width / 2:
                color = re.match(COLOR_REGEX, value.strip())
                color = color.group() if color else f"${{{field_fg}}}"
                value = f"\n    {color}".join(
                    textwrap.wrap(value, self.screen.width // 2)
                )
            data_lines += f"${{{label_fg},1}}{name}:${{{field_fg}}} {value}\n"

        data_lines = data_lines.rstrip("\n")

        self._scene.add_effect(
            NotificationModal(
                self.screen,
                data_lines,
                parent=self,
                frames=None,  # don't auto-close
            )
        )

    def _show_setup(self):
        """Show the setup screen"""
        self._scene.add_effect(SetupFrame(self.screen, self._model))

    def _shift_columns(self, offset: int):
        """Shift the columns by the given offset."""
        self.needs_update = True
        self.data["column_offset"] += offset
        if self.data["column_offset"] < 0:
            self.data["column_offset"] = 0
        visible_columns = [a for a in self._current_columns if a[5]]
        if self.data["column_offset"] >= len(visible_columns):
            self.data["column_offset"] = len(visible_columns) - 1

    def _play(self):
        """Update the model to play"""
        self._model.config["play"] = not self._model.config["play"]

    def _shift_time(self, offset: float):
        """Shift the time in Model by a given amount."""
        self._model.timestamp += offset

        # if the offset is large, notify the user
        if abs(offset) > 10:
            direction = "forward" if offset > 0 else "backward"
            self._scene.add_effect(
                NotificationModal(
                    self.screen, f"Moved {pretty_time(abs(offset))} {direction}", self
                )
            )

        # load new data, if necessary
        if not self._model.loaded:
            raise NextScene("Loading")

        self.needs_recalculate = True

    def _config(self, name: str, value=None):
        """Change a config value, and handle any effects"""
        value = value or not self._model.config[name]
        self._model.config[name] = value

        if name == "collapse_tree":
            self._model.rebuild_tree()

    # -- miscellaneous -- #
    def calculate_widths(self, desired_columns: List[int]) -> List[int]:
        """Manually calculate the widths for a Layout, as the default has rounding errors."""
        total_width = self.screen.width
        total_desired = sum(desired_columns)
        actual_widths = [int(x / total_desired * total_width) for x in desired_columns]
        actual_widths[-1] += total_width - sum(actual_widths)
        return actual_widths

    def _sort_level(
        self, tree: Dict[str, Any], rows: Dict[str, Tuple], depth: int
    ) -> List[Tuple[Any, int]]:
        """Sort a level of the tree, appending sorted versions
        of the children underneath each row."""
        level = []

        # construct a list of all the children of this level
        for id, branch in tree.items():
            if id not in rows:
                # this process is excluded, so don't include it in the tree
                continue
            row = rows[id]
            level.append((row, branch))

        # sort this level
        level = self.stable_sort(
            level,
            self._model.config["sort_column"],
            self._model.config["sort_ascending"],
        )

        # recursively build the final rows
        sorted_rows = []
        for i, row in enumerate(level):
            branch = row[1]
            new_row = row[0]
            new_row["prefix"] = self._make_tree_prefix(
                depth,
                branch is None
                or branch[0]
                or len([x for x in branch[1].keys() if x in rows]) == 0,
                i == len(level) - 1,
            )
            sorted_rows.append(new_row)
            if branch is not None and branch[0]:
                sorted_rows.extend(self._sort_level(branch[1], rows, depth + 1))

        return sorted_rows

    def _get_sorted_rows(
        self, return_sortable=False
    ) -> Union[List[Tuple[Any, int]], List[Any]]:
        """
        Calculate the sorted values for the records table.
        This is useful when you need to reference the options
        in the order they are displayed on-screen
        """
        if self._cached_sortable is None:
            return []

        # if we are displaying a tree, we need to use the model.tree to sort
        # first, and to modify the command (only for processes).
        if self.data["tab"] == "processes" and self._model.config["tree"]:
            # refactor cached sortable data to be indexed by id
            sortable = {}
            for row in self._cached_sortable:
                sortable[row["ID"]] = row
            tree = self._model.tree
            sorted_raw_values = self._sort_level(tree, sortable, 0)

        else:
            if self._model.config["sort_column"]:
                sorted_raw_values = self.stable_sort(
                    self._cached_sortable,
                    self._model.config["sort_column"],
                    self._model.config["sort_ascending"],
                )

            else:
                # just leave the columns in the order they are in
                sorted_raw_values = self._cached_sortable

        if return_sortable:
            return sorted_raw_values

        sorted_rows = []

        for sort_row in sorted_raw_values:
            row = sort_row["displayable"]

            if self.data["tab"] == "processes" and self._model.config["tree"]:
                # shallow copy and add the tree prefix
                row = [_ for _ in row]
                row[-1] = sort_row["prefix"] + row[-1]
            sorted_rows.append(row)

        return sorted_rows

    @staticmethod
    def stable_sort(rows: List[Tuple], key: str, ascending: bool) -> List[Tuple]:
        """Stable sort a list of rows by a key"""
        if len(rows) == 0:
            return []
        key_func = lambda x: x[key]
        if isinstance(rows[0], tuple):
            # sometimes the rows are a tuple of (row, ...)
            key_func = lambda x: x[0][key]
            # sort by PID by default
            if "PID" in rows[0][0]:
                rows.sort(key=lambda x: x[0]["PID"])
        else:
            # sort by PID by default
            if "PID" in rows[0]:
                rows.sort(key=lambda x: x["PID"])
        none_vals = [n for n in rows if key_func(n) is None]
        non_none = [n for n in rows if key_func(n) is not None]
        non_none.sort(key=key_func, reverse=not ascending)
        return non_none + none_vals

    @staticmethod
    def _make_tree_prefix(depth: int, not_expandable: bool, end: bool) -> str:
        """Constructs a prefix for the row showing the tree structure"""
        if depth == 0:
            return ""
        return (
            "│  " * ((depth - 1))
            + ("├" if not end else "└")
            + ("─" if not_expandable else "+")
            + " "
        )

    # -- moving to other frames -- #
    @staticmethod
    def _help():
        raise NextScene("Help")

    @staticmethod
    def _quit():
        raise StopApplication("User quit")

    @property
    def frame_update_count(self):
        # we handle update counts ourselves
        return 1
