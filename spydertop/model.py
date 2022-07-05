#
# model.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc.  All rights reserved.
#

"""
The main app model for the application, containing all logic necessary
to fetch and cache data from the Spyderbat API
"""

from math import nan
import threading
import json
import gzip
from datetime import datetime, timedelta
from typing import Dict, NewType, Optional, Set, List, Any, Tuple, Union

import sbapi
from sbapi.api import source_data_api
from sbapi.model.src_data_query_input import SrcDataQueryInput

from spydertop.config import Config
from spydertop.cursorlist import CursorList
from spydertop.utils import log

# custom types for data held in the model
Tree = NewType("Tree", Dict[str, Tuple[bool, Optional["Tree"]]])
RecordInternal = NewType(
    "RecordInternal",
    Dict[
        str, Union[str, int, float, Dict[str, "RecordInternal"], List["RecordInternal"]]
    ],
)
Record = NewType("Record", Dict[str, RecordInternal])


class AppModel:
    """
    The main app model for the application, containing all logic necessary
    to asynchronously fetch and cache data from the Spyderbat API. It also
    provides a collection of quick methods to get data from the model.
    """

    loaded: bool = False
    failed: bool = False
    failure_reason: str = ""
    progress: float = 0
    thread: Optional[threading.Thread]
    config: Config
    columns_changed: bool = False

    _timestamp: float
    _time_elapsed: float = 0
    _last_good_timestamp: float = None

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
    _machine: Record = None
    _meminfo: Optional[Dict[str, int]] = None

    def __init__(self, config: Config) -> None:
        self.config = config
        self._timestamp = config.start_time.timestamp()

        self._tops = CursorList("time", [], self._timestamp)

    def init(self) -> None:
        """Initialize the model, loading data from the source"""

        def guard():
            try:
                self.load_data(self._timestamp, self.config.start_duration)
            except Exception as e:
                self.fail("An exception occurred while loading data")
                log.traceback(e)

        self.thread = threading.Thread(target=guard)
        self.thread.start()

        # if the output file is gzipped, open it with gzip
        if self.config.output and self.config.output.name.endswith(".gz"):
            self.config.output = gzip.open(self.config.output.name, "wt")

    def load_data(
        self, time: float, duration: timedelta = None, before=timedelta(seconds=120)
    ) -> None:
        """Load data from the source, either the API or a file, then process it"""
        self.loaded = False
        if duration is None:
            duration = self.config.start_duration
        log.info(f"Loading data for time: {time} and duration: {duration}")
        self.loaded = False
        self.progress = 0.0

        source = self.config.input
        lines = []

        if isinstance(source, str):
            # url, load data from api
            configuration = sbapi.Configuration(
                access_token=self.config.api_key, host=source
            )

            with sbapi.ApiClient(configuration) as api_client:
                api_instance = source_data_api.SourceDataApi(api_client)
                input_data = SrcDataQueryInput(
                    data_type="spydergraph",
                    # request data from a bit earlier, so that the information is properly filled out
                    start_time=time - before.total_seconds(),
                    end_time=time + duration.total_seconds(),
                    org_uid=self.config.org,
                    src_uid=self.config.source,
                )

                try:
                    log.info("Querying api for spydergraph records")
                    self.progress = 0.1
                    api_response = api_instance.src_data_query(
                        src_data_query_input=input_data
                    )
                    lines += api_response.split("\n")

                    input_data.data_type = "htop"
                    self.progress = 0.5

                    log.info("Querying api for resource usage records")
                    api_response = api_instance.src_data_query(
                        src_data_query_input=input_data
                    )
                    lines += api_response.split("\n")
                except sbapi.ApiException as e:
                    self.fail(
                        f"Loading data from the api failed with reason: {e.reason}"
                    )
                    log.traceback(e)
                    log.log(
                        f"""\
Debug info:
    URL requested: {source}/api/v1/source/query/
    Method: POST
    Status code: {e.status}
    Reason: {e.reason}
    Body: {e.body}\
                            """
                    )
                    return
                except Exception as e:
                    self.fail("An exception occurred when trying to load from the api.")
                    log.traceback(e)
                    log.log(
                        f"""\
Debug info:
    URL requested: {source}/api/v1/source/query/
    Method: POST\
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
                    "The current time is unloaded, but input is from a file. No more records can be loaded."
                )
                log.log(
                    f"Time was changed to {self.time}, but this is not available in the input file: {source.name}"
                )
                return

        if self.config.output:
            self.config.output.write("\n".join([l.rstrip() for l in lines]))

        self._process_records(lines)

    def _process_records(self, lines: List[str]) -> None:
        """Process the loaded records, parsing them and adding them to the model"""
        log.info("Parsing records")
        self.progress = 0.0

        if not lines or len(lines) == 0 or lines[0] == "":
            self.fail(
                "Loading was successful, but no records were found. Are you asking for the wrong time?"
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
            except json.JSONDecodeError as e:
                log.err(f"Error decoding record: {line}")
                log.traceback(e)
                continue

            if record["schema"].startswith("event_top"):
                if record["id"] in self._top_ids:
                    log.log(f"Skipping duplicate top id: {record['id']}")
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
            # check if the given time is not loaded
            # i.e. the closest time is more than 2 seconds away
            if (
                not self._tops.is_valid(0)
                or abs(self._tops[0]["time"] - self.timestamp) > 2
            ):
                # if the time is 0, there was no specified time, so
                # go back to the beginning of the records
                if self.timestamp == 0.0:
                    self.recover("reload")
                    return

                if not isinstance(self.config.input, str):
                    # we are getting input from a file
                    self.fail(
                        f"The time {datetime.fromtimestamp(self.timestamp)} is not available in the input file."
                    )
                    return

                # load data for a time farther away from the loaded
                # time if self._timestamp is close
                # this is to avoid loading data that is not needed
                if len(self._tops.data) == 0:
                    closest_time = self._timestamp
                    offset = 0
                elif not self._tops.is_valid(0):
                    closest_time = self._tops.data[0]["time"]
                    offset = -298
                else:
                    closest_time = self._tops[0]["time"]
                    offset = +298

                time_to_load = (
                    self._timestamp
                    if abs(self._timestamp - closest_time) > 300
                    else closest_time + offset
                )

                log.log(
                    f"Loading data from API since tops was invalid. Time to load: {time_to_load}"
                )

                self.thread = threading.Thread(
                    target=lambda: self.load_data(
                        time_to_load, timedelta(seconds=300), timedelta(seconds=300)
                    )
                )
                self.thread.start()
                return

            # correct the memory information
            self._correct_meminfo()

            # update the time elapsed
            self._time_elapsed = float(self._tops[0]["time"]) - float(
                self._tops[-1]["time"]
            )

            # update the machine
            # there should only be one machine, so we can just use the first one
            if len(self._records["model_machine"]) == 0:
                self.fail("No machine records were found.")
                return
            self._machine = [m for m in self._records["model_machine"].values()][0]
            if len([m for m in self._records["model_machine"]]) > 1:
                log.warn("More than one machine was found in the input data.")

        except Exception as e:
            log.err(f"Exception occurred while fixing state:")
            log.traceback(e)
            self.fail(
                f"The time {datetime.fromtimestamp(self.timestamp)} is invalid, not enough information could be loaded."
            )

    @staticmethod
    def _make_branch(
        id: str, procs_w_children: Dict[str, List], enabled: bool
    ) -> Tuple[bool, Tree]:
        """Recursively create a tree branch for a process"""
        # branches are tuples of (enabled, {child id: branch})
        if procs_w_children[id] == []:
            return None
        branch = (enabled, {})
        for child in procs_w_children[id]:
            branch[1][child] = AppModel._make_branch(child, procs_w_children, enabled)
        return branch

    def get_value(self, key, previous=False) -> Any:
        """Provides the specified field on the most recent or the previous
        event_top_data record"""
        index = 0 if not previous else -1
        return self._tops[index][key]

    def get_top_processes(
        self,
    ) -> Tuple[Dict[str, Union[str, int]], Dict[str, Union[str, int]]]:
        """Get the resource usage records for the processes at the current time"""
        return (self._tops[-1]["processes"], self._tops[0]["processes"])

    def rebuild_tree(self) -> None:
        """Create a tree structure for the processes, based on the puid and ppuid"""
        procs_w_children = {}
        processes = self.processes

        # the two main root processes are the kernel and the init process
        # we will use these as the root of the tree
        kthreadd = None
        init = None

        for p in processes.values():
            try:
                if p["id"] not in procs_w_children:
                    procs_w_children[p["id"]] = []
                if p["ppuid"] is not None and p["ppuid"] not in procs_w_children:
                    procs_w_children[p["ppuid"]] = []
                if p["ppuid"] is not None:
                    procs_w_children[p["ppuid"]].append(p["id"])
                if p["pid"] == 1:
                    init = p["id"]
                if p["pid"] == 2:
                    kthreadd = p["id"]
            except KeyError as e:
                log.err(f"Process {e} is missing.")
                log.traceback(e)
                continue

        self._tree = {}

        # add the root processes to the tree
        if kthreadd:
            self._tree[kthreadd] = AppModel._make_branch(
                kthreadd, procs_w_children, not self.config["collapse_tree"]
            )
            # root processes are always enabled
            self._tree[kthreadd] = (True, self._tree[kthreadd][1])
        if init:
            self._tree[init] = AppModel._make_branch(
                init, procs_w_children, not self.config["collapse_tree"]
            )
            self._tree[init] = (True, self._tree[init][1])

    def recover(self, method="revert") -> None:
        """Recover the state of the model, using the given method.
        The method can be one of:
            - "revert": revert to the last loaded time
            - "reload": go back to the earliest valid time
            - "retry": try to load the data again, using source"""

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
                starting_time = self._tops.data[index]["time"]
                self._meminfo = new_meminfo
                self.timestamp = starting_time

                log.log(f"Using {starting_time} as new time")

            elif method == "retry":
                log.info("Retrying loading from the API.")
                self.load_data(self._timestamp)

            elif isinstance(method, float):
                log.info("Loading from custom time.")
                self.timestamp = method

            # sanity check
            if not self.is_valid():
                self.fail("Recovering failed to find a valid time.")
                log.log(
                    f"Time: {self._tops.cursor}, # of Records: {len(self._tops.data)}"
                )
                return

            self.failed = False
            self.failure_reason = ""
            self.loaded = True
        except Exception as e:
            log.err(f"Exception occurred while recovering:")
            log.traceback(e)
            self.fail("An exception occurred while attempting to recover.")

    def fail(self, reason: str) -> None:
        """Put the model in a failure state"""
        log.err(f"Model entered failure state with: {reason}")
        self.failed = True
        self.failure_reason = reason

    def is_valid(self) -> bool:
        """Determine if there is enough information
        loaded to be able to use the data"""
        return (
            self.loaded
            and self._tops.is_valid(-1)
            and self._tops.is_valid(2)  # add some buffer in front
            and not abs(self._tops[0]["time"] - self._timestamp) > 2
            and self._meminfo is not None
            and self._machine is not None
        )

    @property
    def state(self) -> str:
        """The current status of the model"""
        if log.log_level == log.DEBUG:
            try:
                return log.lines[-1]
            except:
                pass
        return f"Time: {self.time}"

    @property
    def time_elapsed(self) -> float:
        """The time elapsed between the last event_top_data record and the current one"""
        return self._time_elapsed if self._time_elapsed != 0 else nan

    @property
    def memory(self) -> Dict[str, int]:
        """The most recent memory usage data"""
        return self._meminfo

    @property
    def machine(self) -> Dict[str, Record]:
        """The most recent machine data"""
        if self._machine is None:
            raise Exception("No machine record was loaded.")
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
    def time(self) -> datetime:
        """The current time, as a datetime object"""
        return datetime.fromtimestamp(self._timestamp)

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
