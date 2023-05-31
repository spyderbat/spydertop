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

import re
from typing import Any, Dict, List, Optional
import urllib.parse
import webbrowser

import pyperclip
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
from spydertop.widgets import Table
from spydertop.utils import (
    align_with_overflow,
    get_machine_short_name,
    log,
    convert_to_seconds,
    pretty_time,
    calculate_widths,
)
from spydertop.utils.types import Alignment, ExtendedParser
from spydertop.constants import API_LOG_TYPES
from spydertop.constants.columns import (
    CONTAINER_COLUMNS,
    PROCESS_COLUMNS,
    SESSION_COLUMNS,
    CONNECTION_COLUMNS,
    FLAG_COLUMNS,
    LISTENING_SOCKET_COLUMNS,
    Column,
)
from spydertop.widgets import FuncLabel, Meter, Padding
from spydertop.screens.footer import Footer


class MainFrame(Frame):  # pylint: disable=too-many-instance-attributes
    """The main frame for the application. This frame is responsible
    for taking user input and determining how much to update the screen."""

    # update and caching management
    _model: AppModel
    _old_settings: Dict[str, Any]
    _last_frame: int = 0
    _widgets_initialized: bool = False
    needs_screen_refresh: bool = True
    needs_update: bool = True
    needs_recalculate: bool = True
    _cached_options: Optional[List] = None
    _cached_sortable: List = []
    _cached_displayable: List = []
    _current_columns: List[Column] = PROCESS_COLUMNS
    _old_column_val = None
    _last_effects: int = 1

    # widgets
    _main: Optional[Layout] = None
    _footer: Footer
    _cpus: Dict[str, List[Meter]] = {}
    _tabs: List[Button] = []
    _memory: Meter
    _swap: Meter
    _columns: Table

    # -- initialization -- #
    def __init__(self, screen, model: AppModel) -> None:
        # pylint: disable=duplicate-code
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

    def _init_widgets(self):  # pylint: disable=too-many-statements
        """Initialize the widgets for the main frame. This is separate from the
        __init__ function because the widgets require the model to be initialized."""
        ############## Header #################
        header = Layout([1, 1], fill_frame=False)
        self.add_layout(header)

        # Show what machine is selected
        header.add_widget(
            FuncLabel(
                lambda: "Machine: " if self._model.selected_machine is not None else "",
                align=Alignment.RIGHT,
            ),
            0,
        )
        header.add_widget(
            FuncLabel(
                lambda: get_machine_short_name(
                    self._model.machines[self._model.selected_machine]
                )
                if self._model.selected_machine is not None
                else ""
            ),
            1,
        )

        # meters
        self._cpus = {}
        cpu_count = 0
        for machine in self._model.machines.values():
            cpu_count = machine["machine_cores"]
            self._cpus[machine["id"]] = []

            for i in range(0, cpu_count):
                if i == 0:
                    name = (
                        align_with_overflow(
                            get_machine_short_name(machine), 20, include_padding=False
                        )
                        + f" {i} "
                    )
                else:
                    name = f"{i:<3}"
                self._cpus[machine["id"]].append(
                    Meter(
                        name,
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
                header.add_widget(self._cpus[machine["id"]][i], column)
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
        available_tabs = [
            "Processes",
            "Flags",
            "Sessions",
            "Connections",
            "Listening",
            "Containers",
        ]
        for tab in available_tabs.copy():
            # if there are no records for the tab, don't add it
            if len(getattr(self._model, tab.lower())) == 0:
                available_tabs.remove(tab)

        tabs_layout = Layout(
            calculate_widths(self.screen.width, [1] * len(available_tabs))
        )
        self._tabs = []
        self.add_layout(tabs_layout)
        for i, name in enumerate(available_tabs):

            def wrapper(name):
                def inner():
                    self._switch_to_tab(name.lower())

                return inner

            button = Button(name, wrapper(name), add_box=False)
            self._tabs.append(button)
            tabs_layout.add_widget(button, i)

        if self._model.config["tab"] not in [t.lower() for t in available_tabs]:
            self._model.config["tab"] = available_tabs[0].lower()

        ################# Main Table #######################
        self._main = Layout([1], fill_frame=True)
        self.add_layout(self._main)

        self._columns = Table(self._model, self._model.tree)
        self._main.add_widget(self._columns)

        ################# Footer #######################

        status = FuncLabel(
            lambda: f"{self._model.state}",
            align=Alignment.RIGHT,
            parser=ExtendedParser(),
            color="focus_button",
        )
        self._footer = Footer(
            calculate_widths(self.screen.width, [1] * 10 + [3]), self, [], status
        )
        self.add_layout(self._footer)
        self._switch_buttons("main")

        self.reset()
        self.fix()
        self._switch_to_tab(self._model.config["tab"], force=True)
        self.switch_focus(self._main, 0, 0)
        self._widgets_initialized = True

    # -- overrides -- #
    def update(self, frame_no):  # pylint: disable=too-many-branches,too-many-statements
        conf = self._model.config
        assert self.scene is not None, "Frame must be added to a scene before updating"

        # if model is in failure state, raise next scene
        if self._model.failed:
            raise NextScene("Failure")
        # early exit if model is not ready
        if not self._model.loaded:
            return
        if not self._widgets_initialized:
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
            self._columns.columns = self._current_columns
            self._model.columns_changed = False
            self.needs_screen_refresh = True

        # detect changes in effects (opened/closed)
        if len(self.scene.effects) != self._last_effects:
            self._last_effects = len(self.scene.effects)
            self.needs_screen_refresh = True

        try:
            # work up the caching system, updating each part of the cache
            # only if necessary
            if self.needs_recalculate:
                self._build_options(getattr(self._model, self._model.config["tab"]))
                self.needs_recalculate = False
                self.needs_update = True

            if self.needs_update:
                self._update_columns()
                self.needs_update = False
                self.needs_screen_refresh = True

            # update screen if needed
            if self.needs_screen_refresh:
                # update header
                for muid, cpus in self._cpus.items():
                    for i, cpu in enumerate(cpus):
                        values = update_cpu(i, self._model, muid)
                        cpu.value = values
                (self._memory.total, self._memory.value) = update_memory(self._model)
                (self._swap.total, self._swap.value) = update_swap(self._model)

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
        if self._main is not None:
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
            "n": lambda: self._switch_to_tab("containers"),
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
                return None
            if event.key_code in range(Screen.KEY_F11, Screen.KEY_F1 + 1):
                self._footer.click(-event.key_code - 2)
                return None
            if event.key_code in {Screen.KEY_TAB, Screen.KEY_BACK_TAB}:
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
                return None

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
        self._columns.columns = self._current_columns
        self._columns.set_rows(self._cached_displayable, self._cached_sortable)

    def _build_options(self, records: Dict[str, Any]):
        """Builds options for records other than the processes tab, using
        the current columns"""
        self._cached_displayable = []
        self._cached_sortable = []

        if self._model.timestamp is None:
            self._model.recover()
            self.needs_recalculate = True
            return

        for record in records.values():
            # determine if the record is visible for this time
            if "valid_from" in record:
                if record["valid_from"] > self._model.timestamp or (
                    "valid_to" in record
                    and "muid" in record
                    and record["valid_to"]
                    < self._model.timestamp
                    - self._model.get_time_elapsed(record["muid"])
                ):
                    continue
            elif "time" in record:
                # show all events only after they occur
                if self._model.timestamp < record["time"]:
                    continue

            # ignore if the record is a process and it is hidden
            if self._model.config["tab"] == "processes" and (
                self._model.config["hide_kthreads"]
                and record["type"] == "kernel thread"
                or self._model.config["hide_threads"]
                and record["type"] == "thread"
            ):
                continue

            # build the row for options
            cells = []
            sortable_cells = []
            for col in self._current_columns:
                sort_val = col.get_value(self._model, record)
                cells.append(col.format_value(self._model, record, sort_val))
                sortable_cells.append(sort_val)

            self._cached_displayable.append(cells)
            self._cached_sortable.append(sortable_cells)

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
        self._cached_sortable = []

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

        if tab_name == "containers":
            self._current_columns = CONTAINER_COLUMNS
            self._model.config["sort_column"] = "CREATED"
            self._model.config["sort_ascending"] = False

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
            options=[
                (row.header_name, row.header_name) for row in self._current_columns
            ],
            on_submit=set_sort,
            widget=ListBox,
            theme=self._model.config["theme"],
            height=len(self._current_columns),
            value=self._model.config["sort_column"],
            on_death=lambda: self._switch_buttons("main"),
        )
        assert self.scene is not None, "A scene must be set in the frame before use"
        self.scene.add_effect(menu)

    def _show_search(self):
        """show the search input modal"""
        self._model.log_api(API_LOG_TYPES["navigation"], {"menu": "search"})
        self._switch_buttons("modal")

        def run_search(value):
            if not value:
                return
            self._columns.find(value)
            self.needs_screen_refresh = True

        assert self.scene is not None, "A scene must be set in the frame before use"
        self.scene.add_effect(
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

        assert self.scene is not None, "A scene must be set in the frame before use"
        self.scene.add_effect(
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

        assert self.scene is not None, "A scene must be set in the frame before use"
        self.scene.add_effect(
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
        source = None

        if self._model.selected_machine is not None:
            source = self._model.selected_machine
        elif row is not None:
            record = self._model.get_record_by_id(row[1][0]) or {}
            source = record.get("muid", None)

        if not row or not self._model.config.org or not source:
            log.info("No row selected or no org/machine/input. Skipping URL")
            assert self.scene is not None, "A scene must be set in the frame before use"
            self.scene.add_effect(
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
/source/{source}/spyder-console?ids={urllib.parse.quote(str(row[1][0]))}"

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

        assert self.scene is not None, "A scene must be set in the frame before use"
        self.scene.add_effect(
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
        for name, value in zip([c.header_name for c in self._current_columns], row[0]):
            # remove any tree characters
            if isinstance(value, ColouredText):
                value = str(value.raw_text)  # type: ignore
            value = value.strip()
            if name == "Command":
                value = re.sub(r"^(│  |   )*[├└][─+] ", "", value)
            data_lines += f"${{{label_fg},1}}{name}:${{{field_fg}}} {value}\n"

        data_lines = data_lines.rstrip("\n")

        assert self.scene is not None, "A scene must be set in the frame before use"
        self.scene.add_effect(
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
        assert self.scene is not None, "A scene must be set in the frame before use"
        self.scene.add_effect(
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
        assert self.scene is not None, "A scene must be set in the frame before use"
        if self._model.timestamp is None:
            self._model.recover()
            return
        # the minimum offset should be to the next top time
        min_offset = (
            self._model.get_time_elapsed(self._model.selected_machine)
            if self._model.selected_machine is not None
            else 5
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
            self.scene.add_effect(
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

    # -- moving to other frames -- #
    def _back(self):
        """Move back to configuring sources"""
        # don't go back if the input is from a file
        if not isinstance(self._model.config.input, str):
            assert self.scene is not None, "A scene must be set in the frame before use"
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
