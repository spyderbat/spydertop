#
# model.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
The main app model for the application, containing all logic necessary
to fetch and cache data from the Spyderbat API
"""

import threading
import json
import gzip
from math import nan
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, NewType, Optional, Set, List, Any, Tuple, Union
import uuid

import spyderbat_api
from spyderbat_api.api import (
    source_data_api,
    org_api,
    source_api,
)
import urllib3
from urllib3.exceptions import MaxRetryError

from spydertop.config import Config
from spydertop.cursorlist import CursorList
from spydertop.utils import API_LOG_TYPES, TimeSpanTracker, get_timezone, log

# custom types for data held in the model
Tree = NewType("Tree", Dict[str, Tuple[bool, Optional["Tree"]]])
RecordInternal = NewType(
    "RecordInternal",
    Dict[
        str, Union[str, int, float, Dict[str, "RecordInternal"], List["RecordInternal"]]
    ],
)
Record = NewType("Record", Dict[str, RecordInternal])


class AppModel:  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """
    The main app model for the application, containing all logic necessary
    to asynchronously fetch and cache data from the Spyderbat API. It also
    provides a collection of quick methods to get data from the model.
    """

    loaded: bool = False
    failed: bool = False
    failure_reason: str = ""
    progress: float = 0
    config: Config
    columns_changed: bool = False
    thread: Optional[threading.Thread] = None
    api_client: Optional[spyderbat_api.ApiClient] = None

    # cache for arbitrary states, registered through
    # register_state
    _cache: Dict[str, Dict[str, Any]] = {}

    _timestamp: Optional[float]
    _time_elapsed: float = 0
    _last_good_timestamp: float = None
    _time_span_tracker: TimeSpanTracker = TimeSpanTracker()
    _session_id: str
    _http_client: urllib3.PoolManager

    _records: Dict[str, Dict[str, Record]] = {
        "model_process": {},
        "model_session": {},
        "model_connection": {},
        "model_machine": {},
        "model_listening_socket": {},
        "event_redflag": {},
    }
    _tree: Optional[Tree] = None
    _top_ids: Set[str] = set()
    _tops: CursorList
    _machine: Optional[Record] = None
    _meminfo: Optional[Dict[str, int]] = None

    def __init__(self, config: Config) -> None:
        self.config = config
        self._timestamp = None
        self._session_id = uuid.uuid4().hex
        self._http_client = urllib3.PoolManager()

        self._tops = CursorList("time", [], self._timestamp)

    def __del__(self):
        if self.thread:
            self.thread.join()
        if self.api_client:
            self.api_client.close()

    def init(self) -> None:
        """Initialize the model, loading data from the source. Requires config to be complete"""
        self._timestamp = (
            self.config.start_time.astimezone(timezone.utc).timestamp()
            if self.config.start_time
            else None
        )

        if self.api_client is None:
            self.init_api()

        if not self.config.is_complete:
            # ideally, this would never happen, as the configuration screen
            # should complete the configuration before the model is initialized
            raise Exception("Configuration is incomplete, cannot load data")

        def guard():
            try:
                self.load_data(self._timestamp, self.config.start_duration)
            except Exception as exc:  # pylint: disable=broad-except
                self.fail("An exception occurred while loading data")
                log.traceback(exc)

        thread = threading.Thread(target=guard)
        thread.start()
        self.thread = thread

        # if the output file is gzipped, open it with gzip
        if self.config.output and self.config.output.name.endswith(".gz"):
            self.config.output = gzip.open(self.config.output.name, "wt")

    def init_api(self) -> None:
        """Initialize the API client"""
        if isinstance(self.config.input, str):
            configuration = spyderbat_api.Configuration(
                access_token=self.config.api_key, host=self.config.input
            )

            self.api_client = spyderbat_api.ApiClient(configuration)

    def load_data(
        self,
        timestamp: float,
        duration: timedelta = None,
        before=timedelta(seconds=120),
    ) -> None:
        """Load data from the source, either the API or a file, then process it"""
        self.loaded = False
        if duration is None:
            duration = self.config.start_duration
        log.info(f"Loading data for time: {timestamp} and duration: {duration}")
        self.loaded = False
        self.progress = 0.0

        source = self.config.input
        lines = []

        if isinstance(source, str):
            # url, load data from api

            api_instance = source_data_api.SourceDataApi(self.api_client)
            input_data = {
                # request data from a bit earlier, so that the information is properly filled out
                "st": timestamp - before.total_seconds() + 30,
                "et": timestamp + duration.total_seconds(),
                "src": self.config.machine,
            }

            # we need more than one event_top record, so a buffer of 30 seconds is used
            # to make sure the data is available
            self._time_span_tracker.add_time_span(
                input_data["st"] + 30, input_data["et"]
            )

            log.log(self._time_span_tracker.times)

            try:
                log.info("Querying api for spydergraph records")
                self.progress = 0.1
                log.debug(
                    {"org_uid": self.config.org, "dt": "spydergraph", **input_data}
                )
                api_response: urllib3.HTTPResponse = api_instance.src_data_query_v2(
                    org_uid=self.config.org,
                    dt="spydergraph",
                    **input_data,
                    _preload_content=False,
                )
                lines += api_response.data.split(b"\n")

                self.progress = 0.5

                log.info("Querying api for resource usage records")
                log.debug({"org_uid": self.config.org, "dt": "htop", **input_data})
                api_response = api_instance.src_data_query_v2(
                    org_uid=self.config.org,
                    dt="htop",
                    **input_data,
                    _preload_content=False,
                )
                lines += api_response.data.split(b"\n")
                self.log_api(
                    API_LOG_TYPES["loaded_data"],
                    {
                        "count": len(lines),
                        "source_id": input_data["src"],
                        "start_time": input_data["st"],
                        "end_time": input_data["et"],
                    },
                )
            except spyderbat_api.ApiException as exc:
                self.fail(f"Loading data from the api failed with reason: {exc.reason}")
                log.traceback(exc)
                log.debug(
                    f"""\
Debug info:
    URL requested: {source}/api/v1/source/query/
    Method: POST
    Input data: {input_data}
    Status code: {exc.status}
    Reason: {exc.reason}
    Body: {exc.body}\
                            """
                )
                return
            except MaxRetryError as exc:
                self.fail(
                    f"There was an issue trying to connect to the API. Is the url {source} correct?"
                )
                log.traceback(exc)
                return
            except Exception as exc:  # pylint: disable=broad-except
                self.fail("An exception occurred when trying to load from the api.")
                log.traceback(exc)
                log.debug(
                    f"""\
Debug info:
    URL requested: {source}/api/v1/source/query/
    Method: POST
    Input data: {input_data}\
                            """
                )
                return

        else:
            # file, read in records and parse
            log.info(f"Reading records from input file: {source.name}")

            lines = source.readlines()
            if len(lines) == 0:
                # file was most likely already read
                self.fail(
                    "The current time is unloaded, but input is from a file. \
No more records can be loaded."
                )
                return
            self.log_api(
                API_LOG_TYPES["loaded_data"], {"source_id": "file", "count": len(lines)}
            )

        if self.config.output:
            # if lines is still binary, convert to text
            if len(lines) > 0 and isinstance(lines[0], bytes):
                lines = [line.decode("utf-8") for line in lines]
            self.config.output.write("\n".join([l.rstrip() for l in lines]))

        self._process_records(lines)

    def _process_records(self, lines: List[str]) -> None:
        """Process the loaded records, parsing them and adding them to the model"""
        log.info("Parsing records")
        self.progress = 0.0

        if not lines or len(lines) == 0 or lines[0] == "" or lines[0] == b"":
            self.fail(
                "Loading was successful, but no records were found. \
Are you asking for the wrong time?"
            )
            return

        event_tops = []

        for i, line in enumerate(lines):
            self.progress = i / len(lines)

            # suppress errors for empty lines
            if line.strip() == "":
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                log.err(f"Error decoding record: {line}")
                log.traceback(exc)
                continue

            if record["schema"].startswith("event_top"):
                if record["id"] in self._top_ids:
                    continue
                self._top_ids.add(record["id"])
                event_tops.append(record)
            else:
                short_schema = record["schema"].split(":")[0]

                if short_schema not in self._records:
                    continue

                # only save the most recent version of each record
                if record["id"] not in self._records[short_schema]:
                    self._records[short_schema][record["id"]] = record
                else:
                    if (
                        record["time"]
                        > self._records[short_schema][record["id"]]["time"]
                    ):
                        self._records[short_schema][record["id"]] = record

        self._tops.extend(event_tops)

        self.rebuild_tree()

        log.info("Finished parsing records")
        self.loaded = True
        self._fix_state()

    def _correct_meminfo(self) -> None:
        """Correct the memory information for the current time"""

        # memory is only non-null every 15 seconds, so work back to the
        # previous time that has memory information
        new_meminfo = None
        index = 0
        while not new_meminfo and self._tops.is_valid(index):
            new_meminfo = self._tops[index]["memory"]
            index -= 1
        self._meminfo = new_meminfo

    def _fix_state(self) -> None:
        """
        Fix the state of the model after loading. This includes:
            - correcting the memory information
            - updating time_elapsed
            - updating the machine
        """
        try:
            self._tops.update_cursor(self._timestamp)
            # if the time is None, there was no specified time, so
            # go back to the beginning of the records
            if self.timestamp is None:
                self.recover("reload")
                return

            if not self._time_span_tracker.is_loaded(self._timestamp) and isinstance(
                self.config.input, str
            ):
                # this is currently disabled due to errors
                #
                # # load data for a time farther away from the loaded
                # # time if self._timestamp is close
                # # this is to avoid loading data that is not needed
                # if len(self._tops.data) == 0:
                #     closest_time = self._timestamp
                #     offset = 0
                # # make sure to leave a buffer of 2 event_tops
                # elif not self._tops.is_valid(-2):
                #     closest_time = self._tops.data[2]["time"]
                #     offset = -298
                # else:
                #     closest_time = self._tops[0]["time"]
                #     offset = +298

                # time_to_load = (
                #     self._timestamp
                #     if abs(self._timestamp - closest_time) > 300
                #     else closest_time + offset
                # )
                time_to_load = self._timestamp

                thread = threading.Thread(
                    target=lambda: self.load_data(
                        time_to_load, timedelta(seconds=300), timedelta(seconds=300)
                    )
                )
                thread.start()
                self.thread = thread
                return

            # correct the memory information
            self._correct_meminfo()

            if self._tops.is_valid(0) and self._tops.is_valid(-1):
                # update the time elapsed
                self._time_elapsed = float(self._tops[0]["time"]) - float(
                    self._tops[-1]["time"]
                )
            else:
                self._time_elapsed = nan

            # update the machine
            # there should only be one machine, so we can just use the first one
            if len(self._records["model_machine"]) == 0:
                log.warn("No machine found in the records")
                self._machine = None
            else:
                self._machine = list(self._records["model_machine"].values())[0]
            if len(self._records["model_machine"]) > 1:
                log.warn("More than one machine was found in the input data.")

        except Exception as exc:  # pylint: disable=broad-except
            log.err("Exception occurred while fixing state:")
            log.traceback(exc)
            self.fail(
                f"""\
The time {self.time} is invalid, \
not enough information could be loaded.\
"""
            )

    @staticmethod
    def _make_branch(
        rec_id: str, processes_w_children: Dict[str, List], enabled: bool
    ) -> Tuple[bool, Tree]:
        """Recursively create a tree branch for a process"""
        # branches are tuples of (enabled, {child id: branch})
        if processes_w_children[rec_id] == []:
            return None
        branch = (enabled, {})
        for child in processes_w_children[rec_id]:
            branch[1][child] = AppModel._make_branch(
                child, processes_w_children, enabled
            )
        return branch

    def get_orgs(self) -> Optional[List[org_api.Org]]:
        """Fetch a list of organization for this api_key"""
        api_instance: org_api.OrgApi = org_api.OrgApi(self.api_client)

        try:
            orgs = api_instance.org_list(_preload_content=False)
            orgs = json.loads(orgs.data)
            self.log_api(API_LOG_TYPES["orgs"], {"count": len(orgs)})
            return orgs
        except spyderbat_api.ApiException as exc:
            self.fail(f"Exception when calling OrgApi: {exc.status} - {exc.reason}")
            log.traceback(exc)
            return None
        except Exception as exc:  # pylint: disable=broad-except
            self.fail("Exception when calling OrgApi.")
            log.traceback(exc)
            return None

    def get_sources(
        self, page: int = None, page_size: int = None, uid: str = None
    ) -> Optional[List[Dict]]:
        """Fetch a list of sources for this api_key"""
        # this tends to take a long time for large organizations
        # because the returned json is all one big string
        #
        # we tell the api library to give us the raw response
        # and then parse it ourselves to save some time
        api_instance: source_api.SourceApi = source_api.SourceApi(self.api_client)

        try:
            kwargs = {}
            if page is not None:
                log.warn("Paging of sources is not currently supported by the API.")
                kwargs["page"] = page
            if page_size is not None:
                log.warn("Paging of sources is not currently supported by the API.")
                kwargs["page_size"] = page_size
            if uid is not None:
                kwargs["agent_uid_equals"] = uid
            sources: urllib3.HTTPResponse = api_instance.src_list(
                org_uid=self.config.org,
                _preload_content=False,
                **kwargs,
            )
            sources: List = json.loads(sources.data)
            self.log_api(API_LOG_TYPES["sources"], {"count": len(sources)})

            return sources
        except Exception as exc:  # pylint: disable=broad-except
            self.fail(f"Exception when calling SourceApi: {exc}")
            log.traceback(exc)
            return None

    def log_api(self, name: str, data: Dict[str, Any]) -> None:
        """Send logs to the spyderbat internal logging API"""
        if not isinstance(self.config.input, str):
            url = "https://api.spyderbat.com"
        else:
            url = self.config.input
        new_data = {
            "name": name,
            "application": "spydertop",
            "orgId": self.config.org,
            "session_id": self._session_id,
            **data,
        }

        try:
            headers = {
                "Content-Type": "application/json",
            }
            if self.config.api_key is not None:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            # send the data to the API
            response = self._http_client.request(
                "POST",
                f"{url}/api/v1/_/log",
                headers=headers,
                body=json.dumps(new_data),
            )
            # check the response
            if response.status != 200:
                # don't fail noisily, the user doesn't care about the log
                log.debug(
                    f"Logging API returned status {response.status} with message: {response.data}"
                )
        except Exception as exc:  # pylint: disable=broad-except
            log.debug("Exception when logging to API")
            log.traceback(exc)

    def submit_feedback(self, feedback: str) -> None:
        """Submit feedback to the spyderbat internal logging API"""
        self.log_api(API_LOG_TYPES["feedback"], {"message": feedback})
        self.config["has_submitted_feedback"] = True

    def get_value(self, key, previous=False) -> Any:
        """Provides the specified field on the most recent or the previous
        event_top_data record"""
        index = 0 if not previous else -1
        if not self.tops_valid():
            return None
        return self._tops[index][key]

    def get_top_processes(
        self,
    ) -> Tuple[Dict[str, Union[str, int]], Dict[str, Union[str, int]]]:
        """Get the resource usage records for the processes at the current time"""
        if not self.tops_valid():
            return None, None
        return (self._tops[-1]["processes"], self._tops[0]["processes"])

    def rebuild_tree(self) -> None:
        """Create a tree structure for the processes, based on the puid and ppuid"""
        processes_w_children = {}
        processes = self.processes

        # the two main root processes are the kernel and the init process
        # we will use these as the root of the tree
        kthreadd = None
        init = None

        for proc in processes.values():
            try:
                if proc["id"] not in processes_w_children:
                    processes_w_children[proc["id"]] = []
                if (
                    proc["ppuid"] is not None
                    and proc["ppuid"] not in processes_w_children
                ):
                    processes_w_children[proc["ppuid"]] = []
                if proc["ppuid"] is not None:
                    processes_w_children[proc["ppuid"]].append(proc["id"])
                if proc["pid"] == 1:
                    init = proc["id"]
                if proc["pid"] == 2:
                    kthreadd = proc["id"]
            except KeyError as exc:
                log.err(f"Process {exc} is missing.")
                log.traceback(exc)
                continue

        self._tree = {}

        # add the root processes to the tree
        if kthreadd:
            self._tree[kthreadd] = AppModel._make_branch(
                kthreadd, processes_w_children, not self.config["collapse_tree"]
            )
            # root processes are always enabled
            self._tree[kthreadd] = (True, self._tree[kthreadd][1])
        if init:
            self._tree[init] = AppModel._make_branch(
                init, processes_w_children, not self.config["collapse_tree"]
            )
            self._tree[init] = (True, self._tree[init][1])

    def recover(self, method="revert") -> None:
        """Recover the state of the model, using the given method.
        The method can be one of:
            - "revert": revert to the last loaded time
            - "reload": go back to the earliest valid time
            - "retry": try to load the data again, using the input source"""

        log.info(f"Attempting to recover state using {method}")

        # the user probably wants to get their bearings
        # before moving time again
        self.config["play"] = False

        # we can only revert if we have a previous time
        if method == "revert" and self._last_good_timestamp is None:
            method = "reload"

        try:
            if method == "revert":
                log.info("Reverting to last good state.")
                self.timestamp = self._last_good_timestamp

            elif method == "reload":
                log.info("Reloading from beginning of records.")
                index = 1  # make sure there is a previous index
                new_meminfo = None
                while not new_meminfo and index < len(self._tops.data):
                    new_meminfo = self._tops.data[index]["memory"]
                    index += 1
                if index < len(self._tops.data):
                    self.timestamp = self._tops.data[index]["time"]
                elif len(self._tops.data) > 0:
                    self.timestamp = self._tops.data[0]["time"]
                self._meminfo = new_meminfo

            elif method == "retry":
                log.info("Retrying loading from the API.")
                self.load_data(self._timestamp)

            elif isinstance(method, float):
                log.info("Loading from custom time.")
                self.timestamp = method

            # sanity check
            if not self.is_valid():
                self.fail("Recovering failed to find a valid time.")
                log.debug(
                    f"Time: {self._tops.cursor}, # of Records: {len(self._tops.data)}"
                )
                return

            self.failed = False
            self.failure_reason = ""
            self.loaded = True
        except Exception as exc:  # pylint: disable=broad-except
            log.err("Exception occurred while recovering:")
            log.traceback(exc)
            self.fail("An exception occurred while attempting to recover.")

    def fail(self, reason: str) -> None:
        """Put the model in a failure state"""
        log.err(f"Model entered failure state with: {reason}")
        self.failed = True
        self.failure_reason = reason

    def tops_valid(self) -> bool:
        """Return whether the event top data is valid for this time"""
        # the slowest data should appear is once per 15 seconds
        grace_period = 16
        return (
            self._tops.is_valid(0)
            and self._tops.is_valid(-1)
            and abs(self._tops[0]["time"] - self._timestamp) < grace_period
        )

    def use_state(
        self, name: str, initial_value: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Callable]:
        """Manage state similar to a React state; this is used to retain
        information after resize"""
        if name not in self._cache:
            self._cache[name] = initial_value

        def set_state(**kwargs):
            self._cache[name].update(kwargs)

        return self._cache[name], set_state

    def is_valid(self) -> bool:
        """Determine if there is enough information
        loaded to be able to use the data"""
        return (
            self.loaded
            and self._timestamp is not None
            and (
                self._time_span_tracker.is_loaded(self._timestamp)
                or not isinstance(self.config.input, str)
            )
        )

    def clear(self) -> None:
        """Remove all loaded data from the model"""
        self._timestamp = None
        self._time_elapsed = 0
        self._last_good_timestamp = None
        self._time_span_tracker = TimeSpanTracker()

        self._records = {
            "model_process": {},
            "model_session": {},
            "model_connection": {},
            "model_machine": {},
            "model_listening_socket": {},
            "event_redflag": {},
        }
        self._tree = None
        self._top_ids = set()
        self._tops = CursorList("time", [], self._timestamp)
        self._machine = None
        self._meminfo = None

        self.loaded = False
        self.failed = False
        self.failure_reason = ""
        self.progress = 0
        self.columns_changed = False

    def is_loaded(self, timestamp: float) -> bool:
        """Return whether the model has loaded data for the given time"""
        return self._time_span_tracker.is_loaded(timestamp) or not isinstance(
            self.config.input, str
        )

    @property
    def state(self) -> str:
        """The current status of the model"""
        if log.log_level == log.DEBUG:
            try:
                return log.lines[-1]
            except IndexError:
                pass
        return f"Time: {self.time}"

    @property
    def time_elapsed(self) -> float:
        """The time elapsed between the last event_top_data record and the current one"""
        return (
            self._time_elapsed if self._time_elapsed != 0 and self.tops_valid() else nan
        )

    @property
    def memory(self) -> Dict[str, int]:
        """The most recent memory usage data"""
        if not self.tops_valid():
            return None
        return self._meminfo

    @property
    def machine(self) -> Optional[Record]:
        """The most recent machine data"""
        return self._machine

    @property
    def processes(self) -> Dict[str, Record]:
        """All currently loaded process records"""
        return self._records["model_process"]

    @property
    def flags(self) -> Dict[str, Record]:
        """All currently loaded flag records"""
        return self._records["event_redflag"]

    @property
    def listening(self) -> Dict[str, Record]:
        """All currently loaded listening socket records"""
        return self._records["model_listening_socket"]

    @property
    def connections(self) -> Dict[str, Record]:
        """All currently loaded connection records"""
        return self._records["model_connection"]

    @property
    def sessions(self) -> Dict[str, Record]:
        """All currently loaded session records"""
        return self._records["model_session"]

    @property
    def tree(self) -> Tree:
        """A tree representation of all processes, in the format:

        {
            "id": (
                enabled,
                {subtree} or None
            ),
        }
        """
        if self._tree is None:
            raise Exception("The tree is not yet loaded.")
        return self._tree

    # time properties
    @property
    def time(self) -> Optional[datetime]:
        """The current time, as a datetime object"""
        if self._timestamp is None:
            return None
        return datetime.fromtimestamp(self._timestamp, tz=timezone.utc).astimezone(
            get_timezone(self)
        )

    @property
    def timestamp(self) -> float:
        """The current time, as a float"""
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value: float) -> None:
        # set the current time and fix the state
        self._timestamp = value
        self._fix_state()
        if not self.failed:
            self._last_good_timestamp = self._timestamp
