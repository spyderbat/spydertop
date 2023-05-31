#
# config.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
The configuration frame handles guiding the user through finishing setup or filling in
the information missing from the configuration file.
"""

import os
import fnmatch
import re
from time import sleep
from threading import Thread
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Any, Callable, List, Optional, Tuple, Union

import yaml
from asciimatics.widgets import (
    Frame,
    Text,
    Layout,
    Button,
    Label,
    DatePicker,
    TimePicker,
    CheckBox,
)
from asciimatics.screen import Screen
from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import NextScene, StopApplication

from spydertop.config import Config
from spydertop.constants.columns import Column
from spydertop.model import AppModel
from spydertop.widgets import FuncLabel, Padding
from spydertop.utils import (
    get_timezone,
    pretty_datetime,
    log,
)
from spydertop.constants import API_LOG_TYPES, COLOR_REGEX
from spydertop.widgets.table import Table


class ConfigurationFrame(Frame):  # pylint: disable=too-many-instance-attributes
    """Frame for initial configuration of the application
    to prepare for API access. This frame has several views,
    and switches between them by clearing the layout and rebuilding it."""

    config: Config
    model: AppModel

    thread: Optional[Thread] = None
    _on_submit: Optional[Callable] = None
    _needs_build: bool = True

    def __init__(self, screen: Screen, model: AppModel) -> None:
        super().__init__(  # pylint: disable=duplicate-code
            screen,
            screen.height,
            screen.width,
            has_border=False,
            can_scroll=False,
            name="Configuration",
        )

        self.config = model.config
        self.model = model

        self.cache, self.set_cache = model.use_state(
            str(self._name),
            {
                "has_account": None,  # Optional[bool]
                "orgs": None,  # Optional[List]
                "sources": None,  # Optional[List]
                "source_glob": None,  # Optional[str]
                "looking_for_sources": False,  # bool
                "force_reload": False,  # bool
                "needs_saving": False,  # bool
                "created_account": False,  # bool
                "notification": None,  # Optional[str]
            },
        )

        self.layout = Layout([1, 6, 1], fill_frame=True)
        self.add_layout(self.layout)
        self.footer = Layout([1, 3, 3, 1])
        self.add_layout(self.footer)

        self.set_theme(self.config["theme"])

    def update(self, frame_no):
        if not self._needs_build and self.model.loaded:
            # we have returned from Main, reset state
            self._needs_build = True
            self.model.clear()

        if self._needs_build:
            if self.thread:
                self.thread.join()
                self.thread = None

            self.build_next_layout()

            self.footer.add_widget(Padding(int(self.screen.height * 0.2)), 1)

            self.fix()
            self.reset()
        return super().update(frame_no)

    def process_event(self, event):
        """Processes events from the user"""
        if isinstance(event, KeyboardEvent):
            if event.key_code == ord("\n"):
                if self._on_submit:
                    self._on_submit()
                    self._on_submit = None
        return super().process_event(event)

    def build_next_layout(  # pylint: disable=too-many-branches,too-many-statements,too-many-return-statements
        self,
    ) -> None:
        """Determines which layout to display next based on the state of the config"""

        self._needs_build = False
        self._on_submit = None
        self.layout.clear_widgets()
        self.footer.clear_widgets()

        # add padding which is 20% of the height of the screen (without the title)
        self.layout.add_widget(Padding(max(int(self.screen.height * 0.2) - 2, 0)), 1)
        self.layout.add_widget(
            FuncLabel(
                lambda: """\
 ⢎⡑ ⢀⡀ ⣰⡀ ⡀⢀ ⣀⡀
 ⠢⠜ ⠣⠭ ⠘⠤ ⠣⠼ ⡧⠜
""",
            ),
            1,
        )

        # if the model failed to load, display the error message
        if self.model.failed:
            if "403" in self.model.failure_reason:

                def on_continue():
                    self.config.api_key = None
                    self.model.failed = False
                    self.model.failure_reason = ""

                self.build_instructions(
                    "Your API key is invalid. \
Please make sure you entered it correctly.",
                    on_continue,
                )
                return
            self.build_error(self.model.failure_reason)
            return

        # if there is a notification, display it
        if self.cache["notification"] is not None:
            self.build_instructions(
                self.cache["notification"], lambda: self.set_cache(notification=None)
            )
            return

        # if the config is complete, display the main screen
        if self.config.is_complete:
            if self.cache["needs_saving"] and not self.config.has_config_file:
                self.build_config_save()
                return
            log.info("Config is complete, starting load")
            log.info(self.config)
            self.model.init()
            raise NextScene("Loading")

        # if there is no api_key, determine if the user has an account,
        # and then help them find the api_key
        if self.config.api_key is None:
            self.set_cache(needs_saving=True)
            if self.cache["has_account"] is None:
                self.build_confirm(
                    "Do you have a Spyderbat account?",
                    lambda confirmed: self.set_state("has_account", confirmed),
                )
                return
            if not self.cache["has_account"]:

                def on_next():
                    self.set_cache(created_account=True, has_account=True)

                self.build_instructions(
                    """\
You need a Spyderbat account to use Spydertop, otherwise I won't \
have any data to display! Please go to https://app.spyderbat.com/signup \
and create an account, then come back here to continue.

If you want to try out Spydertop without an account, you can use one \
of the example files (included in the docker image as well as the source \
repository) like so:

    $ spydertop -i examples/minikube-sock-shop.json.gz

""",
                    on_next,
                )
                return
            if self.cache["has_account"]:
                self.build_api_key_question()
                return

        self.model.init_api()

        # if the config has no org, ask the user to select one
        if not self.config.org_confirmed or self.config.org is None:
            self.set_cache(needs_saving=self.config.org is None)
            # if there are no orgs, load the orgs
            if self.cache["orgs"] is None:

                def load_orgs():
                    orgs = self.model.get_orgs(force_reload=self.cache["force_reload"])
                    if orgs is not None:
                        self.set_cache(
                            orgs=[
                                org
                                for org in orgs
                                # the defend the flag org is not useful for the user
                                if org["uid"] != "defend_the_flag"
                            ]
                        )
                    self.trigger_build()
                    self._screen.force_update()
                    self.set_cache(force_reload=False)

                self.thread = Thread(target=load_orgs)
                self.thread.start()
                self.build_loading("Loading organizations...")
                return

            # if there are orgs, determine how many, and pick one
            if self.cache["orgs"] is not None:
                if len(self.cache["orgs"]) == 0:
                    self.build_error(
                        """\
No organizations found! This is unexpected; try \
logging into your account on the website.\
"""
                    )
                    return
                if len(self.cache["orgs"]) == 1:
                    self.set_org(self.cache["orgs"][0])
                if len(self.cache["orgs"]) > 1:
                    orgs = sorted(
                        self.cache["orgs"],
                        key=lambda o: o.get("total_sources", 0),
                        reverse=True,
                    )

                    if self.config.org is None:
                        index = 0
                    else:
                        try:
                            index = [o["uid"] for o in orgs].index(self.config.org)
                        except ValueError:
                            index = 0

                    def reload_orgs():
                        self.set_cache(force_reload=True)
                        self.set_cache(orgs=None)
                        self._on_submit = None
                        self.trigger_build()

                    self.build_question(
                        "Please select an organization",
                        [
                            (
                                [
                                    org["name"],
                                    f"Sources: {org['total_sources']}"
                                    if "total_sources" in org
                                    else "",
                                    str(org.get("owner_email", "")),
                                    ", ".join(org["tags"]) if "tags" in org else "",
                                    org["uid"],
                                ],
                                lambda o=org: self.set_org(o),
                            )
                            for org in orgs
                        ],
                        index,
                        refresh_button=reload_orgs,
                    )
                    return

        # if the config source has asterisks, then it is a glob, and we need to
        # ask the user to select one of the sources that match
        if self.config.machine is not None and "*" in self.config.machine:
            self.set_cache(source_glob=self.config.machine)
            self.config.source_confirmed = False
            self.config.machine = None

        if self.cache["created_account"]:
            self.model.log_api(
                API_LOG_TYPES["account_created"], {"orgId": self.config.org or ""}
            )
            # prevent this log from being sent again
            self.set_cache(created_account=False)

        # if the config has no source, ask the user to select one
        if not self.config.source_confirmed or self.config.machine is None:
            # if the sources have not been loaded, load the sources
            if self.cache["sources"] is None:

                def load_sources():
                    sources = self.model.get_sources(
                        force_reload=self.cache["force_reload"]
                    )
                    clusters = self.model.get_clusters(
                        force_reload=self.cache["force_reload"]
                    )
                    self.set_cache(force_reload=False)
                    if sources is None and clusters is None:
                        self.model.fail("Failed to load any machines or clusters")
                        self.trigger_build()
                        self._screen.force_update()
                        return
                    if self.cache["looking_for_sources"] and sources is not None:
                        if len(sources) == 0:
                            sleep(1)
                            load_sources()
                            return
                    self.set_cache(
                        sources=[
                            source
                            for source in (sources or [])
                            # the global source is not useful in this context
                            if not source["uid"].startswith("global:")
                        ],
                        clusters=clusters or [],
                    )
                    self.trigger_build()
                    self._screen.force_update()

                self.thread = Thread(target=load_sources)
                self.thread.start()
                self.build_loading(
                    "Loading sources..."
                    if not self.cache["looking_for_sources"]
                    else "Looking for sources..."
                )
                return

            # if there are no sources, guide the user through creating one
            if self.cache["sources"] == [] and self.cache["clusters"] == []:
                self.set_cache(needs_saving=True, sources=None)
                self.build_instructions(
                    f"""\
You don't have any sources yet. You can create one by going to \
https://app.spyderbat.com/app/org/{self.config.org}/first-time-config and \
following the instructions. \
Once you have a source configured, you can continue.\
""",
                    lambda: self.set_state("looking_for_sources", True),
                )
                return

            # if there are sources, pick one
            if self.cache["sources"]:
                # if there is a glob, remove non-matching sources
                sources = self.cache["sources"]
                if self.cache["source_glob"]:
                    sources = [
                        s
                        for s in self.cache["sources"]
                        if fnmatch.fnmatch(s["name"], self.cache["source_glob"])
                        or fnmatch.fnmatch(s["uid"], self.cache["source_glob"])
                        or (
                            "description" in s
                            and fnmatch.fnmatch(
                                s["description"],
                                self.cache["source_glob"],
                            )
                        )
                    ]
                    if len(sources) == 0:
                        self.build_instructions(
                            f"No sources matched '{self.cache['source_glob']}'",
                            lambda: self.set_cache(source_glob=None),
                        )
                        return
                    if len(sources) == 1:
                        self.set_source(sources[0])
                        self._needs_build = True
                        self._screen.force_update()
                        return

                self.set_cache(needs_saving=True)
                # sort the sources by the last time they were seen
                sources = sorted(
                    self.cache["sources"],
                    key=lambda s: s.get("last_stored_chunk_end_time", 0),
                    reverse=True,
                )
                if self.config.machine is None:
                    index = 0
                else:
                    try:
                        index = [s["uid"] for s in sources].index(self.config.machine)
                    except ValueError:
                        index = 0

                def back_handler():
                    self.config.org_confirmed = False
                    self.config.source_confirmed = False
                    self._on_submit = None
                    self.trigger_build()

                def refresh_handler():
                    self.set_cache(force_reload=True)
                    self.config.source_confirmed = False
                    self.set_cache(sources=None)
                    self._on_submit = None
                    self.trigger_build()

                # there is no org selection to go back to if
                # the user is in only one org
                if self.cache["orgs"] and len(self.cache["orgs"]) == 1:
                    back = None
                else:
                    back = back_handler

                self.build_question(
                    "Please select a machine or cluster",
                    [
                        (
                            [
                                "${4}Cluster:",
                                cluster.get("name", "<No Name>"),
                                " ",
                                pretty_datetime(
                                    datetime.strptime(
                                        cluster["last_data"],
                                        "%Y-%m-%dT%H:%M:%SZ",
                                    )
                                    .replace(tzinfo=timezone.utc)
                                    .astimezone(tz=get_timezone(self.model))
                                )
                                if "last_data" in cluster
                                else "",
                                str(
                                    datetime.strptime(
                                        cluster["last_data"],
                                        "%Y-%m-%dT%H:%M:%SZ",
                                    )
                                    .replace(tzinfo=timezone.utc)
                                    .astimezone(tz=get_timezone(self.model))
                                ),
                                cluster.get("uid", ""),
                            ],
                            lambda c=cluster: self.set_source(c),
                        )
                        for cluster in sorted(
                            self.cache["clusters"],
                            key=lambda c: c.get("last_data", 0),
                            reverse=True,
                        )
                    ]
                    + [
                        (
                            self.format_source(source),
                            lambda s=source: self.set_source(s),
                        )
                        for source in sources
                    ],
                    index,
                    self.cache["source_glob"],
                    back,
                    refresh_handler,
                )
                return

        # if there is no start time, ask the user to select one
        if not self.config.start_time:
            # if we were looking for sources, we don't need to ask the user to select a start time
            # just use the currently available time
            if self.cache["looking_for_sources"]:
                try:
                    self.config.start_time = datetime.strptime(
                        self.cache["sources"][0]["last_stored_chunk_end_time"],
                        "%Y-%m-%dT%H:%M:%SZ",
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    self.config.start_time = datetime.now() - timedelta(0, 30)
                self._needs_build = True
                self._screen.force_update()
                return

            self.build_timepicker()
            return

        log.err("Reached the end of the config wizard without being complete")
        log.debug(self.config)
        self.build_error("An unexpected error occurred")

    def build_question(  # pylint: disable=too-many-arguments
        self,
        question: str,
        answers: List[Tuple[List[str], Callable]],
        index=0,
        search_string: Optional[str] = None,
        back_button: Optional[Callable] = None,
        refresh_button: Optional[Callable] = None,
    ) -> None:
        """Construct a layout that asks a question and has a set of answers, making use of the
        multi-column list box widget."""
        # create column widths
        columns = [0] * len(answers[0][0])
        # we ignore any more than the first 100 answers to avoid
        # taking too long to calculate the column widths
        for answer in answers[:100]:
            for i in range(len(answer[0])):
                columns[i] = max(
                    columns[i], len(re.sub(COLOR_REGEX, "", answer[0][i])) + 1
                )
        columns = [Column("", min(c, 40), str) for c in columns]
        columns[-1].max_width = 0

        # list_box = MultiColumnListBox(
        #     Widget.FILL_FRAME,
        #     columns,
        #     [(x[0], i) for i, x in enumerate(answers)],
        #     parser=ExtendedParser(),
        #     name="selection",
        # )
        list_box = Table(self.model, None, "selection")
        list_box.header_enabled = False
        list_box.value = index
        list_box.columns = columns
        options = [x[0] for x in answers]
        list_box.set_rows(options, options)
        # list_box.start_line = 0
        text_input = None

        def on_search():
            if text_input is None:
                return
            self.model.config["filter"] = text_input.value
            list_box.do_filter()

        text_input = Text(on_change=on_search, name="search")
        if search_string is not None:
            text_input.value = search_string

        def on_submit():
            if list_box.value is not None:
                self.model.config["filter"] = None
                answers[list_box.value][1]()
            else:
                self.set_cache(notification="No option was selected, please select one")
                self.trigger_build()

        self._on_submit = on_submit

        self.layout.add_widget(Label(question, align="^"), 1)
        self.layout.add_widget(Label("Search:", align="<"), 1)
        self.layout.add_widget(text_input, 1)
        self.layout.add_widget(Padding(), 1)
        self.layout.add_widget(list_box, 1)
        if refresh_button is not None:
            self.layout.add_widget(Button("Refresh", refresh_button), 1)
            self.layout.add_widget(Padding(), 1)
        self.footer.add_widget(
            Button(
                "Continue",
                self._on_submit,
            ),
            1,
        )
        if back_button is None:
            self.footer.add_widget(Button("Quit", self.quit), 2)
        else:
            self.footer.add_widget(Button("Back", back_button), 2)

    def build_instructions(self, instructions: str, callback: Callable) -> None:
        """Construct a layout that displays instructions and waits for user to continue"""
        self.layout.add_widget(FuncLabel(lambda: instructions), 1)
        self.layout.add_widget(Padding(), 1)
        self.footer.add_widget(
            Button("Continue", lambda: (callback(), self.trigger_build())), 1
        )
        self.footer.add_widget(Button("Quit", self.quit), 2)

    def build_api_key_question(self) -> None:
        """Construct a layout that asks the user to enter an api_key"""
        self.layout.add_widget(
            FuncLabel(
                lambda: """\
Please enter your api_key.

You can find this by clicking on the account icon in the top right of the Spyderbat app \
and clicking on 'API Keys'. If you don't have an API key, you can then create one by \
clicking on 'Create API Key'.\
""",
            ),
            1,
        )

        def jwt_validator(text: str) -> bool:
            # regex reference:
            # https://stackoverflow.com/questions/61802832/regex-to-match-jwt#comment125423495_65755789
            return re.match(r"^(?:[\w-]*\.){2}[\w-]*$", text.strip()) is not None

        text = Text(label="API Key:", validator=jwt_validator, name="api_key")

        def set_api_key():
            self.config.api_key = text.value.strip()
            self.trigger_build()

        self._on_submit = set_api_key
        self.layout.add_widget(text, 1)
        self.footer.add_widget(Button("Continue", set_api_key), 1)
        self.footer.add_widget(Button("Quit", self.quit), 2)

    def build_loading(self, message: str) -> None:
        """Construct a layout that displays a loading message"""
        self.layout.add_widget(Label(message, align="^"), 1)

    def build_error(self, message: str) -> None:
        """Construct a layout that displays an error message"""
        self.layout.add_widget(Label(message, align="^"), 1)
        self.layout.add_widget(Button("Quit", self.quit), 1)

    def build_timepicker(  # pylint: disable=too-many-locals,too-many-statements
        self,
    ) -> None:
        """Construct a layout that asks the user to select a start time"""
        self.layout.add_widget(
            FuncLabel(
                lambda: """\
Please select a start time. This can also be passed as a command line argument; \
see the help page for more information.\
""",
            ),
            1,
        )

        time_label = Label("Start Time: 15 minutes ago")
        self.layout.add_widget(time_label, 1)

        time_zone = get_timezone(self.model)

        def on_change():
            selected_time = datetime.combine(date.value, time_widget.value).replace(
                tzinfo=time_zone
            )
            # remove the color from the time label
            time_label.text = f"Start Time: {pretty_datetime(selected_time)[4:]}"

        self.layout.add_widget(Padding(), 1)
        # support for the data necessary to run spydertop began in 2022
        date = DatePicker(
            label="Date:",
            year_range=range(2022, datetime.now().year + 1),
            on_change=on_change,
        )
        self.layout.add_widget(date, 1)
        time_widget = TimePicker(label="Time:", seconds=True, on_change=on_change)

        self.layout.add_widget(Padding(), 1)
        self.layout.add_widget(time_widget, 1)

        default_time = datetime.now(timezone.utc) - timedelta(minutes=15)

        # quick time selector

        # get source create time
        source_time = self.cache.get("source", {}).get("valid_from", None)
        if source_time is not None:
            source_time = datetime.strptime(source_time, "%Y-%m-%dT%H:%M:%SZ")
            source_time = source_time.replace(tzinfo=timezone.utc)
            source_time_local = source_time.astimezone(time_zone)
            # offset by a bit to allow for records to come in.
            source_time_local += timedelta(minutes=1)

            def button_callback():
                date.value = source_time_local
                time_widget.value = source_time_local.time()
                warning_label.text = (
                    "Warning: the create time may not have complete data"
                )
                on_change()

            create_time_button = Button(
                "Use Nano Agent Create Time: "
                + re.sub(COLOR_REGEX, "", pretty_datetime(source_time_local)),
                button_callback,
            )
            warning_label = Label("")
            self.layout.add_widget(Padding(), 1)
            self.layout.add_widget(create_time_button, 1)
            self.layout.add_widget(warning_label, 1)

        last_seen_time = self.cache.get("source", {}).get(
            "last_stored_chunk_end_time", None
        )
        if last_seen_time is not None:
            last_seen_time = datetime.strptime(last_seen_time, "%Y-%m-%dT%H:%M:%SZ")

            # ignore really old dates
            if last_seen_time.year >= 2020:
                last_seen_time = last_seen_time.replace(tzinfo=timezone.utc)
                last_seen_time_local = last_seen_time.astimezone(time_zone)
                if last_seen_time_local < default_time:
                    default_time = last_seen_time_local

                def last_seen_button_callback():
                    date.value = last_seen_time_local
                    time_widget.value = last_seen_time_local.time()
                    on_change()

                last_seen_button = Button(
                    "Use Last Seen Time: "
                    + re.sub(COLOR_REGEX, "", pretty_datetime(last_seen_time_local)),
                    last_seen_button_callback,
                )
                self.layout.add_widget(Padding(), 1)
                self.layout.add_widget(last_seen_button, 1)

        default_time_local = default_time.astimezone(time_zone)
        date.value = default_time_local
        time_widget.value = default_time_local.time()

        # duration selector
        self.layout.add_widget(Padding(), 1)
        duration_label = Label("Duration to pre-load: +/-5 minutes")
        self.layout.add_widget(duration_label, 1)

        def num_validator(value: str) -> bool:
            try:
                float(value)
                return True
            except ValueError:
                return False

        def on_change2():
            nonlocal selected_duration
            if num_validator(duration.value):
                selected_duration = timedelta(minutes=float(duration.value))
                duration_label.text = (
                    f"Duration to pre-load: +{duration.value} minutes, -5 minutes"
                )

        self.layout.add_widget(Padding(), 1)
        duration = Text(
            label="Duration:", validator=num_validator, on_change=on_change2
        )
        duration.value = str(float(self.config.start_duration.total_seconds() // 60))

        selected_duration = timedelta(minutes=float(duration.value))

        self.layout.add_widget(duration, 1)

        self.footer.add_widget(
            Button(
                "Continue",
                lambda: self.set_start_time(
                    date.value, time_widget.value, selected_duration, time_zone  # type: ignore
                ),
            ),
            1,
        )

        def back():
            self.config.source_confirmed = False
            self.trigger_build()

        self.footer.add_widget(Button("Back", back), 2)

    def build_config_save(self) -> None:
        """Construct a layout that asks the user which details to save in their
        configuration to be used again"""
        self.layout.add_widget(
            FuncLabel(
                lambda: """\
Please select which items to save in your configuration. These will be used \
again the next time you start Spydertop, and will skip this configuration menu.

These are default values, and can be overridden by passing them as command line \
arguments (except for the API Key).\
""",
            ),
            1,
        )
        # these values are the opposite of the default values
        # because the CheckBox widget calls the callback when
        # we set its value initially, toggling the value
        to_save = {
            "API_Key": False,
            "Machine": True,
            "Org": False,
        }

        def set_to_save(k):
            to_save[k] = not to_save[k]

        for key, val in to_save.items():
            value = getattr(self.config, key.lower())
            if key == "API_Key":
                # Show only the first and last few characters of the API key
                value = value[:5] + "..." + value[-5:]

            checkbox = CheckBox(
                value,
                label=key,
                on_change=lambda k=key: set_to_save(k),
            )
            checkbox.value = not val
            self.layout.add_widget(checkbox, 1)

        self.footer.add_widget(
            Button(
                "Continue",
                lambda: self.save_config([key for key, val in to_save.items() if val]),
            ),
            1,
        )
        self.footer.add_widget(Button("Quit", self.quit), 2)

    def build_confirm(self, question: str, callback: Callable[[bool], None]) -> None:
        """Create a simple layout to ask a yes/no question"""
        self.layout.add_widget(Label(question, align="^"), 1)
        self.footer.add_widget(Button("Yes", lambda: callback(True)), 1)
        self.footer.add_widget(Button("No", lambda: callback(False)), 2)

    def save_config(self, attributes: List[str]) -> None:
        """Save the configuration to the config file"""
        if len(attributes) == 0:
            self.trigger_build()
            return
        try:
            # make sure the containing folder exists
            path = os.path.join(os.environ["HOME"], ".spyderbat-api")
            if not os.path.exists(path):
                os.mkdir(path)

            # read the config if it exists, and update it with the new values
            config_path = os.path.join(path, "config.yaml")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as conf_file:
                    config = yaml.safe_load(conf_file)
                    if config is None:
                        config = {}
                if "default" not in config:
                    config["default"] = {}
            else:
                config = {"default": {}}
            for attribute in attributes:
                config["default"][attribute.lower()] = getattr(
                    self.config, attribute.lower()
                )

            # write the config back to disk
            with open(
                os.path.join(path, "config.yaml"), "w", encoding="utf-8"
            ) as conf_file:
                yaml.dump(config, conf_file)
        except FileNotFoundError as exc:
            self.model.fail(f"Error saving config: {exc}")

        self.set_cache(needs_saving=False)
        self.trigger_build()

    def format_source(self, source) -> List[str]:
        """Format a source for display"""
        try:
            last_stored_time = (
                datetime.strptime(
                    source["last_stored_chunk_end_time"],
                    "%Y-%m-%dT%H:%M:%SZ",
                )
                .replace(tzinfo=timezone.utc)
                .astimezone(tz=get_timezone(self.model))
            )
        except OverflowError:
            last_stored_time = datetime.fromtimestamp(0).replace(tzinfo=timezone.utc)
        return [
            "${3}Machine:",
            source.get("description", ""),
            " ",
            pretty_datetime(last_stored_time)
            if "last_stored_chunk_end_time" in source
            else "",
            str(last_stored_time),
            source.get("uid", ""),
        ]

    def set_state(self, key: str, value: Any) -> None:
        """Set a state variable"""
        self.set_cache(**{key: value})
        self.trigger_build()

    def set_org(self, org) -> None:
        """Set the organization"""
        if org["uid"] != self.config.org:
            self.set_cache(sources=None)
            self.config.org = org["uid"]
        self.config.org_confirmed = True
        self.trigger_build()

    def set_source(self, source) -> None:
        """Set the source"""
        self.config.machine = source["uid"]
        self.set_cache(source=source)
        self.config.source_confirmed = True
        self.trigger_build()

    def set_start_time(
        self,
        date: datetime,
        time_portion: time,
        duration: timedelta,
        time_zone: Union[timezone, tzinfo, None],
    ) -> None:
        """Set the start time"""
        self.config.start_time = datetime.combine(date, time_portion).replace(
            tzinfo=time_zone
        )
        self.config.start_duration = duration
        self.trigger_build()

    def trigger_build(self) -> None:
        """Trigger a rebuild of the layout"""
        self._needs_build = True

    def quit(self) -> None:
        """Quit the application"""
        raise StopApplication("User quit")
