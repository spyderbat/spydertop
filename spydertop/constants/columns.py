#
# columns.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A series of functions to handle the processing and formatting of top data for
the cells inside of the records table.

The format for each of the columns is a tuple of:
    - The name of the column
    - The function to call to get the text for the column
    - The alignment of the column
    - The width of the column
    - The function to call to get the value for the column
    - Whether the column is enabled (by default)
"""

from datetime import datetime, timezone
import json

from spydertop.utils import (
    get_timezone,
    pretty_address,
    pretty_bytes,
    pretty_time,
)
from spydertop.constants import PAGE_SIZE


########################### Processes ###########################

# functions for the processes table take four parameters:
#   - m: the model
#   - pr: the previous resource usage record
#   - r: the current resource usage record
#   - p: the current model process record
# both the pr and r parameters may be None if
# the process is a thread, or if no information is found


# pylint: disable=invalid-name
def get_cpu_per(m, pr, r, _p):
    """Formats the percentage of CPU time used by the process"""
    if r is None:
        return None
    time_delta = m.time_elapsed
    clk_tck = m.get_value("clk_tck")
    cpu = r["utime"] - pr["utime"] + r["stime"] - pr["stime"]
    cpu /= time_delta
    cpu /= clk_tck
    cpu = round(cpu * 100, 1)
    return cpu


def get_mem_per(m, _pr, r, _p):
    """Formats the percentage of memory used by the process"""
    if r is None:
        return None
    mem = r["rss"] * PAGE_SIZE
    mem_model = m.memory
    if mem_model:
        mem /= mem_model["MemTotal"]
    else:
        mem = 0
    mem = round(mem * 100, 1)
    return mem


def get_time_plus(m, _pr, r, _p):
    """Formats the time spent in the process"""
    if r is None:
        return None
    clk_tck = m.get_value("clk_tck")
    cpu = r["utime"] + r["stime"]
    time = cpu / clk_tck
    return pretty_time(time)


def get_time_plus_value(m, _pr, r, _p):
    """Returns the time spent in the process"""
    if r is None:
        return None
    clk_tck = m.get_value("clk_tck")
    cpu = r["utime"] + r["stime"]
    time = cpu / clk_tck
    return time


def color_cmd(_m, _pr, _r, p):
    """Formats the command for the process"""
    base = f'{" ".join(p["args"])}'
    color = ""
    if p["thread"] is True:
        color = "${2}"
    if p["type"] == "kernel thread":
        color = "${8,1}"
    return color + base


def format_environ(_m, _pr, _r, p):
    """Format the environment of a process"""
    environ_lines = json.dumps(
        p.get("environ", None) or {}, indent=4, sort_keys=True
    ).split("\n")
    if len(environ_lines) > 10:
        environ_lines = environ_lines[:9] + ["    ... <remaining values hidden>"]
    return "\n".join(environ_lines)


PROCESS_COLUMNS = [
    ("ID", lambda m, pr, r, p: p["id"], "<", 30, lambda m, pr, r, p: p["id"], False),
    (
        "NAME",
        lambda m, pr, r, p: p["name"],
        "<",
        15,
        lambda m, pr, r, p: p["name"],
        False,
    ),
    (
        "PPID",
        lambda m, pr, r, p: int(p["ppid"]),
        ">",
        7,
        lambda m, pr, r, p: int(p["ppid"]),
        False,
    ),
    (
        "PID",
        lambda m, pr, r, p: int(p["pid"]),
        ">",
        7,
        lambda m, pr, r, p: int(p["pid"]),
        True,
    ),
    (
        "USER",
        lambda m, pr, r, p: p["euser"] if p["euser"] != "root" else "${8,1}root",
        "<",
        9,
        lambda m, pr, r, p: p["euser"],
        True,
    ),
    (
        "AUSER",
        lambda m, pr, r, p: p["auser"] if p["auser"] != "SYSTEM" else "${8,1}SYSTEM",
        "<",
        9,
        lambda m, pr, r, p: p["auser"],
        False,
    ),
    (
        "START_TIME",
        lambda m, pr, r, p: datetime.fromtimestamp(
            int(p["valid_from"]), timezone.utc
        ).astimezone(get_timezone(m)),
        ">",
        27,
        lambda m, pr, r, p: p["valid_from"],
        False,
    ),
    (
        "PRI",
        lambda m, pr, r, p: int(r["priority"]) if r else "${8,1}?",
        ">",
        3,
        lambda m, pr, r, p: int(r["priority"]) if r else None,
        True,
    ),
    (
        "NI",
        lambda m, pr, r, p: (
            int(r["nice"]) if r["nice"] >= 0 else f'${{1}}{int(r["nice"])}'
        )
        if r
        else "${8,1}?",
        ">",
        3,
        lambda m, pr, r, p: int(r["nice"]) if r else None,
        True,
    ),
    (
        "VIRT",
        lambda m, pr, r, p: pretty_bytes(r["vsize"]) if r else "",
        ">",
        5,
        lambda m, pr, r, p: int(r["vsize"]) if r else None,
        True,
    ),
    (
        "RES",
        lambda m, pr, r, p: pretty_bytes(r["rss"] * PAGE_SIZE) if r else "",
        ">",
        5,
        lambda m, pr, r, p: int(r["rss"]) * PAGE_SIZE if r else None,
        True,
    ),
    (
        "SHR",
        lambda m, pr, r, p: pretty_bytes(r["shared"]) if r else "",
        ">",
        5,
        lambda m, pr, r, p: int(r["shared"]) if r else None,
        True,
    ),
    (
        "S",
        lambda m, pr, r, p: ("${8,1}" + r["state"] if r["state"] != "R" else "${2}R")
        if r
        else "${8,1}?",
        "^",
        1,
        lambda m, pr, r, p: r["state"] if r else None,
        True,
    ),
    (
        "TYPE",
        lambda m, pr, r, p: (
            p["type"] if p["type"] != "kernel thread" else "${8,1}kthread"
        ),
        "<",
        7,
        lambda m, pr, r, p: p["type"],
        False,
    ),
    (
        "I",
        lambda m, pr, r, p: "${2}Y" if p["interactive"] else "${1}N",
        ">",
        1,
        lambda m, pr, r, p: p["interactive"],
        True,
    ),
    ("CPU%", get_cpu_per, ">", 4, get_cpu_per, True),
    ("MEM%", get_mem_per, ">", 4, get_mem_per, True),
    ("TIME+", get_time_plus, ">", 9, get_time_plus_value, True),
    (
        "ELAPSED",
        lambda m, pr, r, p: pretty_time(m.timestamp - p["valid_from"]),
        ">",
        9,
        lambda m, pr, r, p: m.timestamp - p["valid_from"],
        False,
    ),
    (
        "ANCESTORS",
        lambda m, pr, r, p: "/".join(p.get("ancestors", None) or []),
        "<",
        30,
        lambda m, pr, r, p: "/".join(p.get("ancestors", None) or []),
        False,
    ),
    (
        "CGROUP",
        lambda m, pr, r, p: p.get("cgroup", None) or "",
        "<",
        30,
        lambda m, pr, r, p: p["cgroup"] if "cgroup" in p else None,
        False,
    ),
    (
        "CONTAINER",
        lambda m, pr, r, p: p.get("container", None) or "${8,1}N/A",
        ">",
        9,
        lambda m, pr, r, p: p["container"] if "container" in p else None,
        False,
    ),
    (
        "ENVIRONMENT",
        format_environ,
        "<",
        11,
        lambda m, pr, r, p: json.dumps(p.get("environ", None) or {}),
        False,
    ),
    ("Command", color_cmd, "<", 0, lambda m, pr, r, p: f'{" ".join(p["args"])}', True),
]

########################### Sessions ###########################

# functions for the rest of the record types take two parameters:
#  - m: the model
#  - s/l/f/etc.: the current session/listening socket/flag/etc. record


SESSION_COLUMNS = [
    ("ID", lambda m, s: s["id"], "<", 30, lambda m, s: s["id"], False),
    ("EUID", lambda m, s: s["euid"], ">", 6, lambda m, s: int(s["euid"]), True),
    (
        "EUSER",
        lambda m, s: s["euser"] if s["euser"] != "root" else "${8,1}root",
        "<",
        9,
        lambda m, s: s["euser"],
        True,
    ),
    ("AUID", lambda m, s: s["auid"], ">", 6, lambda m, s: int(s["auid"]), False),
    (
        "AUSER",
        lambda m, s: s["auser"] if s["auser"] != "root" else "${8,1}root",
        "<",
        9,
        lambda m, s: s["auser"],
        False,
    ),
    (
        "PARENT",
        lambda m, s: m.sessions[s["psuid"]]["euser"]
        if s["psuid"] is not None and s["psuid"] in m.sessions
        else "",
        "<",
        9,
        lambda m, s: s["psuid"],
        False,
    ),
    (
        "START_TIME",
        lambda m, s: datetime.fromtimestamp(
            int(s["valid_from"]), timezone.utc
        ).astimezone(get_timezone(m)),
        ">",
        27,
        lambda m, s: s["valid_from"],
        True,
    ),
    (
        "DURATION",
        lambda m, s: pretty_time(m.timestamp - s["valid_from"])
        if s["expire_at"] > m.timestamp
        else pretty_time(s["expire_at"] - s["valid_from"]),
        ">",
        9,
        lambda m, s: m.timestamp - s["valid_from"],
        True,
    ),
    ("LEADPID", lambda m, s: s["pid"], ">", 7, lambda m, s: s["pid"], True),
    (
        "LEADPNAME",
        lambda m, s: s["proc_name"],
        "<",
        15,
        lambda m, s: s["proc_name"],
        True,
    ),
    (
        "I",
        lambda m, s: "${2}Y" if s["interactive"] else "${1}N",
        ">",
        1,
        lambda m, s: s["interactive"],
        True,
    ),
    ("MUID", lambda m, s: s["muid"], "<", 20, lambda m, s: s["muid"], False),
    ("SESSPATH", lambda m, s: s["spath"], "<", 0, lambda m, s: s["spath"], True),
]

########################### Connections ###########################

CONNECTION_COLUMNS = [
    ("ID", lambda m, c: c["id"], "<", 42, lambda m, c: c["id"], False),
    ("PTCL", lambda m, c: c["proto"], "<", 4, lambda m, c: c["proto"], True),
    (
        "START_TIME",
        lambda m, c: datetime.fromtimestamp(c["valid_from"], timezone.utc).astimezone(
            get_timezone(m)
        ),
        "<",
        27,
        lambda m, c: c["valid_from"],
        False,
    ),
    (
        "END_TIME",
        lambda m, c: datetime.fromtimestamp(c["valid_to"], timezone.utc).astimezone(
            get_timezone(m)
        )
        if "valid_to" in c
        else None,
        "<",
        27,
        lambda m, c: c.get("valid_to", None),
        False,
    ),
    (
        "DURATION",
        lambda m, c: pretty_time(m.timestamp - c["valid_from"])
        if "duration" not in c or "valid_to" not in c or c["valid_to"] > m.timestamp
        else pretty_time(c["duration"]),
        "<",
        9,
        lambda m, c: m.timestamp - c["valid_from"]
        if "duration" not in c or "valid_to" not in c or c["valid_to"] > m.timestamp
        else c["duration"],
        True,
    ),
    (
        "TXPACK",
        lambda m, c: c["packets_tx"],
        ">",
        6,
        lambda m, c: c["packets_tx"],
        False,
    ),
    (
        "RXPACK",
        lambda m, c: c["packets_rx"],
        ">",
        6,
        lambda m, c: c["packets_rx"],
        False,
    ),
    (
        "TXBYTES",
        lambda m, c: pretty_bytes(c["bytes_tx"]),
        ">",
        7,
        lambda m, c: c["bytes_tx"],
        True,
    ),
    (
        "RXBYTES",
        lambda m, c: pretty_bytes(c["bytes_rx"]),
        ">",
        7,
        lambda m, c: c["bytes_rx"],
        True,
    ),
    (
        "PROCESS",
        lambda m, c: c["proc_name"],
        "<",
        15,
        lambda m, c: c["proc_name"],
        True,
    ),
    (
        "PEER",
        lambda m, c: f'{c["peer_proc_name"]} on {c["peer_muid"]}'
        if "peer_proc_name" in c and "peer_muid" in c
        else "${8,1}EXTERNAL",
        "<",
        20,
        lambda m, c: c.get("peer_proc_name", "EXTERNAL"),
        False,
    ),
    (
        "LOCAL",
        lambda m, c: pretty_address(c["local_ip"], c["local_port"]),
        ">",
        45,
        lambda m, c: f'{c["local_ip"]}:{c["local_port"]}',
        True,
    ),
    (
        "DIR",
        lambda m, c: "${3}<--"
        if c["direction"] == "inbound"
        else "${4}-->"
        if c["direction"] == "outbound"
        else "${8,1}?",
        "^",
        3,
        lambda m, c: c["direction"] == "inbound",
        True,
    ),
    (
        "REMOTE",
        lambda m, c: pretty_address(c["remote_ip"], c["remote_port"]),
        "<",
        0,
        lambda m, c: f'{c["remote_ip"]}:{c["remote_port"]}',
        True,
    ),
]

########################### Flags ###########################


def color_severity(_m, f) -> str:
    """Format the severity of a flag."""
    severity = f["severity"]
    if severity == "info":
        return "${8}I"
    if severity == "low":
        return "L"
    if severity == "medium":
        return "${11}M"
    if severity == "high":
        return "${3,1}H"
    if severity == "critical":
        return "${1,1}C"
    return "${8,1}?"


SEVERITIES = {"info": -1, "low": 0, "medium": 1, "high": 2, "critical": 3}

FLAG_COLUMNS = [
    ("ID", lambda m, f: f["id"], "<", 42, lambda m, f: f["id"], False),
    (
        "TIME",
        lambda m, f: datetime.fromtimestamp(f["time"], timezone.utc).astimezone(
            get_timezone(m)
        ),
        "<",
        27,
        lambda m, f: f["time"],
        True,
    ),
    (
        "AGE",
        lambda m, f: pretty_time(m.timestamp - f["time"]),
        ">",
        9,
        lambda m, f: m.timestamp - f["time"],
        True,
    ),
    (
        "EXCEPTED",
        lambda m, f: "${2}Y" if f["false_positive"] else "${1}N",
        "^",
        8,
        lambda m, f: f["false_positive"],
        True,
    ),
    ("SEV", color_severity, "^", 3, lambda m, f: SEVERITIES[f["severity"]], True),
    (
        "MITRE",
        lambda m, f: f["mitre_mapping"][0].get("technique_name", "")
        if f["mitre_mapping"]
        else "",
        "<",
        30,
        lambda m, f: f["mitre_mapping"][0].get("technique_name", "")
        if f["mitre_mapping"]
        else "",
        False,
    ),
    (
        "ANCESTORS",
        lambda m, f: "/".join(f.get("ancestors", None) or []),
        "<",
        30,
        lambda m, f: "/".join(f.get("ancestors", None) or []),
        False,
    ),
    (
        "Description",
        lambda m, f: f["description"],
        "<",
        0,
        lambda m, f: f["description"],
        True,
    ),
]

########################### Listening Sockets ###########################

LISTENING_SOCKET_COLUMNS = [
    ("ID", lambda m, l: l["id"], "<", 42, lambda m, l: l["id"], False),
    ("FAMILY", lambda m, l: l["family"], "<", 4, lambda m, l: l["family"], True),
    ("PTCL", lambda m, l: l["proto"], "<", 4, lambda m, l: l["proto"], True),
    (
        "START_TIME",
        lambda m, l: datetime.fromtimestamp(l["valid_from"], timezone.utc).astimezone(
            get_timezone(m)
        ),
        "<",
        27,
        lambda m, l: l["valid_from"],
        False,
    ),
    (
        "DURATION",
        lambda m, l: pretty_time(m.timestamp - l["valid_from"])
        if "duration" not in l or l["valid_to"] > m.timestamp
        else pretty_time(l["duration"]),
        "<",
        9,
        lambda m, l: l.get("duration", m.timestamp - l["valid_from"]),
        True,
    ),
    (
        "LOCAL",
        lambda m, l: pretty_address(l["local_ip"], l["local_port"]),
        ">",
        45,
        lambda m, l: f'{l["local_ip"]}:{l["local_port"]}',
        True,
    ),
    ("PUID", lambda m, l: l["puid"], "<", 20, lambda m, l: l["puid"], False),
    ("PROCESS", lambda m, l: l["proc_name"], "<", 0, lambda m, l: l["proc_name"], True),
]
