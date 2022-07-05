#
# columns.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc.  All rights reserved.
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

from datetime import datetime

from spydertop.utils import pretty_address, pretty_bytes, pretty_time, PAGE_SIZE

########################### Processes ###########################

# functions for the processes table take four parameters:
#   - m: the model
#   - pr: the previous resource usage record
#   - r: the current resource usage record
#   - p: the current model process record
# both the pr and r parameters may be None if
# the process is a thread, or if no information is found


def get_cpu_per(m, pr, r, p):
    if r is None:
        return None
    time_delta = m.time_elapsed
    clk_tck = m.get_value("clk_tck")
    cpu = r["utime"] - pr["utime"] + r["stime"] - pr["stime"]
    cpu /= time_delta
    cpu /= clk_tck
    cpu = round(cpu * 100, 1)
    return cpu


def get_mem_per(m, pr, r, p):
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


def get_time_plus(m, pr, r, p):
    if r is None:
        return None
    clk_tck = m.get_value("clk_tck")
    cpu = r["utime"] + r["stime"]
    time = cpu / clk_tck
    return pretty_time(time)


def get_time_plus_value(m, pr, r, p):
    if r is None:
        return None
    clk_tck = m.get_value("clk_tck")
    cpu = r["utime"] + r["stime"]
    time = cpu / clk_tck
    return time


def color_cmd(m, pr, r, p):
    base = f'{" ".join(p["args"])}'
    color = ""
    if p["thread"] == True:
        color = "${2}"
    if p["type"] == "kernel thread":
        color = "${8,1}"
    return color + base


PROCESS_COLUMNS = [
    ("ID", lambda m, pr, r, p: p["id"], "<", 30, lambda m, pr, r, p: p["id"], False),
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
        "START_TIME",
        lambda m, pr, r, p: datetime.fromtimestamp(int(p["valid_from"])),
        ">",
        27,
        lambda m, pr, r, p: p["valid_from"],
        False,
    ),
    (
        "PRI",
        lambda m, pr, r, p: int(r["priority"]) if r else "",
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
        else "",
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
        lambda m, pr, r, p: int(r["rss"]) if r else None,
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
        else "",
        "^",
        1,
        lambda m, pr, r, p: r["state"] if r else None,
        True,
    ),
    ("CPU%", get_cpu_per, ">", 4, get_cpu_per, True),
    ("MEM%", get_mem_per, ">", 4, get_mem_per, True),
    ("TIME+", get_time_plus, ">", 9, get_time_plus_value, True),
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
        "START_TIME",
        lambda m, s: datetime.fromtimestamp(int(s["valid_from"])),
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
    ("MUID", lambda m, s: s["muid"], "<", 20, lambda m, s: s["muid"], True),
    ("SESSPATH", lambda m, s: s["spath"], "<", 0, lambda m, s: s["spath"], True),
]

########################### Connections ###########################

CONNECTION_COLUMNS = [
    ("ID", lambda m, c: c["id"], "<", 42, lambda m, c: c["id"], False),
    ("PTCL", lambda m, c: c["proto"], "<", 4, lambda m, c: c["proto"], True),
    (
        "START_TIME",
        lambda m, c: datetime.fromtimestamp(c["valid_from"]),
        "<",
        27,
        lambda m, c: c["valid_from"],
        False,
    ),
    (
        "END_TIME",
        lambda m, c: datetime.fromtimestamp(c["valid_to"]) if "valid_to" in c else None,
        "<",
        27,
        lambda m, c: c["valid_to"] if "valid_to" in c else None,
        False,
    ),
    (
        "DURATION",
        lambda m, c: pretty_time(m.timestamp - c["valid_from"])
        if "duration" not in c or c["valid_to"] > m.timestamp
        else pretty_time(c["duration"]),
        "<",
        9,
        lambda m, c: c["duration"]
        if "duration" in c
        else m.timestamp - c["valid_from"],
        True,
    ),
    (
        "TXBYTES",
        lambda m, c: pretty_bytes(c["bytes_tx"]),
        ">",
        5,
        lambda m, c: c["bytes_tx"],
        True,
    ),
    (
        "RXBYTES",
        lambda m, c: pretty_bytes(c["bytes_rx"]),
        ">",
        5,
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
        "LOCAL",
        lambda m, c: pretty_address(c["local_ip"], c["local_port"]),
        ">",
        45,
        lambda m, c: f'{c["local_ip"]}:{c["local_port"]}',
        True,
    ),
    (
        "DIR",
        lambda m, c: "${3}<--" if c["direction"] == "inbound" else "${4}-->",
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


def color_severity(m, f):
    severity = f["severity"]
    if severity == "info":
        return "${8}I"
    elif severity == "low":
        return "L"
    elif severity == "medium":
        return "${11}M"
    elif severity == "high":
        return "${3,1}H"
    elif severity == "critical":
        return "${1,1}C"


SEVERITIES = {"info": -1, "low": 0, "medium": 1, "high": 2, "critical": 3}

FLAG_COLUMNS = [
    ("ID", lambda m, f: f["id"], "<", 42, lambda m, f: f["id"], False),
    (
        "TIME",
        lambda m, f: datetime.fromtimestamp(f["time"]),
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
        lambda m, f: f["time"],
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
        lambda m, l: datetime.fromtimestamp(l["valid_from"]),
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
        lambda m, l: l["duration"]
        if "duration" in l
        else m.timestamp - l["valid_from"],
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
    ("PROCESS", lambda m, l: l["proc_name"], "<", 0, lambda m, l: l["proc_name"], True),
]
