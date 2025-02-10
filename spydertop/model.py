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
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional, List, Any, Tuple
import uuid

import orjson
import urllib3

from spydertop.config import DEFAULT_API_URL
from spydertop.config.cache import set_user_cache
from spydertop.config.config import Settings
from spydertop.config.secrets import Secret
from spydertop.recordpool import RecordPool
from spydertop.state import State
from spydertop.utils import get_machine_short_name, get_timezone, log, sum_element_wise
from spydertop.utils.types import APIError, Record, Tree
from spydertop.utils.cursorlist import CursorList
from spydertop.constants import API_LOG_TYPES

DEFAULT_DURATION = timedelta(minutes=15)


class AppModel:  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """
    The main app model for the application, containing all logic necessary
    to provide data and state to the application.

    Data is divided into a few main objects:
    - The record pool, which contains all records fetched from the API
    - The settings, which contains all options that persist across sessions
    - The state, which contains internal state and options that do not persist
        across sessions, such as command line arguments
    """

    failed: bool = False
    failure_reason: str = ""
    settings: Settings
    state: State
    columns_changed: bool = False
    thread: Optional[threading.Thread] = None
    selected_machine: Optional[str] = None

    # cache for arbitrary states, registered through
    # register_state
    _cache: Dict[str, Dict[str, Any]] = {}

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

    def __init__(
        self, settings: Settings, state: State, record_pool: RecordPool
    ) -> None:
        self.settings = settings
        self.state = state
        self._session_id = uuid.uuid4().hex
        self._http_client = urllib3.PoolManager()
        self._record_pool = record_pool

        log.info("Creating model with state:")
        log.info(repr(self.state))

    def __del__(self):
        self.close()

    def close(self):
        """Close the model, cleaning up any resources"""
        if self.thread and self.thread != threading.current_thread():
            self.thread.join()
        self._record_pool.close()

    def init(self, start_duration: Optional[timedelta]) -> None:
        """Initialize the model, loading data from the source. Requires config to be complete"""

        def guard():
            try:
                self.load_data(self.timestamp, start_duration, before=start_duration)
            except Exception as exc:  # pylint: disable=broad-except
                self.fail("An exception occurred while loading data")
                log.traceback(exc)

        thread = threading.Thread(target=guard)
        thread.start()
        self.thread = thread

    def load_data(
        self,
        timestamp: Optional[float],
        duration: Optional[timedelta],
        before: Optional[timedelta] = None,
    ) -> None:
        """Load data from the source, either the API or a file, then process it"""
        if before is None:
            before = timedelta(minutes=15)
        try:
            if isinstance(self._record_pool.input_, Secret):
                if timestamp is None or self.state.source_uid is None:
                    raise RuntimeError("Not enough information to load data from API")

                self._record_pool.load_api(
                    self.state.org_uid,
                    self.state.source_uid,
                    timestamp,
                    duration or timedelta(minutes=15),
                    before,
                )
            else:
                self._record_pool.load_file()
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
            muid: CursorList("time", list(records), self.timestamp)
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
                c_list.update_cursor(self.timestamp)
            # if the time is None, there was no specified time, so
            # go back to the beginning of the records
            if self.timestamp is None:
                self.recover("reload")
                return

            if not self._record_pool.is_loaded(self.timestamp) and isinstance(
                self._record_pool.input_, Secret
            ):
                time_to_load = self.timestamp

                if self.thread and self.thread != threading.current_thread():
                    self.thread.join()

                thread = threading.Thread(
                    target=lambda: self.load_data(
                        time_to_load, timedelta(seconds=900), timedelta(seconds=900)
                    )
                )
                thread.start()
                self.thread = thread
                return

            # FIXME: disabling this for now since it blocks the UI; there is no
            # point in loading pre-emptively if it isn't done in the background
            # # pre-emptively load more records if we're close to the end
            # if (
            #     not self._record_pool.is_loaded(self.timestamp + 300)
            #     or not self._record_pool.is_loaded(self.timestamp - 300)
            # ) and isinstance(self._record_pool.input_, Secret):
            #     time_to_load = self.timestamp

            #     if self.thread and self.thread != threading.current_thread():
            #         self.thread.join()

            #     thread = threading.Thread(
            #         target=lambda: self.load_data(
            #             time_to_load, timedelta(seconds=900), timedelta(seconds=900)
            #         )
            #     )
            #     thread.start()
            #     self.thread = thread
            #     return

            # correct the memory information
            self._correct_meminfo()

            # update the machine
            # there will usually only be one machine, so we can just use the first one
            if len(self._record_pool.records["model_machine"]) == 0:
                log.warn("No machines found in the records")
                self.selected_machine = None
            elif len(self._record_pool.records["model_machine"]) == 1:
                self.selected_machine = list(
                    self._record_pool.records["model_machine"].keys()
                )[0]
            elif len(self._record_pool.records["model_machine"]) > 1:
                # the user will have to select a machine later
                self.selected_machine = self.selected_machine or None

        except Exception as exc:  # pylint: disable=broad-except
            log.err("Exception occurred while fixing state:")
            log.traceback(exc)
            self.fail(
                f"""\
The time {self.state.time} is invalid, \
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

    def get_sources(  # pylint: disable=too-many-arguments
        self,
        org_uid: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        uid: Optional[str] = None,
        force_reload: bool = False,
    ) -> Optional[List[dict]]:
        """Fetch a list of sources for this api_key"""
        if self._record_pool.sources.get(org_uid) is None or force_reload:
            try:
                self._record_pool.load_sources(
                    org_uid, page, page_size, uid, force_reload
                )
                if self._record_pool.sources.get(org_uid) is not None:
                    self.log_api(
                        API_LOG_TYPES["sources"],
                        {"count": len(self._record_pool.sources[org_uid])},
                    )
            except APIError as exc:
                log.traceback(exc)
                self.fail(str(exc))
                return None
            except Exception as exc:  # pylint: disable=broad-except
                self.fail("An exception occurred while loading sources")
                log.traceback(exc)
        return self._record_pool.sources.get(org_uid)

    def get_clusters(
        self, org_uid: str, force_reload: bool = False
    ) -> Optional[List[dict]]:
        """Fetch a list of clusters for this api_key"""
        if self._record_pool.clusters.get(org_uid) is None or force_reload:
            try:
                self._record_pool.load_clusters(org_uid, force_reload)
                if self._record_pool.clusters.get(org_uid) is not None:
                    self.log_api(
                        API_LOG_TYPES["clusters"],
                        {"count": len(self._record_pool.clusters[org_uid])},
                    )
            except APIError as exc:
                log.traceback(exc)
                self.fail(str(exc))
                return None
            except Exception as exc:  # pylint: disable=broad-except
                self.fail("An exception occurred while loading clusters")
                log.traceback(exc)
        return self._record_pool.clusters.get(org_uid)

    def log_api(self, name: str, data: Dict[str, Any]) -> None:
        """Send logs to the spyderbat internal logging API"""
        if not self.is_loading_from_api():
            url = DEFAULT_API_URL
        else:
            assert isinstance(self._record_pool.input_, Secret)
            url = self._record_pool.input_.api_url
        new_data = {
            "name": name,
            "application": "spydertop",
            "orgId": self.state.org_uid,
            "session_id": self._session_id,
            **data,
        }

        log.debug(f"Sending API log: {new_data}")

        def send_log():
            try:
                headers = {
                    "Content-Type": "application/json",
                }
                if isinstance(self._record_pool.input_, Secret):
                    headers[
                        "Authorization"
                    ] = f"Bearer {self._record_pool.input_.api_key}"
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
                        f"Logging API returned status {response.status}"
                        f" with message: {response.data}"
                    )
            except Exception as exc:  # pylint: disable=broad-except
                log.debug("Exception when logging to API")
                log.traceback(exc)

        # sending logs to the API should not block the ui,
        # so do it in a daemon thread
        thread = threading.Thread(target=send_log)
        thread.daemon = True
        thread.start()

    def submit_feedback(self, feedback: str) -> None:
        """Submit feedback to the spyderbat internal logging API"""
        self.log_api(API_LOG_TYPES["feedback"], {"message": feedback})
        set_user_cache("has_submitted_feedback", True)

    def get_value(self, key, muid: Optional[str], previous=False) -> Any:
        """Provides the specified field on the most recent or the previous
        event_top_data record. If `muid` is None, the selected machine is used,
        and if that is None, the value is summed across all machines."""
        index = 0 if not previous else -1
        muid = muid or self.selected_machine
        if muid is not None:
            if not self.tops_valid(muid):
                return None
            if muid not in self._tops:
                return None
            return self._tops[muid][index][key]
        if not self.tops_valid():
            return None
        return sum_element_wise(
            c_list[index][key]
            for c_list in self._tops.values()
        )

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
        all_processes = self.processes
        processes_by_muid = {}
        for p in all_processes.values():
            processes_by_muid.setdefault(p.get("muid"), []).append(p)
        self._tree = {}  # type: ignore

        for _, processes in processes_by_muid.items():
            # the two main root processes are the kernel and the init process
            # we will use these as the root of the tree
            kthreadd = None
            init = None

            for proc in processes:
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

            # add the root processes to the tree
            if kthreadd:
                self._tree[kthreadd] = AppModel._make_branch(
                    kthreadd, processes_w_children, not self.settings.collapse_tree
                )
                # root processes are always enabled
                self._tree[kthreadd] = (True, self._tree[kthreadd][1])
            if init:
                self._tree[init] = AppModel._make_branch(
                    init, processes_w_children, not self.settings.collapse_tree
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
        self.state.play = False

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
                    list(self._tops.keys())[0]
                    if len(self._tops) > 0
                    else (
                        next(
                            iter(
                                m["id"]
                                for m in self._record_pool.records[
                                    "model_machine"
                                ].values()
                            )
                        )
                    )
                )
                if muid is not None:
                    c_list = self._tops.get(muid, CursorList("", [], 0))
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
                if self.timestamp is None:
                    self.fail("No timestamp to retry loading from.")
                    return
                self.load_data(self.timestamp, DEFAULT_DURATION)

            elif isinstance(method, float):
                log.info("Loading from custom time.")
                self.timestamp = method

            # sanity check
            if not self.is_valid():
                self.fail("Recovering failed to find a valid time.")
                et_data = self._record_pool.records["event_top_data"]
                log.debug(f"Time: {self.state.time}, # of Records: {len(et_data)}")
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
            muid in self._tops
            and self._tops[muid].is_valid(0)
            and self._tops[muid].is_valid(-1)
            and abs(self._tops[muid][0]["time"] - self.timestamp) < grace_period
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
            and self.timestamp is not None
            and (
                self._record_pool.is_loaded(self.timestamp)
                or not isinstance(self._record_pool.input_, Secret)
            )
        )

    def clear(self) -> None:
        """Remove all loaded data from the model"""
        self.state.time = None
        self._last_good_timestamp = None
        self._record_pool.clear()

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
            self._record_pool.input_, Secret
        )

    def is_loading_from_api(self) -> bool:
        """Return whether the model is currently loading data from the API"""
        return isinstance(self._record_pool.input_, Secret)

    def get_record_by_id(self, record_id: str) -> Optional[Record]:
        """Get a record from the record pool by its ID"""
        for group in self._record_pool.records.values():
            if record_id in group:
                return group[record_id]
        return None

    def get_machine_short_name(self, machine_id: str) -> str:
        """Get the short name of a machine"""
        source = [
            source
            for source in self._record_pool.sources.get(self.state.org_uid, [])
            if source.get("uid") == machine_id
        ]
        alternative_name = (
            get_machine_short_name(self.machines[machine_id])
            if machine_id in self.machines
            else machine_id
        )
        if len(source) == 0:
            return alternative_name
        source_name = source[0].get("description", source[0].get("runtime_description"))
        return source_name or alternative_name

    @property
    def loaded(self) -> bool:
        """Return whether the model has loaded data"""
        if not self._record_pool.loaded or self.timestamp is None:
            return False

        return self.is_loaded(self.timestamp)

    @property
    def progress(self) -> float:
        """Return the progress of the model"""
        return self._record_pool.progress

    @property
    def status(self) -> str:
        """The current status of the model"""
        if log.log_level <= log.DEBUG:
            try:
                return log.get_last_line()
            except IndexError:
                pass
        return f"Time: {self.state.time}"

    @property
    def memory(self) -> Optional[Dict[str, int]]:
        """The most recent memory usage data"""
        if not self.tops_valid():
            return None
        if self.selected_machine is not None:
            if self.selected_machine not in self._meminfo:
                return None
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

    @property
    def timestamp(self) -> Optional[float]:
        """The current time, as a float"""
        return self.state.time.timestamp() if self.state.time is not None else None

    @timestamp.setter
    def timestamp(self, value: Optional[float]) -> None:
        # set the current time and fix the state
        self.state.time = (
            datetime.fromtimestamp(value, tz=timezone.utc).astimezone(
                get_timezone(self.settings)
            )
            if value is not None
            else None
        )
        self._fix_state()
        if not self.failed:
            self._last_good_timestamp = self.timestamp
