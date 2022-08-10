#
# main.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
The main frame for the tool. This frame contains the record list and usage metrics,
as well as showing all the menu buttons.
"""

from math import nan
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib
import pyperclip
import webbrowser

from asciimatics.screen import Screen
from asciimatics.widgets import (
    Frame,
    Layout,
    Button,
    ListBox,
)
from asciimatics.exceptions import NextScene
from asciimatics.event import KeyboardEvent
from asciimatics.strings import ColouredText

from spydertop.model import AppModel
from spydertop.screens.setup import SetupFrame
from spydertop.screens.meters import (
    update_memory,
    update_swap,
    show_disk_io,
    show_ld_avg,
    show_network,
    show_tasks,
    update_cpu,
    show_uptime,
)
from spydertop.screens.modals import InputModal, NotificationModal
from spydertop.table import Table
from spydertop.utils import (
    API_LOG_TYPES,
    BetterDefaultDict,
    ExtendedParser,
    log,
    convert_to_seconds,
    pretty_time,
)
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
    """The main frame for the application"""

    # update and caching management
    _model: AppModel
    _old_settings: Dict[str, Any]
    _last_frame: int = 0
    _widgets_initialized: bool = False
    needs_screen_refresh: bool = True
    needs_update: bool = True
    needs_recalculate: bool = True
    _cached_options: Optional[List] = None
    _cached_sortable: Optional[List] = None
    _cached_displayable: Optional[List] = None
    _current_columns: List = PROCESS_COLUMNS
    _old_column_val = None
    _last_effects: int = 1

    # widgets
    _main: Layout = None
    _footer: Footer
    _cpus: List[Meter] = []
    _tabs: List[Button] = []
    _memory: Meter
    _swap: Meter
    _columns: Table

    # -- initialization -- #
    def __init__(self, screen, model: AppModel) -> None:
        super().__init__(
            screen,
            screen.height,
            screen.width,
            has_border=False,
            can_scroll=False,
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
        cpu_count = (
            self._model.machine["machine_cores"]
            if self._model.machine
            else len(self._model.get_value("cpu_time") or [])
        )
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
            FuncLabel(lambda: show_disk_io(self._model), parser=ExtendedParser()),
            column=0,
        )
        header.add_widget(
            FuncLabel(lambda: show_network(self._model), parser=ExtendedParser()),
            column=0,
        )

        header.add_widget(
            FuncLabel(lambda: show_tasks(self._model), parser=ExtendedParser()),
            column=1,
        )
        header.add_widget(
            FuncLabel(lambda: show_ld_avg(self._model), parser=ExtendedParser()),
            column=1,
        )
        header.add_widget(
            FuncLabel(lambda: show_uptime(self._model), parser=ExtendedParser()),
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

        self._columns = Table(self._model, self._model.tree)
        self._main.add_widget(self._columns)

        ################# Footer #######################

        status = FuncLabel(
            lambda: f"{self._model.state}",
            align=">",
            parser=ExtendedParser(),
            color="focus_button",
        )
        self._footer = Footer(self.calculate_widths([1] * 10 + [3]), self, [], status)
        self.add_layout(self._footer)
        self._switch_buttons("main")

        self.reset()
        self.fix()
        self._switch_to_tab(self._model.config["tab"], force=True)
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
                new_time = self._model.timestamp + time_delta * conf["play_speed"]
                if not self._model.is_loaded(new_time):
                    # stop playing and notify user
                    conf["play"] = False
                    self.scene.add_effect(
                        NotificationModal(
                            self.screen,
                            "The end of loaded data has been reached. "
                            "Continue forward to load more data.",
                            self,
                            frames=40,
                        )
                    )
                else:
                    self._model.timestamp = new_time
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
                            if self._model.config["tab"] == button.text.lower()
                            else "tab"
                        )
                    else:
                        button.custom_colour = (
                            "selected_focus_field"
                            if self._model.config["tab"] == button.text.lower()
                            else "focus_field"
                        )
                self.needs_screen_refresh = True

            if conf["utc_time"] != self._old_settings["utc_time"]:
                self.needs_recalculate = True

            self._footer.change_button_text(
                "Play" if self._model.config["play"] else "Pause",
                "Play" if not self._model.config["play"] else "Pause",
            )
            self.fix()
            self.needs_screen_refresh = True
            if (
                conf["hide_threads"] != self._old_settings["hide_threads"]
                or conf["hide_kthreads"] != self._old_settings["hide_kthreads"]
            ) and self._model.config["tab"] == "processes":
                self.needs_recalculate = True
            self._old_settings = self._model.config.settings.copy()

        # update columns if needed
        if self._model.columns_changed:
            self._columns.set_columns(self._current_columns)
            self._model.columns_changed = False
            self.needs_screen_refresh = True

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
                self._update_columns()
                self.needs_update = False
                self.needs_screen_refresh = True

            # update screen if needed
            if self.needs_screen_refresh:
                # update header
                for (i, cpu) in enumerate(self._cpus):
                    cpu.value = update_cpu(i, self._model)
                (total, values) = update_memory(self._model)
                self._memory.total = total
                self._memory.value = values
                (total, values) = update_swap(self._model)
                self._swap.total = total
                self._swap.value = values

                self.needs_screen_refresh = False
                # time screen update
                super().update(frame_no)
        except Exception as exc:
            self._model.fail("An error occurred while updating the screen.")
            log.traceback(exc)
            raise NextScene("Failure") from exc

    def process_event(self, event):
        self.needs_screen_refresh = True
        # force the main table to have focus
        self.switch_focus(self._main, 0, 0)
        # Do the key handling for this Frame.
        key_map = {
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
            "u": lambda: self._show_url(True),
            "U": lambda: self._show_url(False),
            "H": lambda: self._config("hide_threads"),
            "K": lambda: self._config("hide_kthreads"),
            "I": lambda: self._config("sort_ascending"),
            "t": lambda: self._config("tree"),
            "*": lambda: self._config("collapse_tree"),
            "F": lambda: self._config("follow_record"),
            "-": self._enable_disable,
            "=": self._enable_disable,
            "+": self._enable_disable,
            "\n": self._show_details,
        }
        if isinstance(event, KeyboardEvent):
            if event.key_code in {ord(k) for k in key_map}:
                key_map[chr(event.key_code)]()
                return
            if event.key_code in range(Screen.KEY_F11, Screen.KEY_F1 + 1):
                self._footer.click(-event.key_code - 2)
            if (
                event.key_code == Screen.KEY_TAB
                or event.key_code == Screen.KEY_BACK_TAB
            ):
                current_tab_index = 0
                for i, tab in enumerate(self._tabs):
                    if tab.text.lower() == self._model.config["tab"]:
                        current_tab_index = i
                        break
                offset = 1 if event.key_code == Screen.KEY_TAB else -1
                next_tab = self._tabs[
                    (current_tab_index + offset) % len(self._tabs)
                ].text.lower()
                self._switch_to_tab(next_tab)
                return

        # if no widget is focused, focus the table widget
        try:
            self._layouts[self._focus].focus()
        except IndexError:
            self.switch_focus(self._main, 0, 0)
        # Now pass on to lower levels for normal handling of the event.
        return super().process_event(event)

    # -- update handling -- #
    def _update_columns(self):
        """Update the columns in the multi-column list box widget."""
        self._columns.set_columns(self._current_columns)
        self._columns.set_rows(self._cached_displayable, self._cached_sortable)

    def _build_options(self):
        """Build the options for the records table, depending on the current tab."""
        if self._model.config["tab"] == "processes":
            (
                self._cached_displayable,
                self._cached_sortable,
            ) = self._build_process_options()

        if self._model.config["tab"] == "sessions":
            (
                self._cached_displayable,
                self._cached_sortable,
            ) = self._build_other_options(self._model.sessions)

        if self._model.config["tab"] == "flags":
            (
                self._cached_displayable,
                self._cached_sortable,
            ) = self._build_other_options(self._model.flags)

        if self._model.config["tab"] == "connections":
            (
                self._cached_displayable,
                self._cached_sortable,
            ) = self._build_other_options(self._model.connections)

        if self._model.config["tab"] == "listening":
            (
                self._cached_displayable,
                self._cached_sortable,
            ) = self._build_other_options(self._model.listening)

    def _build_other_options(self, records: Dict[str, Any]) -> Tuple[List, List]:
        """Builds options for records other than the processes tab, using
        the current columns"""
        rows = []
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
            sortable_cells = []
            for col in self._current_columns:
                sort_val = col[4](self._model, record)
                # pylint: disable=no-value-for-parameter
                cells.append(str(col[1](self._model, record)))
                sortable_cells.append(sort_val)

            rows.append(cells)
            sortable_rows.append(sortable_cells)

        return rows, sortable_rows

    def _build_process_options(
        self,
    ) -> Tuple[List, List]:
        """Build options for the processes tab. This requires more work than
        the other tabs, because the data is not in a single record; the
        event_top data is also required to be bundled in"""
        model_processes = self._model.processes
        previous_et_processes, event_top_processes = self._model.get_top_processes()
        defaults = (
            event_top_processes["default"]
            if event_top_processes is not None
            else BetterDefaultDict(lambda k: nan if k != "state" else "?")
        )

        rows = []
        sortable_rows = []

        # loop through the process records, and fill in the event_top data
        # if it is available
        for process in model_processes.values():
            # determine if the record is visible in this time period
            if process["valid_from"] > self._model.timestamp:
                continue
            end_time = process.get(
                "valid_to",
                process["valid_from"] + process["duration"]
                if "duration" in process
                else None,
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
            if (
                event_top_processes is not None
                and previous_et_processes is not None
                and pid in event_top_processes
                and pid in previous_et_processes
            ):
                et_process = event_top_processes[pid]
                prev_et_process = previous_et_processes[pid]
            else:
                et_process = None
                prev_et_process = None

            # build the row for options
            cells = []
            sortable_cells = []
            for col in self._current_columns:
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
                sortable_cells.append(sort_val)

            rows.append(cells)
            sortable_rows.append(sortable_cells)

        return rows, sortable_rows

    # -- input handling -- #
    def _enable_disable(self):
        """find the currently selected row and enable/disable that
        branch in the model.tree"""
        if self._model.config["tab"] != "processes":
            return
        row = self._columns.get_selected()
        if row is None:
            return

        def recursive_enable_disable(tree, id_to_ed):
            for rec_id, branch in tree.items():
                if branch is None:
                    continue
                if rec_id == id_to_ed:
                    tree[rec_id] = (not branch[0], branch[1])
                    return
                else:
                    recursive_enable_disable(branch[1], id_to_ed)

        recursive_enable_disable(self._model.tree, row[1][0])
        self.needs_update = True

    def _switch_buttons(self, version):
        """Switch the footer buttons to the given version"""
        main = [
            ("Help", self._help),
            ("Setup", self._show_setup),
            ("Search", self._show_search),
            ("Filter", self._show_filter),
            ("Tree", lambda: self._config("tree")),
            ("SortBy", self._show_sort_menu),
            ("Time", lambda: self._switch_buttons("time")),
            ("Play", self._play),
            ("Back", self._back),
            ("Quit", self._quit),
        ]

        # relative time picker
        time_selection = [
            ("-1 hour", lambda: self._shift_time(-3600.0)),
            ("-15 minutes", lambda: self._shift_time(-60.0 * 15)),
            ("-1 minute", lambda: self._shift_time(-60.0)),
            ("-15 seconds", lambda: self._shift_time(-15.0)),
            ("+15 seconds", lambda: self._shift_time(15.0)),
            ("+1 minute", lambda: self._shift_time(60.0)),
            ("+15 minutes", lambda: self._shift_time(60.0 * 15)),
            ("+1 hour", lambda: self._shift_time(3600.0)),
            ("Custom", self._show_time_entry),
            ("Done", lambda: self._switch_buttons("main")),
        ]

        # for when modals are opened
        modal = [
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
            self._footer.set_buttons(main)
        elif version == "time":
            self._footer.set_buttons(time_selection)
        elif version == "modal":
            self._footer.set_buttons(modal)

        self.fix()

    def _switch_to_tab(self, tab_name: str, force: bool = False):
        """Switch to the given tab, and update the state accordingly"""

        # update tabs colors
        for button in self._tabs:
            if "tab" in self.palette:
                button.custom_colour = (
                    "selected_tab" if tab_name == button.text.lower() else "tab"
                )
            else:
                button.custom_colour = (
                    "selected_focus_field"
                    if tab_name == button.text.lower()
                    else "focus_field"
                )
        self.needs_screen_refresh = True

        # update state
        if tab_name == self._model.config["tab"] and not force:
            return
        self._model.config["tab"] = tab_name
        self._columns.value = 0
        self.needs_recalculate = True
        self._model.config["sort_column"] = None
        self._model.config["filter"] = None
        self._cached_options = None
        self._cached_sortable = None

        self._model.log_api(API_LOG_TYPES["navigation"], {"tab": tab_name})

        # update columns and sort
        if tab_name == "processes":
            self._current_columns = PROCESS_COLUMNS
            self._model.config["sort_column"] = "CPU%"
            self._model.config["sort_ascending"] = False
            self._model.config["tree"] = self._model.config["tree_enabled"]
        else:
            self._model.config["tree"] = False

        if tab_name == "sessions":
            self._current_columns = SESSION_COLUMNS
            self._model.config["sort_column"] = "I"
            self._model.config["sort_ascending"] = False

        if tab_name == "flags":
            self._current_columns = FLAG_COLUMNS
            self._model.config["sort_column"] = "AGE"
            self._model.config["sort_ascending"] = True

        if tab_name == "connections":
            self._current_columns = CONNECTION_COLUMNS
            self._model.config["sort_column"] = "DURATION"
            self._model.config["sort_ascending"] = True

        if tab_name == "listening":
            self._current_columns = LISTENING_SOCKET_COLUMNS
            self._model.config["sort_column"] = "DURATION"
            self._model.config["sort_ascending"] = True

    def _show_sort_menu(self):
        """show the sort menu"""
        self._model.log_api(API_LOG_TYPES["navigation"], {"menu": "sort"})
        self._switch_buttons("modal")

        def set_sort(title):
            log.info(f"Switching sort to: {title}")
            self._model.config["sort_column"] = title

        menu = InputModal(
            self.screen,
            label="Sort By:",
            options=[(row[0], row[0]) for row in self._current_columns],
            on_submit=set_sort,
            widget=ListBox,
            theme=self._model.config["theme"],
            height=len(self._current_columns),
            value=self._model.config["sort_column"],
            on_death=lambda: self._switch_buttons("main"),
        )
        self._scene.add_effect(menu)

    def _show_search(self):
        """show the search input modal"""
        self._model.log_api(API_LOG_TYPES["navigation"], {"menu": "search"})
        self._switch_buttons("modal")

        def run_search(value):
            if not value:
                return
            self._columns.find(value)
            self.needs_screen_refresh = True

        self._scene.add_effect(
            InputModal(
                self.screen,
                label="Search:",
                theme=self._model.config["theme"],
                on_change=run_search,
                on_death=lambda: self._switch_buttons("main"),
                validator=self._columns.find,
            )
        )

    def _show_time_entry(self):
        """Show a modal to enter a time offset"""
        self._model.log_api(API_LOG_TYPES["navigation"], {"menu": "time"})
        self._switch_buttons("modal")

        def validator(val):
            try:
                convert_to_seconds(val)
                return True
            except (ValueError, IndexError):
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
        self._model.log_api(API_LOG_TYPES["navigation"], {"menu": "filter"})
        self._switch_buttons("modal")

        def set_filter(value):
            self._model.config["filter"] = value

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

    def _show_url(self, open_in_browser: bool = False):
        """Show a url menu with full width"""
        self._model.log_api(API_LOG_TYPES["navigation"], {"menu": "url"})

        row = self._columns.get_selected()
        if (
            not row
            or not self._model.config.org
            or not self._model.config.machine
            or not isinstance(self._model.config.input, str)
        ):
            log.info("No row selected or no org/machine/input. Skipping URL")
            self._scene.add_effect(
                NotificationModal(
                    self.screen,
                    text="${1,1}Error:${-1,2} Cannot create URL. "
                    "This is likely because you are loading from a file.",
                    parent=self,
                    frames=30,
                )
            )
            return

        url = f"https://app.spyderbat.com/app/org/{self._model.config.org}\
/source/{self._model.config.machine}/spyder-console?ids={urllib.parse.quote(row[0][0])}"

        # try to open the url in the browser and copy it to the clipboard
        browser_label = "URL not opened in browser"
        if open_in_browser:
            try:
                webbrowser.open(url)
                browser_label = "URL Opened in browser"
            except Exception:  # pylint: disable=broad-except
                browser_label = "Failed to open URL in browser"
        try:
            pyperclip.copy(url)
            label = "URL copied to the clipboard"
        except Exception:  # pylint: disable=broad-except
            label = "Could not copy URL to the clipboard"

        self._scene.add_effect(
            NotificationModal(
                self.screen,
                text=f" {browser_label} \n {label} \n {url} ",
                parent=self,
                frames=None,
                max_width=self.screen.width - 2,
            )
        )

    def _show_details(self):
        """Show a modal with details about the selected record"""
        row = self._columns.get_selected()
        if not row:
            return

        label_fg = self.palette["label"][0]
        field_fg = self.palette["field"][0]

        # convert the sorted rows to a human-readable string
        data_lines = ""
        for (name, value) in zip([c[0] for c in self._current_columns], row[0]):
            # remove any tree characters
            if isinstance(value, ColouredText):
                value = value.raw_text
            value = value.strip()
            if name == "Command":
                value = re.sub(r"^(│  |   )*[├└][─+] ", "", value)
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
        self._model.log_api(API_LOG_TYPES["navigation"], {"menu": "setup"})
        self._switch_buttons("modal")
        self._scene.add_effect(
            SetupFrame(
                self.screen,
                self._model,
                on_death=lambda: self._switch_buttons("main"),
            )
        )

    def _play(self):
        """Update the model to play"""
        self._model.log_api(API_LOG_TYPES["navigation"], {"button": "play"})
        self._model.config["play"] = not self._model.config["play"]

    def _shift_time(self, offset: float):
        """Shift the time in Model by a given amount."""
        # the minimum offset should be to the next top time
        min_offset = (
            self._model.time_elapsed if self._model.time_elapsed is not nan else 1
        )
        offset = max(min_offset, abs(offset)) * (1 if offset > 0 else -1)
        self._model.timestamp += offset

        if not self._model.tops_valid() and self._model.loaded:
            self.scene.add_effect(
                NotificationModal(
                    self.screen,
                    """\
${1,1}Warning: ${7}this time is missing some data. \
Some information displayed may not be accurate\
""",
                    self,
                    frames=30,
                )
            )

        # if the offset is large, notify the user
        if abs(offset) > 10:
            direction = "forward" if offset > 0 else "backward"
            self._scene.add_effect(
                NotificationModal(
                    self.screen,
                    f"Moved {pretty_time(abs(round(offset)))} {direction}",
                    self,
                    frames=15,
                )
            )

        self.needs_recalculate = True

        # load new data, if necessary
        if not self._model.loaded:
            raise NextScene("Loading")

    def _config(self, name: str, value=None):
        """Change a config value, and handle any effects"""
        if name == "tree":
            self._model.config["tree_enabled"] = (
                value or not self._model.config["tree_enabled"]
            )
            self._model.config[name] = (
                self._model.config["tree_enabled"]
                and self._model.config["tab"] == "processes"
            )
            return

        value = value or not self._model.config[name]
        self._model.config[name] = value

        if name == "collapse_tree":
            self._model.rebuild_tree()
            self._columns.tree = self._model.tree

    # -- miscellaneous -- #
    def calculate_widths(self, desired_columns: List[int]) -> List[int]:
        """Manually calculate the widths for a Layout, as the default has rounding errors."""
        total_width = self.screen.width
        total_desired = sum(desired_columns)
        actual_widths = [int(x / total_desired * total_width) for x in desired_columns]
        actual_widths[-1] += total_width - sum(actual_widths)
        return actual_widths

    # -- moving to other frames -- #
    def _back(self):
        """Move back to configuring sources"""
        # don't go back if the input is from a file
        if not isinstance(self._model.config.input, str):
            self.scene.add_effect(
                NotificationModal(
                    self.screen,
                    "There's no going back! Input is from a file.",
                    self,
                    frames=40,
                )
            )
            return
        self._model.log_api(API_LOG_TYPES["navigation"], {"button": "back"})
        self._model.config.source_confirmed = False
        self._model.config.start_time = None
        self._model.config["play"] = False
        self._switch_to_tab("processes")
        raise NextScene("Config")

    def _help(self):
        """Show the help screen"""
        self._model.log_api(API_LOG_TYPES["navigation"], {"button": "help"})
        raise NextScene("Help")

    def _quit(self):
        """Quit the program"""
        self._model.log_api(API_LOG_TYPES["navigation"], {"button": "quit"})
        raise NextScene("Quit")

    @property
    def frame_update_count(self):
        # we handle update counts ourselves
        return 1
