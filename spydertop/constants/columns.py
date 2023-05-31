#
# columns.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A series of functions to handle the processing and formatting of top data for
the cells inside of the records table.

The Column class is used to define the columns that are displayed in the table.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Type, Callable, TYPE_CHECKING

import orjson

from spydertop.utils import (
    get_timezone,
    map_optional,
    pretty_address,
    pretty_time,
    log,
)
from spydertop.utils.types import Alignment, Record, Bytes, Severity, Status
from spydertop.constants import PAGE_SIZE

# Note: this is a workaround to avoid circular imports
# TYPE_CHECKING is False at runtime
if TYPE_CHECKING:
    from spydertop.model import AppModel
else:
    AppModel = Any


class Column:
    """
    Holds the information for processing and displaying a column.
    Values here work similarly to the values used in MUI DataGrid columns.
    """

    header_name: str
    max_width: int
    value_type: Type = Any
    enabled: bool
    align: Alignment
    value_getter: Callable[[AppModel, Record], Any]
    value_formatter: Callable[[AppModel, Record, Any], str]

    def __init__(  # pylint: disable=too-many-arguments
        self,
        name: str,
        max_width: int,
        value_type: Type,
        align: Optional[Alignment] = None,
        enabled=True,
        field: Optional[str] = None,
        value_getter: Optional[Callable[[AppModel, Record], Any]] = None,
        value_formatter: Optional[Callable[[AppModel, Record, Any], str]] = None,
    ) -> None:
        self.header_name = name
        self.max_width = max_width
        self.value_type = value_type
        self.align = align or (
            Alignment.RIGHT
            if value_type is int or value_type is float
            else Alignment.LEFT
        )
        self.enabled = enabled
        str_field: str = field or name.lower()
        if value_type is datetime:
            self.value_getter = value_getter or (
                lambda m, r: datetime.fromtimestamp(
                    float(r[str_field]), timezone.utc
                ).astimezone(get_timezone(m))
                if str_field in r
                else None
            )
        else:
            self.value_getter = value_getter or (lambda m, r: value_type(r[str_field]))
        self.value_formatter = value_formatter or (lambda m, r, v: str(v))

    def get_value(self, model: AppModel, record: Record) -> Any:
        """Returns the value for the column"""
        if record is None:
            return None
        try:
            return self.value_getter(model, record)
        except (KeyError, TypeError, IndexError) as err:
            log.debug(f"Getting value for {self.header_name} failed.")
            log.traceback(err)
            return None

    def format_value(self, model: AppModel, record: Record, value: Any) -> str:
        """Returns the formatted value for the column"""
        if record is None or value is None:
            return ""
        try:
            return self.value_formatter(model, record, value)
        except (KeyError, TypeError, IndexError) as err:
            log.debug(f"Getting value for {self.header_name} failed.")
            log.traceback(err)
            return ""


########################### Processes ###########################


def get_cpu_per(model: AppModel, process: Record):
    """Calculates the percentage of CPU time used by the process"""
    record = get_resource_record(model, process)
    prev_record = get_resource_record(model, process, previous=True)
    if record is None or prev_record is None:
        return None
    time_delta = model.get_time_elapsed(muid=process["muid"])
    clk_tck = model.get_value("clk_tck", muid=process["muid"])
    cpu = (
        record["utime"] - prev_record["utime"] + record["stime"] - prev_record["stime"]
    )
    cpu /= time_delta
    cpu /= clk_tck
    cpu = round(cpu * 100, 1)
    return cpu


def get_mem_per(model: AppModel, process: Record):
    """Formats the percentage of memory used by the process"""
    record = get_resource_record(model, process)
    if record is None:
        return None
    mem = record["rss"] * PAGE_SIZE
    mem_model = model.memory
    if mem_model:
        mem /= mem_model["MemTotal"]
    else:
        mem = 0
    mem = round(mem * 100, 1)
    return mem


def get_time_plus_value(model: AppModel, process: Record):
    """Returns the time spent in the process"""
    record = get_resource_record(model, process)
    if record is None:
        return None
    clk_tck = model.get_value("clk_tck", muid=process["muid"])
    cpu = record["utime"] + record["stime"]
    time = cpu / clk_tck
    return timedelta(seconds=time)


def color_cmd(_m, process: Record, args: List[str]):
    """Formats the command for the process"""
    base = f'{" ".join(args)}'
    color = ""
    if process["thread"] is True:
        color = "${2}"
    if process["type"] == "kernel thread":
        color = "${8,1}"
    return color + base


def format_environ(_m, _p, environ: Dict[str, str]):
    """Format the environment of a process"""
    environ_lines = (
        orjson.dumps(environ, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
        .decode()
        .split("\n")
    )
    if len(environ_lines) > 10:
        environ_lines = environ_lines[:9] + ["    ... <remaining values hidden>"]
    return "\n".join(environ_lines)


def format_container(model: AppModel, _p, container: str):
    """Formats the container information"""
    container_rec = model.containers.get(container)
    if container_rec is None:
        return ""
    color = "${2,1}" if container_rec["container_state"] == "running" else "${8,1}"
    return f"{container_rec['image']}#{container_rec['container_short_id']} \
[{color}{container_rec['container_state']}${{-1,0}}]"


def get_resource_record(
    model: AppModel, process_record: Record, previous=False
) -> Optional[Record]:
    """Returns the resource record for the process"""
    process_table = model.get_value("processes", process_record["muid"], previous)
    if process_table is None:
        return None
    default_values = process_table["default"]
    if str(process_record["pid"]) not in process_table:
        return None
    record = default_values.copy()
    record.update(process_table[str(process_record["pid"])])
    return record


PROCESS_COLUMNS = [
    Column("ID", 30, str, enabled=False),
    Column("NAME", 15, str, enabled=False),
    Column("PPID", 7, int, enabled=False),
    Column("PID", 7, int),
    Column("MUID", 16, str, enabled=False),
    Column(
        "USER",
        9,
        str,
        field="euser",
        value_formatter=lambda m, r, x: x if x != "root" else "${8,1}root",
    ),
    Column(
        "AUSER",
        9,
        str,
        field="auser",
        value_formatter=lambda m, r, x: x if x != "SYSTEM" else "${8,1}SYSTEM",
        enabled=False,
    ),
    Column(
        "START_TIME",
        27,
        datetime,
        align=Alignment.RIGHT,
        field="valid_from",
        enabled=False,
    ),
    Column(
        "PRI",
        3,
        int,
        value_getter=lambda m, x: map_optional(
            (lambda x: int(x["priority"])), get_resource_record(m, x)
        ),
        value_formatter=lambda m, r, x: str(x) if x is not None else "${8,1}?",
    ),
    Column(
        "NI",
        3,
        int,
        value_getter=lambda m, x: map_optional(
            (lambda x: int(x["nice"])), get_resource_record(m, x)
        ),
        value_formatter=lambda m, r, x: str(x) if x is not None else "${8,1}?",
    ),
    Column(
        "VIRT",
        5,
        Bytes,
        align=Alignment.RIGHT,
        value_getter=lambda m, x: map_optional(
            (lambda x: Bytes(x["vsize"])), get_resource_record(m, x)
        ),
    ),
    Column(
        "RES",
        5,
        Bytes,
        align=Alignment.RIGHT,
        value_getter=lambda m, x: map_optional(
            (lambda x: Bytes(x["rss"])), get_resource_record(m, x)
        ),
    ),
    Column(
        "SHR",
        5,
        Bytes,
        align=Alignment.RIGHT,
        value_getter=lambda m, x: map_optional(
            (lambda x: Bytes(x["shared"])), get_resource_record(m, x)
        ),
    ),
    Column(
        "S",
        1,
        Status,
        value_getter=lambda m, x: map_optional(
            (lambda x: Status(x["state"])), get_resource_record(m, x)
        )
        or Status.UNKNOWN,
        value_formatter=lambda m, r, x: "${8,1}" + str(x)
        if x != Status.RUNNING
        else "${2}R",
    ),
    Column(
        "TYPE",
        7,
        str,
        value_getter=lambda m, x: x["type"]
        if x["type"] != "kernel thread"
        else "kthread",
        enabled=False,
    ),
    Column(
        "I",
        1,
        bool,
        field="interactive",
        value_formatter=lambda m, r, x: "${2}Y" if x else "${1}N",
    ),
    Column(
        "CPU%",
        4,
        float,
        value_getter=get_cpu_per,
        value_formatter=lambda m, r, x: f"{x:4.1f}",
    ),
    Column(
        "MEM%",
        4,
        float,
        value_getter=get_mem_per,
        value_formatter=lambda m, r, x: f"{x:4.1f}",
    ),
    Column(
        "TIME+",
        9,
        timedelta,
        align=Alignment.RIGHT,
        value_getter=get_time_plus_value,
        value_formatter=lambda m, r, x: pretty_time(x.total_seconds()),
    ),
    Column(
        "ELAPSED",
        9,
        timedelta,
        align=Alignment.RIGHT,
        value_getter=lambda m, x: timedelta(seconds=m.timestamp - x["valid_from"]),
        value_formatter=lambda m, r, x: pretty_time(x.total_seconds()),
        enabled=False,
    ),
    Column(
        "ANCESTORS",
        30,
        list,
        value_getter=lambda m, x: x.get("ancestors", None) or [],
        value_formatter=lambda m, r, x: "/".join(x),
        enabled=False,
    ),
    Column("CGROUP", 20, str, enabled=False),
    Column(
        "CONT_SHORT_ID",
        12,
        str,
        value_getter=lambda m, x: map_optional(
            lambda x: m.containers.get(x, {}).get("container_short_id"),
            x.get("container"),
        ),
        enabled=False,
    ),
    Column(
        "CONTAINER_IMAGE",
        15,
        str,
        value_getter=lambda m, x: map_optional(
            lambda x: m.containers.get(x, {}).get("image"), x.get("container")
        ),
        enabled=False,
    ),
    Column(
        "ENVIRONMENT",
        11,
        dict,
        field="environ",
        value_formatter=format_environ,
        enabled=False,
    ),
    Column("Command", 0, list, field="args", value_formatter=color_cmd),
]

########################### Sessions ###########################

SESSION_COLUMNS = [
    Column("ID", 30, str, enabled=False),
    Column("EUID", 6, int),
    Column(
        "EUSER",
        9,
        str,
        value_formatter=lambda m, s, x: x if x != "root" else "${8,1}root",
    ),
    Column("AUID", 6, int, enabled=False),
    Column(
        "AUSER",
        9,
        str,
        value_formatter=lambda m, s, x: x if x != "root" else "${8,1}root",
        enabled=False,
    ),
    Column(
        "PARENT",
        9,
        str,
        field="psuid",
        value_formatter=lambda m, s, x: m.sessions[x]["euser"]
        if x in m.sessions
        else "",
        enabled=False,
    ),
    Column("START_TIME", 27, datetime, align=Alignment.RIGHT, field="valid_from"),
    Column(
        "DURATION",
        10,
        timedelta,
        align=Alignment.RIGHT,
        value_getter=lambda m, s: timedelta(seconds=m.timestamp - s["valid_from"])
        if s["expire_at"] > m.timestamp
        else timedelta(seconds=s["expire_at"] - s["valid_from"]),
        value_formatter=lambda m, s, x: pretty_time(x.total_seconds()),
    ),
    Column("LEADPID", 7, int, field="pid"),
    Column("LEADPNAME", 15, str, field="proc_name"),
    Column(
        "I",
        1,
        bool,
        field="interactive",
        value_formatter=lambda m, s, x: "${2}Y" if x else "${1}N",
    ),
    Column("MUID", 20, str, field="muid", enabled=False),
    Column("SESSPATH", 0, str, field="spath"),
]


########################### Connections ###########################

CONNECTION_COLUMNS = [
    Column("ID", 42, str, enabled=False),
    Column("PTCL", 4, str, field="proto"),
    Column("START_TIME", 27, datetime, field="valid_from", enabled=False),
    Column("END_TIME", 27, datetime, field="valid_to", enabled=False),
    Column(
        "DURATION",
        10,
        timedelta,
        value_getter=lambda m, c: timedelta(seconds=m.timestamp - c["valid_from"])
        if "duration" not in c or "valid_to" not in c or c["valid_to"] > m.timestamp
        else timedelta(seconds=c["duration"]),
        value_formatter=lambda m, c, x: pretty_time(x.total_seconds()),
    ),
    Column("TXPACK", 6, int, field="packets_tx", enabled=False),
    Column("RXPACK", 6, int, field="packets_rx", enabled=False),
    Column("TXBYTES", 7, Bytes, align=Alignment.RIGHT, field="bytes_tx"),
    Column("RXBYTES", 7, Bytes, align=Alignment.RIGHT, field="bytes_rx"),
    Column("PROCESS", 15, str, field="proc_name"),
    Column(
        "PEER",
        20,
        str,
        value_getter=lambda m, c: f'{c["peer_proc_name"]} on {c["peer_muid"]}'
        if "peer_proc_name" in c and "peer_muid" in c
        else "EXTERNAL",
        value_formatter=lambda m, c, x: x if x != "EXTERNAL" else "${8,1}EXTERNAL",
        enabled=False,
    ),
    Column(
        "LOCAL",
        45,
        str,
        align=Alignment.RIGHT,
        value_getter=lambda m, c: f'{c["local_ip"]}:{c["local_port"]}',
        value_formatter=lambda m, c, x: pretty_address(c["local_ip"], c["local_port"]),
    ),
    Column(
        "DIR",
        3,
        str,
        field="direction",
        align=Alignment.CENTER,
        value_formatter=lambda m, c, x: "${3}<--"
        if x == "inbound"
        else "${4}-->"
        if x == "outbound"
        else "${8,1}?",
    ),
    Column(
        "REMOTE",
        0,
        str,
        value_getter=lambda m, c: f'{c["remote_ip"]}:{c["remote_port"]}',
        value_formatter=lambda m, c, x: pretty_address(
            c["remote_ip"], c["remote_port"]
        ),
    ),
]

########################### Flags ###########################


def color_severity(_m, _f, severity: Severity) -> str:
    """Format the severity of a flag."""
    if severity == Severity.INFO:
        return "${8}I"
    if severity == Severity.LOW:
        return "L"
    if severity == Severity.MEDIUM:
        return "${11}M"
    if severity == Severity.HIGH:
        return "${3,1}H"
    if severity == Severity.CRITICAL:
        return "${1,1}C"
    return "${8,1}?"


SEVERITIES = {"info": -1, "low": 0, "medium": 1, "high": 2, "critical": 3}

FLAG_COLUMNS = [
    Column("ID", 42, str, enabled=False),
    Column("TIME", 27, datetime),
    Column(
        "AGE",
        10,
        timedelta,
        align=Alignment.RIGHT,
        value_getter=lambda m, f: timedelta(seconds=m.timestamp - f["time"]),
        value_formatter=lambda m, f, x: pretty_time(x.total_seconds()),
    ),
    Column(
        "EXCEPTED",
        8,
        bool,
        align=Alignment.CENTER,
        field="false_positive",
        value_formatter=lambda m, f, x: "${2}Y" if x else "${1}N",
    ),
    Column(
        "SEV",
        3,
        Severity,
        align=Alignment.CENTER,
        value_getter=lambda m, f: Severity(SEVERITIES[f["severity"]]),
        value_formatter=color_severity,
    ),
    Column(
        "MITRE",
        30,
        str,
        value_getter=lambda m, f: f["mitre_mapping"][0].get("technique_name", None)
        if len(f["mitre_mapping"]) > 0
        else None,
        enabled=False,
    ),
    Column(
        "ANCESTORS",
        30,
        list,
        value_getter=lambda m, f: f.get("ancestors", None) or [],
        value_formatter=lambda m, f, x: "/".join(x),
        enabled=False,
    ),
    Column("Description", 0, str),
]

########################### Listening Sockets ###########################

LISTENING_SOCKET_COLUMNS = [
    Column("ID", 42, str, enabled=False),
    Column("FAMILY", 4, str),
    Column("PTCL", 4, str, field="proto"),
    Column("START_TIME", 27, datetime, field="valid_from", enabled=False),
    Column(
        "DURATION",
        10,
        timedelta,
        value_getter=lambda m, l: timedelta(
            seconds=l.get("duration", m.timestamp - l["valid_from"])
        ),
        value_formatter=lambda m, l, x: pretty_time(x.total_seconds()),
    ),
    Column(
        "LOCAL",
        45,
        str,
        align=Alignment.RIGHT,
        value_getter=lambda m, l: f'{l["local_ip"]}:{l["local_port"]}',
        value_formatter=lambda m, l, x: pretty_address(l["local_ip"], l["local_port"]),
    ),
    Column("PUID", 20, str, enabled=False),
    Column("PROCESS", 0, str, field="proc_name"),
]

########################### Containers ###########################


def get_system(model: AppModel, cont: Record) -> Optional[str]:
    """Get the system name for a container."""
    muid = cont["muid"]
    machine_rec = model.machines[muid]
    if machine_rec is not None:
        return machine_rec["hostname"]
    return None


def format_mounts(_m: AppModel, _c: Record, mounts: List[Record]) -> str:
    """Format the mounts for a container."""
    return "\n".join(
        f"{m['Source']}:{m['Destination']}"
        for m in sorted(mounts, key=lambda m: m["Destination"])
    )


def format_networks(_m: AppModel, _c: Record, networks: dict) -> str:
    """Format the networks for a container."""
    return "\n".join(
        f"{key}: {orjson.dumps(value)}" for key, value in networks.items() if value
    )


CONTAINER_COLUMNS = [
    Column("ID", 42, str, enabled=False),
    Column("CONTAINER_ID", 12, str, field="container_short_id"),
    Column("CONT_ID_FULL", 10, str, field="container_id", enabled=False),
    Column("IMAGE", 40, str),
    Column("IMAGE_ID", 10, str, enabled=False),
    Column(
        "COMMAND",
        25,
        str,
        value_formatter=lambda m, c, x: x if x != "/pause" else "${8,1}/pause",
    ),
    Column(
        "CREATED",
        15,
        datetime,
        value_formatter=lambda m, c, x: pretty_time((m.time - x).total_seconds())
        + " ago",
    ),
    Column("START_TIME", 27, datetime, field="valid_from", enabled=False),
    Column(
        "STATUS",
        15,
        datetime,
        value_getter=lambda m, c: map_optional(
            lambda x: datetime.fromtimestamp(x, timezone.utc).astimezone(
                get_timezone(m)
            ),
            c.get("container_detail_state", {}).get("StartedAt"),
        ),
        value_formatter=lambda m, c, x: f"Up {pretty_time((m.time - x).total_seconds())}",
    ),
    Column(
        "PORTS",
        12,
        list,
        field="port_bindings",
        value_formatter=lambda m, c, x: ", ".join(x),
    ),
    Column(
        "VOLUMES",
        11,
        list,
        field="mounts",
        value_formatter=format_mounts,
        enabled=False,
    ),
    Column(
        "ENVIRONMENT",
        11,
        dict,
        field="env",
        value_formatter=format_environ,
        enabled=False,
    ),
    Column("NETWORKS", 11, dict, value_formatter=format_networks, enabled=False),
    Column("SYSTEM", 15, str, value_getter=get_system, enabled=False),
    Column(
        "ENTRYPOINT",
        15,
        str,
        value_getter=lambda m, c: " ".join(c.get("entrypoint") or []),
        value_formatter=lambda m, c, x: x if x != "/pause" else "${8,1}/pause",
        enabled=False,
    ),
    Column("NAME", 0, str, field="container_name"),
]
