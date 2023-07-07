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
import gzip
import multiprocessing
from typing import DefaultDict, Dict, List, Optional, TextIO, Union

import orjson
import urllib3
from urllib3.exceptions import MaxRetryError

from spydertop.config.secrets import Secret
from spydertop.utils import log, obscure_key
from spydertop.config.cache import DEFAULT_TIMEOUT, cache_block
from spydertop.utils.types import APIError, Record, TimeSpanTracker


class RecordPool:
    """
    Handles the loading, and storing, the records.
    The model is meant to use this class to provide data in a better format
    to the UI elements.
    """

    loaded: bool = False
    progress: float = 0.0
    input_: Union[Secret, TextIO]
    records: DefaultDict[str, Dict[str, Record]] = defaultdict(lambda: {})
    orgs: List[dict] = []
    sources: Dict[str, List[dict]] = {}
    clusters: Dict[str, List[dict]] = {}

    _output: Optional[TextIO]
    _time_span_tracker = TimeSpanTracker()
    _connection_pool: Optional[urllib3.PoolManager] = None

    def __init__(
        self,
        input_src: Union[Secret, TextIO],
        output: Optional[TextIO] = None,
    ):
        self.input_ = input_src
        self._output = output

        # if the output file is gzipped, open it with gzip
        if self._output and self._output.name.endswith(".gz"):
            self._output = gzip.open(self._output.name, "wt")
        if isinstance(self.input_, Secret) and self._connection_pool is None:
            self._connection_pool = urllib3.PoolManager()

    def __del__(self):
        self.close()

    def close(self):
        """Close the record pool"""
        if not isinstance(self._output, Secret) and self._output is not None:
            self._output.close()

    def load_api(  # pylint: disable=too-many-arguments
        self,
        org_uid: str,
        source_uid: str,
        timestamp: float,
        duration: timedelta,
        before=timedelta(seconds=120),
    ):
        """Load data from the source, either the API or a file, then process it"""
        log.info(f"Loading data for time: {timestamp} and duration: {duration}")
        self.loaded = False
        self.progress = 0.0

        data_source = self.input_

        if not isinstance(data_source, Secret):
            raise RuntimeError("Data source must be a Secret when loading from API")

        input_data = {
            # request data from a bit earlier, so that the information is properly filled out
            "start_time": timestamp - before.total_seconds() + 30,
            "end_time": timestamp + duration.total_seconds(),
            "org_uid": org_uid,
        }

        # we need more than one event_top record, so a buffer of 30 seconds is used
        # to make sure the data is available
        self._time_span_tracker.add_time_span(
            input_data["start_time"] + 30, input_data["end_time"]
        )

        if source_uid.startswith("clus:"):
            # this is a cluster, so we need to get the k8s data
            # and then query each node
            log.info("Loading cluster data")
            k8s_data = self.guard_api_call(
                method="POST",
                url="/api/v1/source/query/",
                **input_data,
                src_uid=f"{source_uid}_base",
                data_type="k8s",
            )
            log.info("Parsing cluster data")
            self._process_records(k8s_data.split(b"\n"), 0.1, parallel=False)
            log.info("Loading node data")
            sources = [node["muid"] for node in self.records["model_k8s_node"].values()]
        else:
            self.progress = 0.1
            log.info("Loading machine data")
            sources = [source_uid]

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

        if self._output is not None:
            lines = [
                orjson.dumps(record).decode() + "\n"
                for group in self.records.values()
                for record in group.values()
            ]
            self._output.writelines(lines)

        self.loaded = True
        log.debug("Completed loading records")

    def load_file(self):
        """Load data from a file, then process it"""
        self.loaded = False
        self.progress = 0.0
        if isinstance(self.input_, Secret):
            raise RuntimeError("Data source must be a file when loading from file")
        # file, read in records and parse
        log.info(f"Reading records from input file: {self.input_.name}")

        lines = self.input_.readlines()
        if len(lines) == 0:
            # file was most likely already read
            raise RuntimeError(
                "The current time is unloaded, but input is from a file. \
No more records can be loaded."
            )
        self._process_records(lines, 1.0)

        self.loaded = True
        log.debug("Completed loading records from file")

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
            self.progress += progress_increase
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

    def is_loaded(self, timestamp: float) -> bool:
        """Check if the data is loaded for a given timestamp"""
        return self._time_span_tracker.is_loaded(timestamp)

    def load_orgs(self, force_reload=False) -> None:
        """Fetch a list of organization for this api_key"""

        orgs = self.guard_api_call(
            method="GET",
            url="/api/v1/org/",
            enable_cache=True,
            timeout=(timedelta(minutes=0) if force_reload else timedelta(hours=6)),
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
            timeout=(timedelta(minutes=0) if force_reload else timedelta(hours=1)),
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
            timeout=(timedelta(minutes=0) if force_reload else timedelta(hours=1)),
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
        if not isinstance(self.input_, Secret):
            raise ValueError(
                "Data cannot be loaded from an API, input is from somewhere else."
            )

        if not self.input_.api_url.startswith("http"):
            base_url = f"https://{self.input_.api_url}"
        else:
            base_url = self.input_.api_url

        full_url = base_url + url
        conn_pool = self._connection_pool

        def make_api_call():
            assert isinstance(self.input_, Secret)
            headers = {
                "Authorization": f"Bearer {self.input_.api_key}",
                "Content-Type": "application/json",
            }
            log.debug(f"Making API call to {full_url} with ", input_data)
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
                    f"Is the url {self.input_} correct?"
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
                    **headers,
                    "Authorization": f"Bearer {obscure_key(self.input_.api_key)}",
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
                orjson.dumps((self.input_.api_key, method, full_url, input_data)),
                make_api_call,
                timeout=timeout,
            )
        else:
            data = make_api_call()
        return data

    def clear(self):
        """Clear all data from the loader"""
        self.records.clear()
        self.orgs.clear()
        self.sources.clear()
        self.clusters.clear()
        self._time_span_tracker = TimeSpanTracker()
