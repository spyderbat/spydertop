#
# meters.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc.  All rights reserved.
#

"""
A series of functions to handle the processing and formatting of top data for
the header meters.
"""


from typing import Dict
from datetime import timedelta

from spydertop.model import AppModel
from spydertop.utils import add_palette, header_bytes

# --- Disk IO Meter ---


def sum_disks(disks: Dict[str, Dict[str, int]]):
    # see https://github.com/htop-dev/htop/blob/main/linux/Platform.c#L578-L593 for reference
    prev_disk_name = ""
    totals: Dict[str, int] = {
        "io_time_ms": 0,
        "ios_in_progress": 0,
        "read_completed": 0,
        "read_time_ms": 0,
        "reads_merged": 0,
        "sectors_read": 0,
        "sectors_written": 0,
        "weighted_io_time_ms": 0,
        "write_time_ms": 0,
        "writes_completed": 0,
        "writes_merged": 0,
    }

    for (disk_name, values) in disks.items():
        # ignore these disks
        if disk_name.startswith("dm-") or disk_name.startswith("zram"):
            continue

        # assuming sda comes before sda1, skip all duplicate partitions
        if prev_disk_name != "" and disk_name.startswith(prev_disk_name):
            continue

        prev_disk_name = disk_name

        for (key, val) in values.items():
            if key not in totals:
                totals[key] = 0
            totals[key] += val
    return totals


def show_disk_io(model: AppModel):
    # modeled after https://github.com/htop-dev/htop/blob/main/DiskIOMeter.c#L34-L108
    disk = model.get_value("disk")
    prev_disk = model.get_value("disk", previous=True)
    disk_count = len(disk.keys()) + 0.00000001
    disk = sum_disks(disk)
    prev_disk = sum_disks(prev_disk)
    time_elapsed_ms = model.time_elapsed * 1000
    percent_used = round(
        (disk["io_time_ms"] - prev_disk["io_time_ms"])
        / time_elapsed_ms
        / disk_count
        * 100,
        1,
    )
    read_bytes = header_bytes((disk["sectors_read"] - prev_disk["sectors_read"]) * 512)
    write_bytes = header_bytes(
        (disk["sectors_written"] - prev_disk["sectors_written"]) * 512
    )
    return add_palette(
        "  ${{{meter_label}}}Disk IO: ${{{meter_label},1}}{percent_used}% ${{{meter_label}}}read: ${{2}}{read_bytes} ${{{meter_label}}}write ${{4}}{write_bytes}",
        model,
        percent_used=percent_used,
        read_bytes=read_bytes,
        write_bytes=write_bytes,
    )


# --- Network Meter ---


def show_network(model: AppModel):
    network_totals = model.get_value("network")["total"]
    prev_net_totals = model.get_value("network", previous=True)["total"]
    time_elapsed_sec = model.time_elapsed
    rx = header_bytes(
        (network_totals["bytes_rx"] - prev_net_totals["bytes_rx"]) / time_elapsed_sec
    )
    tx = header_bytes(
        (network_totals["bytes_tx"] - prev_net_totals["bytes_tx"]) / time_elapsed_sec
    )
    if not (tx[-1]).isdigit():
        tx += "i"
    if not (rx[-1]).isdigit():
        rx += "i"
    reads = network_totals["reads"] - prev_net_totals["reads"]
    writes = network_totals["writes"] - prev_net_totals["writes"]

    return add_palette(
        "  ${{{meter_label}}}Network: rx: ${{2}}{rx}b/s ${{{meter_label}}}write: ${{4}}{tx}b/s ${{{meter_label}}}({reads}/{writes} reads/writes)",
        model,
        rx=rx,
        tx=tx,
        reads=reads,
        writes=writes,
    )


# --- Task Meter ---


def show_tasks(model: AppModel):
    tasks = model.get_value("tasks")
    # this is necessary because of how tasks seem to be counted
    task_count = len(model.get_value("processes")) - tasks["kernel_threads"]
    running = tasks["running"]
    threads = tasks["total_threads"] - tasks["kernel_threads"]
    kthreads = tasks["kernel_threads"]

    thread_style = "${8,1}" if model.config["hide_threads"] else "${2,1}"
    thread_lbl_style = (
        "${{8}}" if model.config["hide_threads"] else "${{{meter_label}}}"
    )
    kthread_style = "${8,1}" if model.config["hide_kthreads"] else "${2,1}"
    kthread_lbl_style = (
        "${{8}}" if model.config["hide_kthreads"] else "${{{meter_label}}}"
    )
    return add_palette(
        "  ${{{meter_label}}}Tasks: ${{{meter_label},1}}{task_count}"
        + thread_lbl_style
        + ", {thread_style}{threads} "
        + thread_lbl_style
        + "thr"
        + kthread_lbl_style
        + ", {kthread_style}{kthreads} "
        + kthread_lbl_style
        + "kthr${{{meter_label}}}; ${{2,1}}{running} ${{{meter_label}}}running",
        model,
        task_count=task_count,
        threads=threads,
        kthreads=kthreads,
        running=running,
        thread_style=thread_style,
        kthread_style=kthread_style,
    )


# --- Load Average Meter ---


def show_ld_avg(model: AppModel):
    ld_avg = model.get_value("load_avg")

    if len(ld_avg) < 3:
        return add_palette("  ${{{meter_label}}}Load average: ${{1,1}}No Data", model)
    return add_palette(
        "  ${{{meter_label}}}Load average: ${{{background},1}}{ld_avg[0]} ${{{meter_label},1}}{ld_avg[1]} ${{{meter_label}}}{ld_avg[2]}",
        model,
        ld_avg=ld_avg,
    )


# --- CPU Meter ---


def update_cpu(i, model: AppModel):
    # reference: https://github.com/htop-dev/htop/blob/main/linux/Platform.c#L312-L346
    cpu = model.get_value("cpu_time")[f"cpu{i}"]
    prev_cpu = model.get_value("cpu_time", previous=True)[f"cpu{i}"]
    time_elapsed_sec = model.time_elapsed
    clk_tck = model.get_value("clk_tck")
    values = [0, 0, 0, 0]
    values[0] = (cpu["nice_time"] - prev_cpu["nice_time"]) / clk_tck / time_elapsed_sec
    values[1] = (
        (cpu["user_space_time"] - prev_cpu["user_space_time"])
        / clk_tck
        / time_elapsed_sec
    )
    values[2] = (
        (cpu["system_time"] - prev_cpu["system_time"]) / clk_tck / time_elapsed_sec
    )
    values[3] = (
        (
            cpu["guest_time"]
            + cpu["steal_time"]
            - prev_cpu["guest_time"]
            - prev_cpu["steal_time"]
        )
        / clk_tck
        / time_elapsed_sec
    )
    return values


# --- Memory Meter ---


def get_memory(model: AppModel):
    # reference: https://github.com/htop-dev/htop/blob/main/linux/LinuxProcessList.c#L1778-L1795
    # and https://github.com/htop-dev/htop/blob/main/linux/Platform.c#L354-L357
    mem = model.memory
    if not mem:
        return (0.00000001, (0, 0, 0, 0))
    total = mem["MemTotal"]
    buffers = mem["Buffers"]
    usedDiff = mem["MemFree"] + mem["Cached"] + mem["SReclaimable"] + buffers
    used = total - usedDiff if total >= usedDiff else total - mem["MemFree"]
    shared = mem["Shmem"]
    cached = mem["Cached"] + mem["SReclaimable"] - shared
    values = [0, 0, 0, 0]
    values[0] = used
    values[1] = buffers
    values[2] = shared
    values[3] = cached

    return (total, values)


# --- Swap Meter ---


def get_swap(model: AppModel):
    # reference: https://github.com/htop-dev/htop/blob/main/linux/LinuxProcessList.c#L1793-L1795
    mem = model.memory
    if not mem:
        return (0.00000001, (0, 0))
    total = mem["SwapTotal"]
    cached = mem["SwapCached"]
    used = total - mem["SwapFree"] - cached
    values = [0, 0]
    values[0] = used
    values[1] = cached

    return (total, values)


# --- Uptime ---


def show_uptime(model: AppModel):
    mach = model.machine
    uptime = timedelta(seconds=model.timestamp - mach["boot_time"])
    return add_palette(
        "  ${{{meter_label}}}Uptime: ${{{background},1}}{uptime}",
        model,
        uptime=uptime,
    )
