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

from itertools import groupby
import threading
import gzip
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional, List, Any, Tuple
import uuid

import orjson
import urllib3

from spydertop.config import Config
from spydertop.recordpool import RecordPool
from spydertop.utils import get_timezone, log, sum_element_wise
from spydertop.utils.types import APIError, Record, Tree
from spydertop.utils.cursorlist import CursorList
from spydertop.constants import API_LOG_TYPES


class AppModel:  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """
    The main app model for the application, containing all logic necessary
    to asynchronously fetch and cache data from the Spyderbat API. It also
    provides a collection of quick methods to get data from the model.
    """

    failed: bool = False
    failure_reason: str = ""
    config: Config
    columns_changed: bool = False
    thread: Optional[threading.Thread] = None
    selected_machine: Optional[str] = None

    # cache for arbitrary states, registered through
    # register_state
    _cache: Dict[str, Dict[str, Any]] = {}

    _timestamp: Optional[float] = None
    _last_good_timestamp: Optional[float] = None
    _session_id: str
    _http_client: urllib3.PoolManager

    _record_pool: RecordPool

    _tree: Optional[Tree] = None
    # the event_top records grouped by machine
    _tops: Dict[str, CursorList] = {}
    # memory information for the current time, grouped by machine
    # meminfo may not be available for every time
    _meminfo: Dict[str, Optional[Dict[str, int]]] = {}

    def __init__(self, config: Config) -> None:
        self.config = config
        self._session_id = uuid.uuid4().hex
        self._http_client = urllib3.PoolManager()
        self._record_pool = RecordPool(config)

    def __del__(self):
        if self.thread:
            self.thread.join()

    def init(self) -> None:
        """Initialize the model, loading data from the source. Requires config to be complete"""
        self._timestamp = (
            self.config.start_time.astimezone(timezone.utc).timestamp()
            if self.config.start_time
            else None
        )

        self._record_pool.init_api()

        if not self.config.is_complete:
            # ideally, this would never happen, as the configuration screen
            # should complete the configuration before the model is initialized
            raise RuntimeError("Configuration is incomplete, cannot load data")

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

    def init_api(self):
        """Initialize the API client"""
        self._record_pool.init_api()

    def load_data(
        self,
        timestamp: Optional[float],
        duration: Optional[timedelta] = None,
        before=timedelta(seconds=120),
    ) -> None:
        """Load data from the source, either the API or a file, then process it"""
        try:
            self._record_pool.load(timestamp, duration, before)
            log.debug(
                "Loaded Items: ",
                {key: len(value) for key, value in self._record_pool.records.items()},
            )
        except (RuntimeError, APIError) as exc:
            log.traceback(exc)
            self.fail(str(exc))
            return
        except Exception as exc:  # pylint: disable=broad-except
            # fallback case; we don't want to crash the app if something
            # unexpected happens
            log.warn("An unexpected type of exception occurred while loading data")
            log.traceback(exc)
            self.fail(str(exc))
            return

        event_top_data = self._record_pool.records["event_top_data"].values()
        event_top_data = groupby(event_top_data, lambda record: record["muid"])
        self._tops = {
            muid: CursorList("time", list(records), self._timestamp)
            for muid, records in event_top_data
        }

        self.rebuild_tree()

        log.info("Finished loading data")
        self._fix_state()

    def _correct_meminfo(self) -> None:
        """Correct the memory information for the current time"""

        # memory is only non-null every 15 seconds, so work back to the
        # previous time that has memory information
        new_meminfo = None
        index = 0
        for muid, cursorlist in self._tops.items():
            while not new_meminfo and cursorlist.is_valid(index):
                new_meminfo = cursorlist[index]["memory"]
                index -= 1
            self._meminfo[muid] = new_meminfo

    def _fix_state(self) -> None:
        """
        Fix the state of the model after loading. This includes:
            - correcting the memory information
            - updating time_elapsed
            - updating the machine
        """
        try:
            for c_list in self._tops.values():
                c_list.update_cursor(self._timestamp)
            # if the time is None, there was no specified time, so
            # go back to the beginning of the records
            if self._timestamp is None:
                self.recover("reload")
                return

            if not self._record_pool.is_loaded(self._timestamp) and isinstance(
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

            # update the machine
            # there will usually only be one machine, so we can just use the first one
            if len(self._record_pool.records["model_machine"]) == 0:
                log.warn("No machines found in the records")
                self.selected_machine = None
            else:
                self.selected_machine = list(
                    self._record_pool.records["model_machine"].keys()
                )[0]
            if len(self._record_pool.records["model_machine"]) > 1:
                # the user will have to select a machine later
                self.selected_machine = None

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
    ) -> Optional[Tuple[bool, Tree]]:
        """Recursively create a tree branch for a process"""
        # branches are tuples of (enabled, {child id: branch})
        if processes_w_children[rec_id] == []:
            return None
        branch = (enabled, {})
        for child in processes_w_children[rec_id]:
            branch[1][child] = AppModel._make_branch(
                child, processes_w_children, enabled
            )
        return branch  # type: ignore

    def get_orgs(self, force_reload: bool = False) -> Optional[List[dict]]:
        """Fetch a list of organization for this api_key"""
        if len(self._record_pool.orgs) == 0 or force_reload:
            try:
                self._record_pool.load_orgs(force_reload)
                self.log_api(
                    API_LOG_TYPES["orgs"], {"count": len(self._record_pool.orgs)}
                )
            except APIError as exc:
                log.traceback(exc)
                self.fail(str(exc))
                return None
            except Exception as exc:  # pylint: disable=broad-except
                self.fail("An exception occurred while loading orgs")
                log.traceback(exc)
        return self._record_pool.orgs

    def get_sources(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        uid: Optional[str] = None,
        force_reload: bool = False,
    ) -> Optional[List[dict]]:
        """Fetch a list of sources for this api_key"""
        if self.config.org is None:
            return None
        if self._record_pool.sources.get(self.config.org) is None or force_reload:
            try:
                self._record_pool.load_sources(
                    self.config.org, page, page_size, uid, force_reload
                )
                if self._record_pool.sources.get(self.config.org) is not None:
                    self.log_api(
                        API_LOG_TYPES["sources"],
                        {"count": len(self._record_pool.sources[self.config.org])},
                    )
            except APIError as exc:
                log.traceback(exc)
                self.fail(str(exc))
                return None
            except Exception as exc:  # pylint: disable=broad-except
                self.fail("An exception occurred while loading sources")
                log.traceback(exc)
        return self._record_pool.sources.get(self.config.org)

    def get_clusters(self, force_reload: bool = False) -> Optional[List[dict]]:
        """Fetch a list of clusters for this api_key"""
        if self.config.org is None:
            return None
        if self._record_pool.clusters.get(self.config.org) is None or force_reload:
            try:
                self._record_pool.load_clusters(self.config.org, force_reload)
                if self._record_pool.clusters.get(self.config.org) is not None:
                    self.log_api(
                        API_LOG_TYPES["clusters"],
                        {"count": len(self._record_pool.clusters[self.config.org])},
                    )
            except APIError as exc:
                log.traceback(exc)
                self.fail(str(exc))
                return None
            except Exception as exc:  # pylint: disable=broad-except
                self.fail("An exception occurred while loading clusters")
                log.traceback(exc)
        return self._record_pool.clusters.get(self.config.org)

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

        log.debug(f"Sending API log: {new_data}")

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
                body=orjson.dumps(new_data),
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

    def get_value(self, key, muid: Optional[str], previous=False) -> Any:
        """Provides the specified field on the most recent or the previous
        event_top_data record. If `muid` is None, the selected machine is used,
        and if that is None, the value is summed across all machines."""
        index = 0 if not previous else -1
        muid = muid or self.selected_machine
        if muid is not None:
            if not self.tops_valid():
                return None
            return self._tops[muid][index][key]
        return sum_element_wise(c_list[index][key] for c_list in self._tops.values())

    def get_time_elapsed(self, muid: str) -> float:
        """Get the time elapsed since the last event_top_data record for
        the specified machine."""
        if not self.tops_valid(muid):
            return 0
        return float(self._tops[muid][0]["time"]) - float(self._tops[muid][-1]["time"])

    def get_top_processes(
        self,
    ) -> Dict[str, Tuple]:
        """Get the resource usage records for the processes at the current time"""
        process_map = {}

        for muid, c_list in self._tops.items():
            if self.tops_valid(muid):
                process_map[muid] = (c_list[-1]["processes"], c_list[0]["processes"])

        return process_map

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
                    init = str(proc["id"])
                if proc["pid"] == 2:
                    kthreadd = str(proc["id"])
            except KeyError as exc:
                log.err(f"Process {exc} is missing.")
                log.traceback(exc)
                continue

        self._tree = {}  # type: ignore

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

    def recover(self, method="revert") -> None:  # pylint: disable=too-many-branches
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
                muid = self.selected_machine or (
                    list(self._tops.keys())[0] if len(self._tops) > 0 else None
                )
                if muid is not None:
                    c_list = self._tops[muid]
                    while not new_meminfo and index < len(c_list.data):
                        new_meminfo = c_list.data[index]["memory"]
                        index += 1
                    if index < len(c_list.data):
                        self.timestamp = c_list.data[index]["time"]
                    elif len(c_list.data) > 0:
                        self.timestamp = c_list.data[0]["time"]
                    self._correct_meminfo()
                else:
                    log.warn("No machine available to reload from.")

            elif method == "retry":
                log.info("Retrying loading from the API.")
                if self._timestamp is None:
                    self.fail("No timestamp to retry loading from.")
                    return
                self.load_data(self._timestamp)

            elif isinstance(method, float):
                log.info("Loading from custom time.")
                self.timestamp = method

            # sanity check
            if not self.is_valid():
                self.fail("Recovering failed to find a valid time.")
                et_data = self._record_pool.records["event_top_data"]
                log.debug(f"Time: {self._timestamp}, # of Records: {len(et_data)}")
                return

            self.failed = False
            self.failure_reason = ""
        except Exception as exc:  # pylint: disable=broad-except
            log.err("Exception occurred while recovering:")
            log.traceback(exc)
            self.fail("An exception occurred while attempting to recover.")

    def fail(self, reason: str) -> None:
        """Put the model in a failure state"""
        log.err(f"Model entered failure state with: {reason}")
        self.failed = True
        self.failure_reason = reason

    def tops_valid(self, muid: Optional[str] = None) -> bool:
        """Return whether the event top data is valid for this time"""
        # the slowest data should appear is once per 15 seconds
        grace_period = 16
        if muid is None:
            for muid_inner in self._tops.keys():
                if not self.tops_valid(muid_inner):
                    return False
            return True
        return (
            self._tops[muid].is_valid(0)
            and self._tops[muid].is_valid(-1)
            and abs(self._tops[muid][0]["time"] - self._timestamp) < grace_period
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
            self._record_pool.loaded
            and self._timestamp is not None
            and (
                self._record_pool.is_loaded(self._timestamp)
                or not isinstance(self.config.input, str)
            )
        )

    def clear(self) -> None:
        """Remove all loaded data from the model"""
        self._timestamp = None
        self._last_good_timestamp = None
        self._record_pool = RecordPool(self.config)

        self._tree = None
        self._tops = {}
        self.selected_machine = None
        self._meminfo = {}

        self.failed = False
        self.failure_reason = ""
        self.columns_changed = False

    def is_loaded(self, timestamp: float) -> bool:
        """Return whether the model has loaded data for the given time"""
        return self._record_pool.is_loaded(timestamp) or not isinstance(
            self.config.input, str
        )

    def get_record_by_id(self, record_id: str) -> Optional[Record]:
        """Get a record from the record pool by its ID"""
        for group in self._record_pool.records.values():
            if record_id in group:
                return group[record_id]
        return None

    @property
    def loaded(self) -> bool:
        """Return whether the model has loaded data"""
        return self._record_pool.loaded

    @property
    def progress(self) -> float:
        """Return the progress of the model"""
        return self._record_pool.progress

    @property
    def state(self) -> str:
        """The current status of the model"""
        if log.log_level <= log.DEBUG:
            try:
                return log.get_last_line()
            except IndexError:
                pass
        return f"Time: {self.time}"

    @property
    def memory(self) -> Optional[Dict[str, int]]:
        """The most recent memory usage data"""
        if not self.tops_valid():
            return None
        if self.selected_machine is not None:
            return self._meminfo[self.selected_machine]
        # create a sum of all machines
        return sum_element_wise(  # type: ignore
            m for m in self._meminfo.values() if m is not None
        )

    @property
    def machines(self) -> Dict[str, Record]:
        """The most recent machine data"""
        return self._record_pool.records["model_machine"]

    @property
    def processes(self) -> Dict[str, Record]:
        """All currently loaded process records"""
        return self._record_pool.records["model_process"]

    @property
    def flags(self) -> Dict[str, Record]:
        """All currently loaded flag records"""
        return self._record_pool.records["event_redflag"]

    @property
    def listening(self) -> Dict[str, Record]:
        """All currently loaded listening socket records"""
        return self._record_pool.records["model_listening_socket"]

    @property
    def connections(self) -> Dict[str, Record]:
        """All currently loaded connection records"""
        return self._record_pool.records["model_connection"]

    @property
    def sessions(self) -> Dict[str, Record]:
        """All currently loaded session records"""
        return self._record_pool.records["model_session"]

    @property
    def containers(self) -> Dict[str, Record]:
        """All currently loaded container records"""
        return self._record_pool.records["model_container"]

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
            raise RuntimeError("The tree is not yet loaded.")
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
    def timestamp(self) -> Optional[float]:
        """The current time, as a float"""
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value: Optional[float]) -> None:
        # set the current time and fix the state
        self._timestamp = value
        self._fix_state()
        if not self.failed:
            self._last_good_timestamp = self._timestamp
