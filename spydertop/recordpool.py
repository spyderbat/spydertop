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


from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import threading
from time import perf_counter
from typing import DefaultDict, Dict, List, Literal, Optional

import urllib3
from urllib3.exceptions import MaxRetryError, PoolError

from spydertop.config import Config
from spydertop.utils import log
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

    # def __del__(self):
    #     if self._api_client:
    #         self._api_client.close()

    def init_api(self) -> None:
        """Initialize the API client"""
        if isinstance(self._config.input, str) and self._connection_pool is None:
            self._connection_pool = urllib3.PoolManager()

    def load(
        self,
        timestamp: Optional[float],
        duration: Optional[timedelta] = None,
        before=timedelta(seconds=120),
    ) -> int:
        """Load data from the source, either the API or a file, then process it"""
        self.loaded = False
        if duration is None:
            duration = self._config.start_duration
        log.info(f"Loading data for time: {timestamp} and duration: {duration}")
        self.loaded = False
        self.progress = 0.0

        source = self._config.input
        lines = []

        if isinstance(source, str):
            # url, load data from api

            if timestamp is None:
                raise RuntimeError("No start time specified")
            if not self._config.api_key:
                raise RuntimeError("No API key specified")

            input_data = {
                # request data from a bit earlier, so that the information is properly filled out
                "start_time": timestamp - before.total_seconds() + 30,
                "end_time": timestamp + duration.total_seconds(),
                "src_uid": self._config.machine,
                "org_uid": self._config.org,
            }

            # we need more than one event_top record, so a buffer of 30 seconds is used
            # to make sure the data is available
            self._time_span_tracker.add_time_span(
                input_data["start_time"] + 30, input_data["end_time"]
            )

            def call_api(data_type: str):
                nonlocal lines
                ndjson = self.guard_api_call(
                    method="POST",
                    url="/api/v1/source/query/",
                    **input_data,
                    data_type=data_type,
                )
                lines += ndjson.split(b"\n")

            threads: list[threading.Thread] = []
            start = perf_counter()
            for data_type in ["htop", "k8s", "spydergraph"]:
                data_t = data_type
                thread = threading.Thread(target=call_api, args=(data_t,))
                thread.start()
                threads.append(thread)
            for thread in threads:
                thread.join()
                self.progress += 1.0 / len(threads)
                mid: float = perf_counter()
                log.info(f"Partial API call took {mid - start} seconds")
            end = perf_counter()
            log.info(f"API call took {end - start} seconds")
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
            # model.log_api(
            #     API_LOG_TYPES["loaded_data"], {"source_id": "file", "count": len(lines)}
            # )

        if self._config.output:
            # if lines is still binary, convert to text
            if len(lines) > 0 and isinstance(lines[0], bytes):
                lines = [line.decode("utf-8") for line in lines]  # type: ignore
            self._config.output.write("\n".join([l.rstrip() for l in lines]))

        start = perf_counter()
        self._process_records(lines)
        end = perf_counter()
        log.info(f"Processing records took {end - start} seconds")
        return len(lines)

    def _process_records(self, lines: List[str]) -> None:
        """Process the loaded records, parsing them and adding them to the model"""
        log.info("Parsing records")
        self.progress = 0.0

        lines = [line for line in lines if len(line.strip()) != 0]

        if len(lines) == 0:
            raise RuntimeError(
                "Loading was successful, but no records were found. \
Are you asking for the wrong time?"
            )

        for i, line in enumerate(lines):
            self.progress = i / len(lines)

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                log.err(f"Error decoding record: {line}")
                log.traceback(exc)
                continue

            short_schema = record["schema"].split(":")[0]

            group = self.records[short_schema]
            rec_id = record["id"]
            if rec_id in group:
                curr_rec = group[rec_id]
                if curr_rec["time"] > record["time"]:
                    # we already have a record with a newer timestamp
                    continue
            group[rec_id] = record

        log.info("Finished parsing records")
        self.loaded = True

    def is_loaded(self, timestamp: float) -> bool:
        """Check if the data is loaded for a given timestamp"""
        return self._time_span_tracker.is_loaded(timestamp)

    def load_orgs(self) -> None:
        """Fetch a list of organization for this api_key"""

        orgs = self.guard_api_call(method="GET", url="/api/v1/org/")
        orgs = json.loads(orgs)
        self.orgs = orgs

    def load_sources(
        self,
        org_uid: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        uid: Optional[str] = None,
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
            org_uid=self._config.org,
            **kwargs,
        )
        sources: List = json.loads(raw_sources)

        if len(sources) > 0:
            self.sources[org_uid] = sources

    def load_clusters(self, org_uid: str) -> None:
        """Fetch a list of clusters for this api_key"""
        response = self.guard_api_call(
            "GET",
            f"/api/v1/org/{org_uid}/cluster/",
        )
        # parse the response
        self.clusters[org_uid] = json.loads(response)
        log.log(self.clusters[org_uid])

    def guard_api_call(
        self, method: Literal["GET", "POST"], url: str, **input_data
    ) -> bytes:
        """Calls the api with the given arguments, properly handling any errors
        in the API call and converting them to an APIError"""
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        if self._connection_pool is None:
            raise RuntimeError("Connection pool is not initialized")
        if not isinstance(self._config.input, str):
            raise ValueError("Data cannot be loaded from an API; there is no url")
        log.debug(f"Making API call to {self._config.input + url} with ", input_data)
        try:
            api_response: urllib3.HTTPResponse = self._connection_pool.request(
                method,
                url=self._config.input + url,
                headers=headers,
                body=(json.dumps(input_data).encode() if method == "POST" else None),
            )
            newline = b"\n"
            log.debug(
                f"Context-uid in response to {url}: \
{api_response.headers.get('x-context-uid', None)}, \
status: {api_response.status}, size: {len(api_response.data.split(newline))}"
            )
        except MaxRetryError as exc:
            raise APIError(
                f"There was an issue trying to connect to the API. \
Is the url {self._config.input} correct?"
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
            raise APIError("There was an issue trying to connect to the API.") from exc

        if api_response.status != 200:
            log.debug(
                f"""\
Debug info:
API Call: {method} {url}
Input data: {input_data}
Status code: {api_response.status}
Reason: {api_response.reason}
Headers: {api_response.headers}
Request Headers: {headers}
Body: {api_response.data.decode("utf-8")}
Context-UID: {api_response.headers.get("x-context-uid", None) if api_response.headers else None}\
"""
            )
            raise APIError(
                f"Loading data from the api failed with reason: {api_response.reason}"
            )
        return api_response.data
