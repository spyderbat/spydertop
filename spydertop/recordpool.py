#
# recordpool.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A data loading helper class for the model to abstract away and generalize
some of the data management functionality.
"""


import asyncio
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import timedelta
import multiprocessing
from typing import DefaultDict, Dict, List, Optional, Union

import orjson
import urllib3
from urllib3.exceptions import MaxRetryError

from spydertop.config import Config
from spydertop.utils import log
from spydertop.utils.cache import DEFAULT_TIMEOUT, cache_block
from spydertop.utils.types import APIError, Record, TimeSpanTracker


class RecordPool:
    """
    Handles the loading, and storing, the records.
    The model is meant to use this class to provide data in a better format
    to the UI elements.
    """

    loaded: bool = False
    progress: float = 0.0
    records: DefaultDict[str, Dict[str, Record]]
    orgs: List[dict] = []
    sources: Dict[str, List[dict]] = {}
    clusters: Dict[str, List[dict]] = {}

    _config: Config
    _time_span_tracker = TimeSpanTracker()
    _connection_pool: Optional[urllib3.PoolManager] = None

    def __init__(self, config: Config):
        self.records = defaultdict(lambda: {})
        self._config = config

    def init_api(self) -> None:
        """Initialize the API client"""
        if isinstance(self._config.input, str) and self._connection_pool is None:
            self._connection_pool = urllib3.PoolManager()

    def load(
        self,
        timestamp: Optional[float],
        duration: Optional[timedelta] = None,
        before=timedelta(seconds=120),
    ):
        """Load data from the source, either the API or a file, then process it"""
        self.loaded = False
        if duration is None:
            duration = self._config.start_duration
        log.info(f"Loading data for time: {timestamp} and duration: {duration}")
        self.loaded = False
        self.progress = 0.0

        source = self._config.input

        if isinstance(source, str):
            # url, load data from api

            if timestamp is None:
                raise RuntimeError("No start time specified")
            if not self._config.api_key:
                raise RuntimeError("No API key specified")
            assert self._config.machine is not None

            input_data = {
                # request data from a bit earlier, so that the information is properly filled out
                "start_time": timestamp - before.total_seconds() + 30,
                "end_time": timestamp + duration.total_seconds(),
                "org_uid": self._config.org,
            }

            # we need more than one event_top record, so a buffer of 30 seconds is used
            # to make sure the data is available
            self._time_span_tracker.add_time_span(
                input_data["start_time"] + 30, input_data["end_time"]
            )

            if self._config.machine.startswith("clus:"):
                # this is a cluster, so we need to get the k8s data
                # and then query each node
                log.info("Loading cluster data")
                k8s_data = self.guard_api_call(
                    method="POST",
                    url="/api/v1/source/query/",
                    **input_data,
                    src_uid=self._config.machine,
                    data_type="k8s",
                )
                log.info("Parsing cluster data")
                self._process_records(k8s_data.split(b"\n"), 0.1, parallel=False)
                log.info("Loading node data")
                sources = [
                    node["muid"] for node in self.records["model_k8s_node"].values()
                ]
            else:
                self.progress = 0.1
                log.info("Loading machine data")
                sources = [self._config.machine]

            def call_api(data_type: str, src_id: str):
                ndjson = self.guard_api_call(
                    method="POST",
                    url="/api/v1/source/query/",
                    **input_data,
                    src_uid=src_id,
                    data_type=data_type,
                )
                return ndjson.split(b"\n")

            async def load():
                nonlocal lines
                # future is unsubscriptable in python 3.7
                threads: List[Future] = []  # : List[Future[List[bytes]]]
                with ThreadPoolExecutor() as executor:
                    for source in sources:
                        for data_type in ["htop", "spydergraph"]:
                            threads.append(executor.submit(call_api, data_type, source))
                    for thread in as_completed(threads):
                        self._process_records(
                            thread.result(), 0.9 / len(threads), parallel=False
                        )
                        await asyncio.sleep(0)  # try to let the UI update

            asyncio.run(load())
        else:
            # file, read in records and parse
            log.info(f"Reading records from input file: {source.name}")

            lines = source.readlines()
            if len(lines) == 0:
                # file was most likely already read
                raise RuntimeError(
                    "The current time is unloaded, but input is from a file. \
No more records can be loaded."
                )
            self._process_records(lines, 1.0)

        if self._config.output:
            lines = [
                orjson.dumps(record).decode() + "\n"
                for group in self.records.values()
                for record in group.values()
            ]
            self._config.output.writelines(lines)

    def _process_records(
        self,
        lines: Union[List[str], List[bytes]],
        progress_increase: float,
        parallel=True,
    ) -> None:
        """Process the loaded records, parsing them and adding them to the model"""

        # if lines is binary, convert to text
        if len(lines) > 0 and isinstance(lines[0], bytes):
            str_lines = [line.decode("utf-8") for line in lines]  # type: ignore
        else:
            str_lines: List[str] = lines  # type: ignore
        lines = [line for line in str_lines if len(line.strip()) != 0]

        if len(lines) == 0:
            log.info("No records to process")
            return

        # translate the lines from json to a dict in parallel

        # for some reason, forking seems to break stdin/out in some cases
        if parallel:
            multiprocessing.set_start_method("spawn")
            with multiprocessing.Pool() as pool:
                records = pool.map(orjson.loads, lines)
        else:
            records = [orjson.loads(line) for line in lines]

        self.progress += 0.5 * progress_increase

        for record in records:
            self.progress += 1 / len(lines) * progress_increase * 0.5

            short_schema = record["schema"].split(":")[0]

            group = self.records[short_schema]
            rec_id = record["id"]
            if rec_id in group:
                curr_rec = group[rec_id]
                if curr_rec["time"] > record["time"]:
                    # we already have a record with a newer timestamp
                    continue
            group[rec_id] = record

        self.loaded = True

    def is_loaded(self, timestamp: float) -> bool:
        """Check if the data is loaded for a given timestamp"""
        return self._time_span_tracker.is_loaded(timestamp)

    def load_orgs(self, force_reload=False) -> None:
        """Fetch a list of organization for this api_key"""

        orgs = self.guard_api_call(
            method="GET",
            url="/api/v1/org/",
            enable_cache=True,
            timeout=(timedelta(minutes=0) if force_reload else timedelta(hours=1)),
        )
        orgs = orjson.loads(orgs)
        self.orgs = orgs

    def load_sources(  # pylint: disable=too-many-arguments
        self,
        org_uid: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        uid: Optional[str] = None,
        force_reload=False,
    ) -> None:
        """Fetch a list of sources for this api_key"""
        # this tends to take a long time for large organizations
        # because the returned json is all one big string
        kwargs = {}
        if page is not None:
            log.warn("Paging of sources is not currently supported by the API.")
            kwargs["page"] = page
        if page_size is not None:
            log.warn("Paging of sources is not currently supported by the API.")
            kwargs["page_size"] = page_size
        if uid is not None:
            kwargs["agent_uid_equals"] = uid
        raw_sources = self.guard_api_call(
            method="GET",
            url=f"/api/v1/org/{org_uid}/source/",
            enable_cache=True,
            timeout=(timedelta(minutes=0) if force_reload else timedelta(minutes=15)),
            **kwargs,
        )
        sources: List = orjson.loads(raw_sources)

        if len(sources) > 0:
            self.sources[org_uid] = sources

    def load_clusters(self, org_uid: str, force_reload=False) -> None:
        """Fetch a list of clusters for this api_key"""
        response = self.guard_api_call(
            "GET",
            f"/api/v1/org/{org_uid}/cluster/",
            enable_cache=True,
            timeout=(timedelta(minutes=0) if force_reload else timedelta(minutes=15)),
        )
        # parse the response
        self.clusters[org_uid] = orjson.loads(response)

    def guard_api_call(
        self,
        method: str,
        url: str,
        timeout: timedelta = DEFAULT_TIMEOUT,
        enable_cache=False,
        **input_data,
    ) -> bytes:
        """Calls the api with the given arguments, properly handling any errors
        in the API call and converting them to an APIError"""

        if self._connection_pool is None:
            raise RuntimeError("Connection pool is not initialized")
        if not isinstance(self._config.input, str):
            raise ValueError("Data cannot be loaded from an API; there is no url")

        full_url = self._config.input + url
        conn_pool = self._connection_pool

        def make_api_call():
            if self._config.api_key is None:
                raise APIError("API key is not set")
            headers = {
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            }
            assert isinstance(self._config.input, str)
            log.debug(
                f"Making API call to {self._config.input + url} with ", input_data
            )
            try:
                api_response = conn_pool.request(
                    method,
                    url=full_url,
                    headers=headers,
                    body=(orjson.dumps(input_data) if method == "POST" else None),
                )
                newline = b"\n"
                log.debug(
                    f"Context-uid in response to {url}: "
                    f"{api_response.headers.get('x-context-uid', None)}, "
                    f"status: {api_response.status}, size: {len(api_response.data.split(newline))}"
                )

            except MaxRetryError as exc:
                raise APIError(
                    "There was an issue trying to connect to the API."
                    f"Is the url {self._config.input} correct?"
                ) from exc
            except Exception as exc:
                log.traceback(exc)
                log.debug(
                    f"""\
Debug info:
API Call: {url}
Input data: {input_data}
Args: {exc.args}\
"""
                )
                raise APIError(
                    "There was an issue trying to connect to the API."
                ) from exc

            if api_response.status != 200:
                sanitized_headers = {
                    "Authorization": f"Bearer {self._config.api_key[:3]}"
                    f"...{self._config.api_key[-3:]}",
                    **headers,
                }
                log.debug(
                    f"""\
Debug info:
API Call: {method} {url}
Input data: {input_data}
Status code: {api_response.status}
Reason: {api_response.reason}
Headers: {api_response.headers}
Request Headers: {sanitized_headers}
Body: {api_response.data.decode("utf-8")}
Context-UID: {api_response.headers.get("x-context-uid", None) if api_response.headers else None}\
"""
                )
                raise APIError(
                    f"Loading data from the api failed with reason: {api_response.reason}"
                )
            return api_response.data

        if enable_cache:
            data = cache_block(
                orjson.dumps((self._config.api_key, method, full_url, input_data)),
                make_api_call,
                timeout=timeout,
            )
        else:
            data = make_api_call()
        return data
