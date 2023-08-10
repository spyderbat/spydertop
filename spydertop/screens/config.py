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

from dataclasses import dataclass
from enum import Enum
import fnmatch
import re
from threading import Thread
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, TextIO

from asciimatics.widgets import (
    Frame,
    Text,
    Layout,
    Button,
    Label,
    DatePicker,
    TimePicker,
)
from asciimatics.screen import Screen
from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import StopApplication
from spydertop.config import DEFAULT_API_URL

from spydertop.config.config import Config, Context
from spydertop.config.secrets import Secret
from spydertop.constants.columns import Column
from spydertop.model import AppModel
from spydertop.recordpool import RecordPool
from spydertop.state import ExitReason, State
from spydertop.utils.types import APIError, LoadArgs
from spydertop.widgets import FuncLabel, Padding
from spydertop.utils import (
    get_timezone,
    pretty_datetime,
    log,
)
from spydertop.constants import API_LOG_TYPES, COLOR_REGEX
from spydertop.widgets.table import Table


@dataclass
class ConfigState:  # pylint: disable=too-many-instance-attributes
    """State for the configuration frame"""

    duration: timedelta
    has_account: Optional[bool] = None
    api_key: Optional[str] = None
    source_glob: Optional[str] = None
    looking_for_sources: bool = False
    force_reload: bool = False
    created_account: bool = False
    notification: Optional[str] = None
    failure_reason: Optional[str] = None


class ConfigStep(Enum):
    """Enum for the different configuration steps"""

    HAS_ACCOUNT = 0
    API_KEY = 1
    ORGANIZATION = 2
    SOURCE = 3
    TIME = 4
    FINISH = -1


class ConfigurationFrame(Frame):  # pylint: disable=too-many-instance-attributes
    """Frame for initial configuration of the application
    to prepare for API access. This frame has several views,
    and switches between them by clearing the layout and rebuilding it."""

    config: Config
    state: State
    recordpool: Optional[RecordPool] = None

    thread: Optional[Thread] = None
    cache: ConfigState
    _on_submit: Optional[Callable] = None
    _needs_build: bool = True
    _ouptut: Optional[TextIO]

    def __init__(
        self,
        screen: Screen,
        config: Config,
        state: State,
        args: LoadArgs,
    ) -> None:
        super().__init__(  # pylint: disable=duplicate-code
            screen,
            screen.height,
            screen.width,
            has_border=False,
            can_scroll=False,
            name="Configuration",
        )

        self.config = config
        self.state = state
        self.args = args

        self.cache = self.state.use_state(
            str(self._name),
            ConfigState(
                duration=timedelta(minutes=config.settings.default_duration_minutes)
            ),
        )

        # set up information that is already in config or args
        if self.config.active_context is not None:
            context = self.config.contexts[self.config.active_context]
            secret = context.get_secret(config.directory)
            if secret is not None:
                self.set_api_key(secret.api_key, secret.api_url)
                self.cache.has_account = True
            self.state.org_uid = context.org_uid or ""
            self.state.source_uid = context.source
            if context.time is not None:
                import dateparser  # pylint: disable=import-outside-toplevel

                self.state.time = dateparser.parse(context.time)
                log.log("parsing time:", context, self.state.time)

        if self.args.source is not None:
            if "*" in self.args.source:
                self.cache.source_glob = self.args.source
                self.state.source_uid = None
            else:
                self.state.source_uid = self.args.source

        self.cache.duration = args.duration or timedelta(
            minutes=config.settings.default_duration_minutes
        )
        self.state.time = args.timestamp or self.state.time

        self.state.org_uid = self.args.organization or self.state.org_uid

        self.layout = Layout([1, 6, 1], fill_frame=True)
        self.add_layout(self.layout)
        self.footer = Layout([1, 3, 3, 1])
        self.add_layout(self.footer)

        self.set_theme(self.config.settings.theme)

    def update(self, frame_no):
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

    def _pick_current_step(self) -> ConfigStep:
        """Determines which step of the configuration process to display next"""
        if not self.cache.has_account:
            return ConfigStep.HAS_ACCOUNT
        if self.cache.api_key is None:
            return ConfigStep.API_KEY
        if self.state.org_uid == "":
            return ConfigStep.ORGANIZATION
        if self.state.source_uid is None:
            return ConfigStep.SOURCE
        if self.state.time is None:
            return ConfigStep.TIME
        return ConfigStep.FINISH

    def build_next_layout(  # pylint: disable=too-many-branches,too-many-statements,too-many-locals,too-many-return-statements
        self,
    ) -> None:
        """Determines which layout to display next based on the state of the config"""
        self._needs_build = False
        self._on_submit = None
        self.layout.clear_widgets()
        self.footer.clear_widgets()

        current_step = self._pick_current_step()

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
        if self.cache.failure_reason is not None:
            self.build_error(self.cache.failure_reason or "Unknown error")
            return

        # if there is a notification, display it
        if self.cache.notification is not None:
            self.build_instructions(
                self.cache.notification,
                lambda: setattr(self.cache, "notification", None),
            )
            return

        # if the config is complete, display the main screen
        if current_step == ConfigStep.FINISH:
            assert self.recordpool is not None

            if self.cache.created_account:
                # create a temporary model to log the account creation
                model = AppModel(
                    self.config.settings,
                    self.state,
                    self.recordpool,
                )
                model.log_api(
                    API_LOG_TYPES["account_created"],
                    {"orgId": self.state.org_uid or ""},
                )
            # update the configuration if the user does not have one complete
            if len(self.config.contexts) == 0:
                secrets = Secret.get_secrets(self.config.directory)
                if not self.cache.api_key in [s.api_key for s in secrets.values()]:
                    assert isinstance(self.recordpool.input_, Secret)
                    secrets["default"] = self.recordpool.input_
                    Secret.set_secrets(self.config.directory, secrets)

                self.config.contexts["default"] = Context(
                    secret_name="default",
                    org_uid=None,
                    source=None,
                )
                self.config.active_context = "default"
            log.info("Config is complete, starting load")
            raise StopApplication("Finished configuration")

        if current_step == ConfigStep.HAS_ACCOUNT:
            if self.cache.has_account is None:

                def callback1(confirmed):
                    self.cache.has_account = confirmed
                    self._needs_build = True

                self.build_confirm(
                    "Do you have a Spyderbat account?",
                    callback1,
                )
                return

            def callback():
                self.cache.has_account = True
                self.cache.created_account = True
                self._needs_build = True

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
                callback,
            )
            return

        if current_step == ConfigStep.API_KEY:
            self.build_api_key_question()
            return

        # if the config has no org, ask the user to select one
        if current_step == ConfigStep.ORGANIZATION:
            assert self.recordpool is not None
            # if there are no orgs, load the orgs
            if len(self.recordpool.orgs) == 0:
                self.load_data("orgs")
                self.build_loading("Loading organizations...")
                return

            # if there are orgs, determine how many, and pick one
            if len(self.recordpool.orgs) == 1:
                self.state.org_uid = self.recordpool.orgs[0]["id"]
                self._needs_build = True
                return
            if len(self.recordpool.orgs) > 1:
                orgs = sorted(
                    self.recordpool.orgs,
                    key=lambda o: o.get("name", "").lower(),
                    reverse=False,
                )

                def reload_orgs():
                    self.cache.force_reload = True
                    self._on_submit = None
                    self._needs_build = True

                def org_callback(row):
                    if row is None:
                        return
                    self.state.org_uid = row[3]
                    self._needs_build = True

                self.build_question(
                    "Please select an organization",
                    [
                        [
                            org.get("name", ""),
                            str(org.get("owner_email", "")),
                            ", ".join(org.get("tags", [])),
                            org.get("uid", ""),
                        ]
                        for org in orgs
                    ],
                    org_callback,
                    0,
                    refresh_button=reload_orgs,
                )
                return

        # if the config has no source, ask the user to select one
        if current_step == ConfigStep.SOURCE:
            assert self.recordpool is not None
            # if the sources have not been loaded, load the sources
            if self.state.org_uid not in self.recordpool.sources:
                self.load_data("sources")
                self.build_loading(
                    "Loading sources..."
                    if not self.cache.looking_for_sources
                    else "Looking for sources..."
                )
                return

            sources = self.recordpool.sources.get(self.state.org_uid, [])
            clusters = self.recordpool.clusters.get(self.state.org_uid, [])
            # if there are no sources, guide the user through creating one
            if len(sources) == 0 and len(clusters) == 0:
                self.build_instructions(
                    f"""\
You don't have any sources yet. You can create one by going to \
https://app.spyderbat.com/app/org/{self.state.org_uid}/first-time-config and \
following the instructions. \
Once you have a source configured, you can continue.\
""",
                    lambda: setattr(self.cache, "looking_for_sources", True),
                )
                return

            # if there are sources, pick one
            if sources:
                # if there is a glob, remove non-matching sources
                if self.cache.source_glob:
                    sources = [
                        s
                        for s in sources
                        if fnmatch.fnmatch(s["name"], self.cache.source_glob)
                        or fnmatch.fnmatch(s["uid"], self.cache.source_glob)
                        or (
                            "description" in s
                            and fnmatch.fnmatch(
                                s["description"],
                                self.cache.source_glob,
                            )
                        )
                    ]
                    if len(sources) == 0:
                        self.build_instructions(
                            f"No sources matched '{self.cache.source_glob}'",
                            lambda: setattr(self.cache, "source_glob", None),
                        )
                        return
                    if len(sources) == 1:
                        self.state.source_uid = sources[0]["uid"]
                        self._needs_build = True
                        self._screen.force_update()
                        return

                # sort the sources by the last time they were seen
                sources = sorted(
                    sources,
                    key=lambda s: s.get("last_stored_chunk_end_time", 0),
                    reverse=True,
                )

                def back_handler():
                    self.state.org_uid = ""
                    self.state.source_uid = None
                    self._on_submit = None
                    self._needs_build = True

                def refresh_handler():
                    self.cache.force_reload = True
                    self.state.source_uid = None
                    self._on_submit = None
                    self._needs_build = True

                # there is no org selection to go back to if
                # the user is in only one org
                if self.recordpool.orgs and len(self.recordpool.orgs) == 1:
                    back = None
                else:
                    back = back_handler

                def set_source(row):
                    if row is None:
                        return
                    self.state.source_uid = row[5]
                    self._needs_build = True

                self.build_question(
                    "Please select a machine or cluster",
                    [
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
                                .astimezone(tz=get_timezone(self.config.settings))
                            )
                            if "last_data" in cluster
                            else "",
                            str(
                                datetime.strptime(
                                    cluster["last_data"],
                                    "%Y-%m-%dT%H:%M:%SZ",
                                )
                                .replace(tzinfo=timezone.utc)
                                .astimezone(tz=get_timezone(self.config.settings))
                            ),
                            cluster.get("uid", ""),
                        ]
                        for cluster in sorted(
                            clusters,
                            key=lambda c: c.get("last_data", 0),
                            reverse=True,
                        )
                    ]
                    + [self.format_source(source) for source in sources],
                    set_source,
                    0,
                    self.cache.source_glob,
                    back,
                    refresh_handler,
                )
                return

        # if there is no start time, ask the user to select one
        if not self.state.time:
            # if we were looking for sources, we don't need to ask the user to select a start time
            # just use the currently available time
            if self.cache.looking_for_sources and self.state.org_uid:
                assert self.recordpool is not None
                sources = self.recordpool.sources.get(self.state.org_uid, [])
                try:
                    self.state.time = datetime.strptime(
                        sources[0]["last_stored_chunk_end_time"],
                        "%Y-%m-%dT%H:%M:%SZ",
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    self.state.time = datetime.now() - timedelta(0, 30)
                self._needs_build = True
                self._screen.force_update()
                return

            self.build_timepicker()
            return

        log.err("Reached the end of the config wizard without being complete")
        log.debug(self.cache)
        self.build_error("An unexpected error occurred")

    def build_question(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        question: str,
        answers: List[List[str]],
        callback: Callable[[Optional[List[str]]], None],
        index=0,
        search_string: Optional[str] = None,
        back_button: Optional[Callable] = None,
        refresh_button: Optional[Callable] = None,
    ) -> None:
        """Construct a layout that asks a question and has a set of answers, making use of the
        multi-column list box widget."""
        # create column widths
        columns = [0] * len(answers[0])
        # we ignore any more than the first 100 answers to avoid
        # taking too long to calculate the column widths
        for answer in answers[:100]:
            for i, cell in enumerate(answer):
                columns[i] = max(columns[i], len(re.sub(COLOR_REGEX, "", cell)) + 1)
        columns = [Column("", min(c, 40), str) for c in columns]
        # make the last column take up the rest of the space
        columns[-1].max_width = 0

        list_box = Table(self.state, self.config.settings, None, "selection")
        list_box.header_enabled = False
        list_box.value = index
        list_box.columns = [Column("ID", 0, int, enabled=False)] + columns
        list_box.set_rows(
            [[str(i)] + row for i, row in enumerate(answers)],
            [[i] + row for i, row in enumerate(answers)],
        )
        text_input = None

        def on_search():
            if text_input is None:
                return
            self.state.filter = text_input.value
            list_box.do_filter()

        text_input = Text(on_change=on_search, name="search")
        if search_string is not None:
            text_input.value = search_string

        def on_submit():
            if list_box.value is not None:
                self.state.filter = ""
                row = list_box.get_selected()
                callback([str(v) for v in row[1][1:]] if row is not None else None)
            else:
                self.cache.notification = "No option was selected, please select one"
                self._needs_build = True

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
            Button(
                "Continue", lambda: (callback(), setattr(self, "_needs_build", True))
            ),
            1,
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
        api_url_input = Text(label="API URL:", name="api_url")
        api_url_input.value = DEFAULT_API_URL

        self._on_submit = lambda: self.set_api_key(
            text.value.strip(), api_url_input.value.strip()
        )
        self.layout.add_widget(text, 1)
        self.layout.add_widget(api_url_input, 1)

        self.footer.add_widget(
            Button(
                "Continue",
                lambda: self.set_api_key(
                    text.value.strip(), api_url_input.value.strip()
                ),
            ),
            1,
        )
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

        time_zone = get_timezone(self.config.settings)

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
        sources = (
            self.recordpool.sources.get(self.state.org_uid, [])
            if self.recordpool and self.state.org_uid
            else []
        )
        source = next((s for s in sources if s["uid"] == self.state.source_uid), {})
        source_time = source.get("valid_from", None)
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

        last_seen_time = source.get("last_stored_chunk_end_time", None)
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
                    f"Duration to pre-load: +/-{duration.value} minutes"
                )

        self.layout.add_widget(Padding(), 1)
        duration = Text(
            label="Duration:", validator=num_validator, on_change=on_change2
        )
        duration.value = str(self.cache.duration.total_seconds() / 60)

        selected_duration = timedelta(minutes=float(duration.value))

        self.layout.add_widget(duration, 1)

        def set_start_time():
            self.state.time = datetime.combine(date.value, time_widget.value).replace(
                tzinfo=time_zone
            )
            self.cache.duration = selected_duration
            self._needs_build = True

        self.footer.add_widget(
            Button(
                "Continue",
                set_start_time,
            ),
            1,
        )

        def back():
            self.state.source_uid = None
            self._needs_build = True

        self.footer.add_widget(Button("Back", back), 2)

    def load_data(self, load_type: str) -> None:
        """Loads a type of data from the API"""

        def thread_target():
            assert self.recordpool is not None

            try:
                if load_type == "orgs":
                    self.recordpool.load_orgs(force_reload=self.cache.force_reload)
                    if len(self.recordpool.orgs) == 0:
                        self.cache.failure_reason = (
                            "No organizations found! This is unexpected; try"
                            "logging into your account on the website."
                        )
                if load_type == "sources":
                    assert self.state.org_uid is not None
                    self.recordpool.load_sources(
                        self.state.org_uid, force_reload=self.cache.force_reload
                    )
                    self.recordpool.load_clusters(
                        self.state.org_uid, force_reload=self.cache.force_reload
                    )
                    self.cache.force_reload = False
                    if (
                        self.state.org_uid not in self.recordpool.sources
                        and self.state.org_uid not in self.recordpool.clusters
                    ):
                        self.cache.failure_reason = (
                            "Failed to load any machines or clusters"
                        )
            except APIError as exc:
                self.cache.failure_reason = str(exc)

            self._needs_build = True
            self._screen.force_update()
            self.cache.force_reload = False

        self.thread = Thread(target=thread_target)
        self.thread.start()

    def build_confirm(self, question: str, callback: Callable[[bool], None]) -> None:
        """Create a simple layout to ask a yes/no question"""
        self.layout.add_widget(Label(question, align="^"), 1)
        self.footer.add_widget(Button("Yes", lambda: callback(True)), 1)
        self.footer.add_widget(Button("No", lambda: callback(False)), 2)

    def format_source(self, source) -> List[str]:
        """Format a source for display"""
        try:
            last_stored_time = (
                datetime.strptime(
                    source["last_stored_chunk_end_time"],
                    "%Y-%m-%dT%H:%M:%SZ",
                )
                .replace(tzinfo=timezone.utc)
                .astimezone(tz=get_timezone(self.config.settings))
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

    def set_api_key(self, key: str, api_url: str = DEFAULT_API_URL) -> None:
        """Set the organization"""

        self.cache.api_key = key
        self.recordpool = RecordPool(Secret(key, api_url), self.args.output)

        self._needs_build = True

    def quit(self) -> None:
        """Quit the application"""
        self.state.exit_reason = ExitReason.QUIT
        raise StopApplication("User quit")
