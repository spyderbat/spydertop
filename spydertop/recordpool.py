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
from datetime import timedelta
import json
from typing import DefaultDict, Dict, List, Optional

import spyderbat_api
from spyderbat_api.api import (
    source_data_api,
    org_api,
    source_api,
)
import urllib3
from urllib3.exceptions import MaxRetryError

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
    _api_client: Optional[spyderbat_api.ApiClient] = None
    _time_span_tracker = TimeSpanTracker()

    def __init__(self, config: Config):
        self.records = defaultdict(lambda: {})
        self._config = config

    def __del__(self):
        if self._api_client:
            self._api_client.close()

    def init_api(self) -> None:
        """Initialize the API client"""
        if isinstance(self._config.input, str) and self._api_client is None:
            configuration = spyderbat_api.Configuration(
                access_token=self._config.api_key, host=self._config.input
            )

            self._api_client = spyderbat_api.ApiClient(configuration)

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

            api_instance = source_data_api.SourceDataApi(self._api_client)
            input_data = {
                # request data from a bit earlier, so that the information is properly filled out
                "st": timestamp - before.total_seconds() + 30,
                "et": timestamp + duration.total_seconds(),
                "src": self._config.machine,
            }

            # we need more than one event_top record, so a buffer of 30 seconds is used
            # to make sure the data is available
            self._time_span_tracker.add_time_span(
                input_data["st"] + 30, input_data["et"]
            )

            lines += self.load_from_api(api_instance, input_data, "spydergraph").split(
                b"\n"
            )
            lines += self.load_from_api(api_instance, input_data, "htop").split(b"\n")
            lines += self.load_from_api(api_instance, input_data, "k8s").split(b"\n")
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

        self._process_records(lines)
        return len(lines)

    def load_from_api(
        self,
        api_instance: source_data_api.SourceDataApi,
        input_data: dict,
        datatype: str,
    ) -> bytes:
        """Load data from the API with a specified type"""
        log.debug({"org_uid": self._config.org, "dt": datatype, **input_data})
        try:
            api_response: urllib3.HTTPResponse = api_instance.src_data_query_v2(
                org_uid=self._config.org,
                dt=datatype,
                **input_data,
                _preload_content=False,
            )
            newline = b"\n"
            log.debug(
                f"Context-uid in response: {api_response.headers.get('x-context-uid', None)}, \
status: {api_response.status}, size: {len(api_response.data.split(newline))}"
            )
        except spyderbat_api.ApiException as exc:
            log.debug(
                f"""\
Debug info:
URL requested: {self._config.input}/api/v1/source/query/
Method: POST
Input data: {input_data}
Data type: {datatype}
Status code: {exc.status}
Reason: {exc.reason}
Body: {exc.body}
Context-UID: {exc.headers.get("x-context-uid", None) if exc.headers else None}\
"""
            )
            raise APIError(
                f"Loading data from the api failed with reason: {exc.reason}"
            ) from exc
        except MaxRetryError as exc:
            raise APIError(
                f"There was an issue trying to connect to the API. \
Is the url {self._config.input} correct?"
            ) from exc
        return api_response.data

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

            # suppress errors for empty lines
            if line.strip() == "":
                continue

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
        api_instance: org_api.OrgApi = org_api.OrgApi(self._api_client)

        try:
            orgs = api_instance.org_list(_preload_content=False)
            orgs = json.loads(orgs.data)
            self.orgs = orgs
        except spyderbat_api.ApiException as exc:
            raise APIError(
                f"Exception when calling OrgApi: {exc.status} - {exc.reason}"
            ) from exc
        except MaxRetryError as exc:
            raise APIError(
                f"There was an issue trying to connect to the API. \
Is the url {self._config.input} correct?"
            ) from exc
        except Exception as exc:  # pylint: disable=broad-except
            raise APIError("Exception when calling OrgApi.") from exc

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
        #
        # we tell the api library to give us the raw response
        # and then parse it ourselves to save some time
        api_instance: source_api.SourceApi = source_api.SourceApi(self._api_client)

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
            raw_sources: urllib3.HTTPResponse = api_instance.src_list(
                org_uid=self._config.org,
                _preload_content=False,
                **kwargs,
            )
            sources: List = json.loads(raw_sources.data)

            if len(sources) > 0:
                self.sources[org_uid] = sources
        except MaxRetryError as exc:
            raise APIError(
                f"There was an issue trying to connect to the API. \
Is the url {self._config.input} correct?"
            ) from exc
        except Exception as exc:  # pylint: disable=broad-except
            raise APIError(f"Exception when calling SourceApi: {exc}") from exc

    def load_clusters(self, org_uid: str) -> None:
        """Fetch a list of clusters for this api_key"""
        # for now, the cluster API is not supported in the python client
        # so we have to do it manually
        assert self._api_client is not None
        http_client = self._api_client.rest_client.pool_manager

        if not isinstance(self._config.input, str):
            raise ValueError("Kubernetes data cannot be loaded; there is no url")

        url = f"{self._config.input}/api/v1/org/{org_uid}/clusters"
        log.log(url)

        headers = {
            "Content-Type": "application/json",
        }
        if self._config.api_key is not None:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        else:
            raise ValueError("Kubernetes data cannot be loaded; there is no API key")

        # send the data to the API
        try:
            response = http_client.request("GET", url, headers=headers)
        except MaxRetryError as exc:
            raise APIError(
                f"There was an issue trying to connect to the API. \
Is the url {self._config.input} correct?"
            ) from exc
        # check the response
        if response.status != 200:
            raise APIError("Loading data from the api failed: " + response.data)

        # parse the response
        self.clusters[org_uid] = json.loads(response.data)
        log.log(self.clusters[org_uid])
