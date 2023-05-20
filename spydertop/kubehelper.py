#
# kubehelper.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A kubernetes helper class for the model to abstract away some of the kubernetes
functionality.
"""

import json
from typing import List, Dict

import urllib3
from spydertop.config import Config
from spydertop.utils import log
from spydertop.utils.types import Record


class KubeHelper:
    """
    Handles the same responsibilities as the model, except for kubernetes data:
    This class manages the loading, processing, and access to kubernetes models
    """

    clusters: Dict[str, Record]
    nodes: Dict[str, Record]
    pods: Dict[str, Record]
    services: Dict[str, Record]
    containers: Dict[str, Record]

    _http_client: urllib3.PoolManager

    def __init__(self):
        self._http_client = urllib3.PoolManager()

    def process_data(self, records: List[str]):
        """
        Initializes the helper with the given records
        """
        self.clusters = {}
        self.nodes = {}
        self.pods = {}
        self.services = {}
        self.containers = {}

        for record in records:
            record = json.loads(record)
            short_schema = record["schema"].split(":")[0]
            if short_schema == "model_container":
                self.containers[record["id"]] = record

    def load_kube_data(self, config: Config):
        """
        Loads the kubernetes data from the kubernetes API
        """
        if not isinstance(config.input, str):
            log.err("Kubernetes data cannot be loaded; there is no url")
            return
        url = f"{config.input}/api/v1/org/{config.org}/clusters"
        log.log(url)

        try:
            headers = {
                "Content-Type": "application/json",
            }
            if config.api_key is not None:
                headers["Authorization"] = f"Bearer {config.api_key}"
            else:
                log.err("Kubernetes data cannot be loaded; there is no API key")
                return
            # send the data to the API
            response = self._http_client.request("GET", url, headers=headers)
            # check the response
            if response.status != 200:
                log.err("Kubernetes data cannot be loaded; the API returned an error")
                return

            # parse the response
            data = response.data.decode("utf-8").split("\n")
            self.process_data(data)
        except Exception as exc:  # pylint: disable=broad-except
            log.debug("Exception when logging to API")
            log.traceback(exc)
